"""Проверка интерфейса на временной базе. Нужен Playwright и Chromium."""
import json
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor.checker import Monitor
from monitor.database import Database
from monitor.server import Server, make_handler
from scripts.demo import DemoHandler


def main():
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as temp:
        db = Database(Path(temp) / "ui.db")
        monitor = Monitor(db)
        target = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
        server = Server(("127.0.0.1", 0), make_handler(db, monitor))
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (target, server)]
        for thread in threads:
            thread.start()
        monitor.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            for name, endpoint in (("API магазина", "ok"), ("Платёжный шлюз", "fail"),
                                   ("Каталог товаров", "slow"), ("Сервис уведомлений", "unstable")):
                body = json.dumps({"name": name, "url": f"http://127.0.0.1:{target.server_port}/{endpoint}",
                                   "category": "Демо", "interval": 10}).encode()
                request = urllib.request.Request(base + "/api/services", data=body,
                                                  headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request) as response:
                    assert response.status == 201
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                page.wait_for_function("() => document.querySelectorAll('#services tr').length === 4 && !document.querySelector('#services .pending')")
                screenshots = ROOT / "docs" / "screenshots"
                screenshots.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshots / "dashboard.png"), full_page=True)
                page.get_by_role("button", name="API магазина", exact=True).click()
                page.locator("#checks .history-item").first.wait_for()
                page.screenshot(path=str(screenshots / "service.png"), full_page=True)
                page.locator("#pause").click()
                page.wait_for_function("() => document.querySelector('#pause').textContent === 'Продолжить'")
                page.locator("#check").click()
                page.locator("#close-detail").click()
                page.locator("#search").fill("Платёжный")
                page.wait_for_function("() => document.querySelectorAll('#services tr').length === 1")
                page.locator("#search").fill("")
                page.wait_for_function("() => document.querySelectorAll('#services tr').length === 4")
                page.locator("#add").click()
                page.locator("[name=name]").fill("Тестовый сервис")
                page.locator("[name=url]").fill(f"http://127.0.0.1:{target.server_port}/ok")
                page.get_by_role("button", name="Сохранить сервис").click()
                page.get_by_role("button", name="Тестовый сервис", exact=True).wait_for()
                page.get_by_role("button", name="Тестовый сервис", exact=True).click()
                page.locator("#edit").click()
                page.locator("[name=name]").fill("Переименованный сервис")
                page.get_by_role("button", name="Сохранить сервис").click()
                page.get_by_role("button", name="Переименованный сервис", exact=True).wait_for()
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator("#delete").click()
                page.wait_for_function("() => document.querySelectorAll('#services tr').length === 4")
                report = page.request.get(base + "/api/report.csv")
                assert report.status == 200 and "API магазина" in report.body().decode("utf-8-sig")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator("#toast").wait_for(state="hidden")
                page.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Горизонтальная прокрутка страницы"
                assert not errors, errors
                browser.close()
                print("UI: создание, изменение, удаление, поиск, история, пауза, ручная проверка, CSV и мобильный экран — OK")
        finally:
            server.shutdown()
            target.shutdown()
            server.server_close()
            target.server_close()
            monitor.stop()
            for thread in threads:
                thread.join()


if __name__ == "__main__":
    main()
