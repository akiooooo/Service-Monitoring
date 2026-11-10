import csv
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from monitor.checker import Monitor, probe
from monitor.database import Database, now
from monitor.server import APIError, Server, make_handler, validate


class Target(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/slow":
            time.sleep(1.2)
        code = 503 if self.path == "/fail" else 302 if self.path == "/redirect" else 200
        self.send_response(code)
        if code == 302:
            self.send_header("Location", "/ok")
        self.end_headers()

    def log_message(self, *args):
        pass


class MonitoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
        cls.target_thread = threading.Thread(target=cls.target.serve_forever, daemon=True)
        cls.target_thread.start()
        cls.url = f"http://127.0.0.1:{cls.target.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.target.shutdown()
        cls.target.server_close()
        cls.target_thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "data")
        self.db = Database(Path(self.temp.name) / "test.db")
        self.monitor = Monitor(self.db)
        self.server = Server(("127.0.0.1", 0), make_handler(self.db, self.monitor))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.monitor.pool.shutdown(wait=True)
        self.temp.cleanup()

    def request(self, path, method="GET", data=None, headers=None):
        request = urllib.request.Request(self.base + quote(path, safe="/?=&"),
            data=json.dumps(data).encode() if data is not None else None, method=method,
            headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            content = response.read()
            return response.status, json.loads(content) if "json" in response.headers["Content-Type"] else content

    def add(self, **extra):
        status, data = self.request("/api/services", "POST", {"name": "API", "url": self.url + "/ok", **extra})
        self.assertEqual(status, 201)
        return data["id"]

    def test_probe_success_failure_redirect_and_timeout(self):
        for path, expected, ok, code in (("/ok", 200, True, 200), ("/fail", 200, False, 503),
                                         ("/redirect", 200, False, 302), ("/redirect", 302, True, 302),
                                         ("/slow", 200, False, None)):
            with self.subTest(path=path, expected=expected):
                result = probe({"url": self.url + path, "timeout": 1, "expected_code": expected})
                self.assertEqual(result["ok"], ok)
                self.assertEqual(result["status_code"], code)
                self.assertGreaterEqual(result["response_ms"], 0)

    def test_incident_dedup_recovery_and_persistence(self):
        service_id = self.add()
        failure = {"ok": False, "response_ms": 100, "status_code": 503, "error": "HTTP 503"}
        self.db.record(service_id, failure)
        self.db.record(service_id, failure)
        self.db.record(service_id, {**failure, "ok": True, "error": None, "status_code": 200})
        self.db.record(service_id, failure)
        reopened = Database(self.db.path)
        with reopened.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM checks").fetchone()[0], 4)
            incidents = db.execute("SELECT * FROM incidents ORDER BY id").fetchall()
            self.assertEqual(len(incidents), 2)
            self.assertIsNotNone(incidents[0]["resolved_at"])
            self.assertIsNone(incidents[1]["resolved_at"])
        self.assertEqual(self.request("/api/services")[1][0]["uptime"], 25)

    def test_crud_filters_history_and_cascade(self):
        service_id = self.add(name="Магазин", category="Backend")
        self.assertEqual(len(self.request("/api/services?q=магазин&status=pending&category=Backend")[1]), 1)
        self.assertEqual(self.request("/api/services?status=up")[1], [])
        status, _ = self.request(f"/api/services/{service_id}", "PUT", {"name": "Новое имя", "url": self.url, "enabled": False})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("/api/services")[1][0]["status"], "paused")
        self.db.record(service_id, {"ok": False, "response_ms": 3, "status_code": 500, "error": "HTTP 500"})
        self.assertEqual(len(self.request(f"/api/services/{service_id}/history")[1]["checks"]), 1)
        self.assertEqual(self.request(f"/api/services/{service_id}", "DELETE")[0], 200)
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM checks").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0], 0)
        self.assertEqual(self.request(f"/api/services/{service_id}/history")[0], 404)

    def test_validation_and_origin(self):
        for extra in ({"url": "file:///etc/passwd"}, {"url": "https://user:pass@example.com"},
                      {"url": "http://example.com:bad"}, {"interval": 0}, {"timeout": True},
                      {"name": " "}, {"expected_code": 999}, {"enabled": "false"}):
            with self.subTest(extra=extra):
                self.assertEqual(self.request("/api/services", "POST", {"name": "API", "url": self.url, **extra})[0], 400)
        self.assertEqual(self.request("/api/services", "POST", [], {"Origin": "https://other.test"})[0], 403)
        self.assertEqual(self.request("/api/services?hours=0")[0], 400)
        self.assertEqual(self.request("/api/services?hours=abc")[0], 400)
        self.assertEqual(self.request("/../run.py")[0], 404)

    def test_period_and_csv_formula_protection(self):
        service_id = self.add(name="=HYPERLINK(1)")
        self.db.record(service_id, {"ok": True, "response_ms": 24, "status_code": 200, "error": None})
        with self.db.connect() as db:
            db.execute("INSERT INTO checks(service_id,checked_at,ok,response_ms) VALUES (?, ?, 0, 10)",
                       (service_id, "2000-01-01T00:00:00.000+00:00"))
        self.assertEqual(self.request("/api/services?hours=24")[1][0]["uptime"], 100)
        status, body = self.request("/api/report.csv")
        rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(status, 200)
        self.assertTrue(rows[1][0].startswith("'="))
        self.assertEqual(rows[1][2:5], ["1", "1", "100.0"])

    def test_scheduler_pause_and_manual_check(self):
        active = self.add()
        paused = self.add(enabled=False)
        self.monitor.start()
        try:
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                with self.db.connect() as db:
                    count = db.execute("SELECT COUNT(*) FROM checks WHERE service_id=?", (active,)).fetchone()[0]
                if count:
                    break
                time.sleep(.05)
            self.assertGreater(count, 0)
            with self.db.connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM checks WHERE service_id=?", (paused,)).fetchone()[0], 0)
            self.assertEqual(self.request(f"/api/services/{paused}/check", "POST", {})[0], 202)
        finally:
            self.monitor.stop()

    def test_duplicate_checks_are_rejected(self):
        service_id = self.add(url=self.url + "/slow")
        service = self.db.service(service_id)
        self.assertTrue(self.monitor.submit(service))
        self.assertFalse(self.monitor.submit(service))


if __name__ == "__main__":
    unittest.main()
