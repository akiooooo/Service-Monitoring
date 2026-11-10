import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


WORKER = Path(__file__).resolve().parents[1]/'scripts/publish_prepared.py'
SPEC = importlib.util.spec_from_file_location('queue_schedule', WORKER)
SCHEDULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCHEDULE)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root/'repo'
        self.origin = self.root/'origin.git'
        self.repo.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Queue test')
        self.git('config', 'user.email', 'queue@example.test')
        (self.repo/'README.md').write_text('baseline\n', encoding='utf-8')
        self.git('add', '.')
        self.git('commit', '-m', 'baseline')
        base = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-b', 'prepared-improvements')
        (self.repo/'tests').mkdir()
        (self.repo/'tests/test_added.py').write_text('import os, unittest\nclass Added(unittest.TestCase):\n    def test_contract(self):\n        self.assertNotEqual(os.getenv("FAIL_QUEUE_TEST"), "1")\n', encoding='utf-8')
        self.git('add', '.')
        self.git('commit', '-m', 'Проверить контракт приложения')
        sha = self.git('rev-parse', 'HEAD')
        patch = subprocess.check_output(['git', 'diff', '--binary', base, sha], cwd=self.repo)
        self.manifest = {'version': 1, 'repository': 'queue/test', 'branch': 'prepared-improvements', 'baseline': base, 'entries': [
            {'number': i, 'commit': sha, 'title': 'Проверить контракт приложения', 'files': ['tests/test_added.py'], 'sha256': hashlib.sha256(patch).hexdigest()} for i in range(1, 101)]}
        self.git('checkout', 'main')
        (self.repo/'scripts').mkdir()
        (self.repo/'scripts/publish_prepared.py').write_bytes(WORKER.read_bytes())
        (self.repo/'.ghostcommit').mkdir()
        self.write_manifest()
        self.write_state({'completed': 0})
        self.git('add', '.')
        self.git('commit', '-m', 'setup')
        subprocess.run(['git', 'init', '--bare', str(self.origin)], check=True, capture_output=True)
        self.git('remote', 'add', 'origin', str(self.origin))
        self.git('push', 'origin', 'main', 'prepared-improvements')
        self.remote_before = self.git('ls-remote', 'origin', 'refs/heads/main')

    def tearDown(self):
        # Git делает object-файлы read-only на Windows.
        for path in self.root.rglob('*'):
            if path.is_file():
                path.chmod(0o600)
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, stderr=subprocess.PIPE).decode('utf-8').strip()

    def write_manifest(self):
        (self.repo/'.ghostcommit/queue.json').write_text(json.dumps(self.manifest, ensure_ascii=False), encoding='utf-8')

    def write_state(self, value):
        (self.repo/'.ghostcommit/state.json').write_text(json.dumps(value), encoding='utf-8')

    def save(self):
        self.git('add', '.')
        self.git('commit', '-m', 'test configuration')

    def worker(self, *args, fail=False):
        return subprocess.run([sys.executable, 'scripts/publish_prepared.py', *args], cwd=self.repo,
            env={**os.environ, 'PYTHONUTF8': '1', 'FAIL_QUEUE_TEST': '1' if fail else '0'}, capture_output=True, encoding='utf-8')

    def scheduled_worker(self, hour):
        launcher = '''import importlib.util, sys
from datetime import datetime, timezone, timedelta
spec = importlib.util.spec_from_file_location("worker", "scripts/publish_prepared.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.moscow_now = lambda: datetime(2026, 11, 10, HOUR, 30, tzinfo=timezone(timedelta(hours=3)))
sys.argv = ["publish_prepared.py", "--scheduled"]
worker.main()
'''.replace('HOUR', str(hour))
        return subprocess.run([sys.executable, '-B', '-c', launcher], cwd=self.repo,
            env={**os.environ, 'PYTHONUTF8': '1', 'FAIL_QUEUE_TEST': '0'}, capture_output=True, encoding='utf-8')

    def assert_no_push(self):
        self.assertEqual(self.git('ls-remote', 'origin', 'refs/heads/main'), self.remote_before)

    def test_check_only_keeps_repository_clean(self):
        result = self.worker('--check-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assert_no_push()

    def test_success_applies_checks_and_pushes_one_change(self):
        result = self.worker()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.repo/'.ghostcommit/state.json').read_text())
        self.assertEqual(state['completed'], 1)
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'Проверить контракт приложения')
        self.assertNotEqual(self.git('ls-remote', 'origin', 'refs/heads/main'), self.remote_before)

    def test_failed_tests_never_push(self):
        result = self.worker(fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads((self.repo/'.ghostcommit/state.json').read_text())['completed'], 0)
        self.assert_no_push()

    def test_changed_patch_hash_blocks_publication(self):
        self.manifest['entries'][0]['sha256'] = '0'*64
        self.write_manifest()
        self.save()
        self.assertNotEqual(self.worker().returncode, 0)
        self.assertFalse((self.repo/'tests/test_added.py').exists())
        self.assert_no_push()

    def test_changed_title_blocks_publication(self):
        self.manifest['entries'][0]['title'] = 'Не соответствует изменению'
        self.write_manifest()
        self.save()
        self.assertNotEqual(self.worker().returncode, 0)
        self.assert_no_push()

    def test_dirty_worktree_is_preserved(self):
        (self.repo/'README.md').write_text('user edits', encoding='utf-8')
        self.assertNotEqual(self.worker().returncode, 0)
        self.assertEqual((self.repo/'README.md').read_text(), 'user edits')
        self.assert_no_push()

    def test_finished_queue_is_noop(self):
        self.write_state({'completed': 100})
        self.save()
        self.assertEqual(self.worker().returncode, 0)
        self.assert_no_push()

    def test_invalid_cursor_is_rejected(self):
        self.write_state({'completed': -1})
        self.save()
        self.assertNotEqual(self.worker().returncode, 0)
        self.assert_no_push()

    def test_apply_conflict_does_not_change_existing_file(self):
        (self.repo/'tests').mkdir(exist_ok=True)
        (self.repo/'tests/test_added.py').write_text('existing user code', encoding='utf-8')
        self.save()
        self.assertNotEqual(self.worker().returncode, 0)
        self.assertEqual((self.repo/'tests/test_added.py').read_text(), 'existing user code')
        self.assert_no_push()

    def test_wrong_parent_is_rejected(self):
        self.manifest['baseline'] = '0'*40
        self.write_manifest()
        self.save()
        self.assertNotEqual(self.worker().returncode, 0)
        self.assert_no_push()

    def test_daily_limit_stops_after_four_publications(self):
        today = datetime.now(timezone(timedelta(hours=3))).date().isoformat()
        self.write_state({'completed': 0, 'day': today, 'published_today': 4})
        self.save()
        self.assertEqual(self.worker().returncode, 0)
        self.assertFalse((self.repo/'tests/test_added.py').exists())
        self.assert_no_push()

    def test_daily_random_target_blocks_extra_publication(self):
        today = datetime.now(timezone(timedelta(hours=3))).date().isoformat()
        target = SCHEDULE.daily_plan('queue/test', today)['target']
        self.write_state({'completed': 0, 'day': today, 'published_today': target})
        self.save()
        self.assertEqual(self.worker().returncode, 0)
        self.assert_no_push()

    def test_new_day_resets_daily_limit(self):
        self.write_state({'completed': 0, 'day': '2000-01-01', 'published_today': 3})
        self.save()
        result = self.worker()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.repo/'.ghostcommit/state.json').read_text())
        self.assertEqual((state['completed'], state['published_today']), (1, 1))

    def test_selected_hour_publishes_and_remembers_slot(self):
        hour = SCHEDULE.daily_plan('queue/test', '2026-11-10')['slots'][0]['hour']
        result = self.scheduled_worker(hour)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.repo/'.ghostcommit/state.json').read_text())
        self.assertEqual(state['scheduled_hours'], [hour])
        self.assertEqual(state['completed'], 1)

    def test_unselected_hour_never_pushes(self):
        selected = {s['hour'] for s in SCHEDULE.daily_plan('queue/test', '2026-11-10')['slots']}
        hour = next(h for h in range(9, 23) if h not in selected)
        result = self.scheduled_worker(hour)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.repo/'tests/test_added.py').exists())
        self.assert_no_push()


class ScheduleTests(unittest.TestCase):
    def test_plan_has_one_to_four_distinct_hours_inside_window(self):
        for offset in range(100):
            day = (datetime(2026, 11, 10) + timedelta(days=offset)).date().isoformat()
            plan = SCHEDULE.daily_plan('akiooooo/Service-Monitoring', day)
            self.assertIn(plan['target'], range(1, 5))
            hours = [slot['hour'] for slot in plan['slots']]
            self.assertEqual(len(hours), plan['target'])
            self.assertEqual(hours, sorted(set(hours)))
            self.assertTrue(all(9 <= h < 23 for h in hours))
            self.assertTrue(all(0 <= slot['delay_seconds'] < 600 for slot in plan['slots']))

    def test_retries_keep_same_daily_plan(self):
        self.assertEqual(SCHEDULE.daily_plan('queue/test', '2026-11-10'), SCHEDULE.daily_plan('queue/test', '2026-11-10'))

    def test_repositories_get_independent_plans(self):
        self.assertNotEqual(SCHEDULE.daily_plan('queue/one', '2026-11-10'), SCHEDULE.daily_plan('queue/two', '2026-11-10'))

    def test_number_of_publications_varies_between_days(self):
        targets = {SCHEDULE.daily_plan('queue/test', f'2026-11-{day:02}')['target'] for day in range(1, 31)}
        self.assertEqual(targets, {1, 2, 3, 4})

    def test_delay_uses_selected_minute_and_seconds(self):
        plan = {'slots': [{'hour': 9, 'delay_seconds': 245}]}
        self.assertEqual(SCHEDULE.scheduled_delay(plan, datetime(2026, 11, 10, 9, 5), []), 365)

    def test_delayed_runner_does_not_wait_again(self):
        plan = {'slots': [{'hour': 9, 'delay_seconds': 245}]}
        self.assertEqual(SCHEDULE.scheduled_delay(plan, datetime(2026, 11, 10, 9, 22), []), 0)

    def test_processed_and_unselected_hours_are_skipped(self):
        plan = {'slots': [{'hour': 9, 'delay_seconds': 0}]}
        self.assertIsNone(SCHEDULE.scheduled_delay(plan, datetime(2026, 11, 10, 9, 7), [9]))
        self.assertIsNone(SCHEDULE.scheduled_delay(plan, datetime(2026, 11, 10, 12), []))

    def test_window_boundaries_skip_publication(self):
        plan = {'slots': [{'hour': 8, 'delay_seconds': 0}, {'hour': 23, 'delay_seconds': 0}]}
        for current in (datetime(2026, 11, 10, 8, 59), datetime(2026, 11, 10, 23)):
            self.assertIsNone(SCHEDULE.scheduled_delay(plan, current, []))


if __name__ == '__main__':
    unittest.main()
