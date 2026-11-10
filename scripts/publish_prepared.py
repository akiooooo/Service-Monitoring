"""Публикует одно заранее проверенное изменение из закреплённой очереди."""

import argparse
import hashlib
import json
import os
import re
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def git(*args, data=None):
    result = subprocess.run(['git', *args], input=data, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result.stdout


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def summary(message):
    print(message, flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(message+'\n')


def daily_plan(repository, day):
    seed = hashlib.sha256(f'{repository}:{day}:schedule-v1'.encode()).digest()
    rng = random.Random(int.from_bytes(seed, 'big'))
    target = rng.randint(1, 4)
    return {'target': target, 'slots': [
        {'hour': hour, 'delay_seconds': rng.randrange(600)}
        for hour in sorted(rng.sample(range(9, 23), target))]}


def moscow_now():
    return datetime.now(timezone(timedelta(hours=3)))


def scheduled_delay(plan, current, used_hours):
    if not 9 <= current.hour < 23 or current.hour in used_hours:
        return None
    slot = next((slot for slot in plan['slots'] if slot['hour'] == current.hour), None)
    if slot is None:
        return None
    due = current.replace(minute=7, second=0, microsecond=0) + timedelta(seconds=slot['delay_seconds'])
    return max(0, (due-current).total_seconds())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true', help='Проверить следующий шаг без применения и публикации')
    parser.add_argument('--scheduled', action='store_true', help='Применять случайный дневной план и выбранные часы')
    parser.add_argument('--show-plan', action='store_true', help='Показать план текущего московского дня')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    manifest = read_json(root/'.ghostcommit/queue.json')
    state_path = root/'.ghostcommit/state.json'
    state = read_json(state_path)
    entries = manifest['entries']
    position = state['completed']
    if manifest['version'] != 1 or len(entries) != 100 or type(position) is not int or not 0 <= position <= len(entries):
        raise ValueError('Повреждён список очереди или её состояние')
    if position == len(entries):
        summary('Очередь завершена: 100/100. Новые коммиты не создаются.')
        return
    current = moscow_now()
    day = current.date().isoformat()
    plan = daily_plan(manifest['repository'], day)
    if args.show_plan:
        summary(json.dumps({'day': day, **plan}, ensure_ascii=False))
        return
    published = state.get('published_today', 0) if state.get('day') == day else 0
    if published >= plan['target'] and not args.check_only:
        summary(f'План на сегодня выполнен: {published}/{plan["target"]} по московскому дню.')
        return
    if git('status', '--porcelain').strip():
        raise ValueError('Рабочая копия содержит изменения. Публикация остановлена.')
    used_hours = state.get('scheduled_hours', []) if state.get('day') == day else []
    if args.scheduled and not args.check_only:
        delay = scheduled_delay(plan, current, used_hours)
        if delay is None:
            summary('Этот час не выбран дневным планом или уже обработан.')
            return
        if delay:
            time.sleep(delay)
        # Во время ожидания в main могли появиться изменения пользователя.
        branch = os.environ.get('DEFAULT_BRANCH', 'main')
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', branch):
            raise ValueError('Некорректная целевая ветка')
        git('pull', '--ff-only', 'origin', branch)
        manifest = read_json(root/'.ghostcommit/queue.json')
        state = read_json(state_path)
        if moscow_now().date().isoformat() != day or not 9 <= moscow_now().hour < 23:
            summary('Окно публикации завершилось. Изменение остаётся в очереди.')
            return
        if state.get('day') == day:
            published = state.get('published_today', 0)
            used_hours = state.get('scheduled_hours', [])
        if published >= plan['target'] or current.hour in used_hours:
            summary('Этот шаг дневного плана уже выполнен.')
            return
        entries = manifest['entries']
        position = state['completed']
        if type(position) is not int or not 0 <= position <= len(entries):
            raise ValueError('Повреждено состояние очереди после обновления')
        if position == len(entries):
            summary('Очередь завершена: 100/100.')
            return
    entry = entries[position]
    sha = entry['commit']
    if entry['number'] != position+1 or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Нарушен порядок очереди')
    git('fetch', '--no-tags', 'origin', f'refs/heads/{manifest["branch"]}:refs/remotes/origin/{manifest["branch"]}')
    git('merge-base', '--is-ancestor', sha, f'origin/{manifest["branch"]}')
    parent = git('rev-parse', f'{sha}^').decode().strip()
    expected_parent = entries[position-1]['commit'] if position else manifest['baseline']
    if parent != expected_parent:
        raise ValueError('Родитель подготовленного коммита изменился')
    patch = git('diff', '--binary', parent, sha)
    if not patch or hashlib.sha256(patch).hexdigest() != entry['sha256']:
        raise ValueError('Содержимое подготовленного изменения не совпадает с проверенным')
    files = git('diff-tree', '--no-commit-id', '--name-only', '-r', sha).decode('utf-8').splitlines()
    if files != entry['files'] or any(not name.startswith(('tests/', 'monitor/', 'promo_bot/', 'dockercheck/')) and name != 'requirements.txt' for name in files):
        raise ValueError('Изменение затрагивает незаявленные файлы')
    if git('show', '-s', '--format=%s', sha).decode('utf-8').strip() != entry['title']:
        raise ValueError('Описание коммита не совпадает с очередью')
    git('apply', '--check', '--index', '-', data=patch)
    if args.check_only:
        summary(f'Следующий шаг проверен: {entry["number"]}/100 — {entry["title"]}')
        return
    # Изменения применяются строго по порядку; при ошибке CI сохранит диагностику.
    git('apply', '--index', '-', data=patch)
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
        env={**os.environ, 'PYTHONUTF8': '1'}, timeout=300)
    if result.returncode:
        raise RuntimeError('Тесты не прошли. Изменение не закоммичено и не отправлено.')
    if git('diff', '--name-only').strip():
        raise RuntimeError('Проверки изменили отслеживаемые файлы. Публикация остановлена.')
    if args.scheduled and (moscow_now().date().isoformat() != day or not 9 <= moscow_now().hour < 23):
        raise RuntimeError('Окно публикации закончилось во время тестов. Изменение не отправлено.')
    if args.scheduled:
        used_hours = [*used_hours, current.hour]
    state.update(completed=position+1, last_prepared_commit=sha, day=day, published_today=published+1,
        daily_target=plan['target'], scheduled_hours=used_hours)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    git('add', '--', '.ghostcommit/state.json')
    git('config', 'user.name', 'akiooooo')
    git('config', 'user.email', '57313968+akiooooo@users.noreply.github.com')
    git('commit', '-m', entry['title'])
    branch = os.environ.get('DEFAULT_BRANCH', 'main')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', branch):
        raise ValueError('Некорректная целевая ветка')
    git('push', 'origin', f'HEAD:refs/heads/{branch}')
    summary(f'Опубликовано {position+1}/100: {entry["title"]}')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Очередь остановлена: {error}', file=sys.stderr)
        sys.exit(1)
