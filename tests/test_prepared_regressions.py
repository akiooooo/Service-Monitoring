import csv
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from monitor.checker import Monitor
from monitor.database import Database
from monitor.server import APIError, Server, make_handler, validate


class PreparedRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "monitor.db")
        self.monitor = Mock()
        self.monitor.submit.return_value = True
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
        self.temp.cleanup()

    def add(self, **extra):
        data = validate({"name": "Сервис", "url": "https://example.test", **extra})
        with self.db.connect() as conn:
            return conn.execute("""INSERT INTO services
                (name,url,category,interval,timeout,expected_code,enabled,created_at)
                VALUES(:name,:url,:category,:interval,:timeout,:expected_code,:enabled,'2026-01-01')""", data).lastrowid

    def rows(self, query, values=()):
        with self.db.connect() as conn:
            return [dict(row) for row in conn.execute(query, values)]

    def record(self, service_id, ok=True, **extra):
        self.db.record(service_id, {"ok": ok, "response_ms": 12.5,
            "status_code": 200 if ok else 503, "error": None if ok else "HTTP 503", **extra})

    def request(self, path, method="GET", data=None, headers=None, raw=None):
        if self.server is None:
            self.server = Server(("127.0.0.1", 0), make_handler(self.db, self.monitor))
            self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
            self.thread.start()
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request(method, path, body, {"Content-Type": "application/json", **(headers or {})})
            response = conn.getresponse()
            content = response.read()
            result = json.loads(content) if "json" in response.getheader("Content-Type", "") else content
            return response.status, result, dict(response.getheaders())
        finally:
            conn.close()

    def test_001(self):
        monitor = Monitor(self.db)
        service = {"id": 1}
        monitor.running.add(1)
        try:
            with patch("monitor.checker.probe", return_value={}), patch.object(self.db, "record"), patch.object(self.db, "connect", side_effect=sqlite3.OperationalError("disk full")):
                with self.assertRaises(sqlite3.OperationalError):
                    monitor.run(service)
            self.assertNotIn(1, monitor.running)
        finally:
            monitor.pool.shutdown(wait=True)

    def test_002(self):
        with self.assertRaises(APIError) as error:
            validate([])
        self.assertEqual(error.exception.status, 400)

    def test_003(self):
        with self.assertRaises(APIError) as error:
            validate('abc')
        self.assertEqual(error.exception.status, 400)

    def test_004(self):
        with self.assertRaises(APIError) as error:
            validate(42)
        self.assertEqual(error.exception.status, 400)

    def test_005(self):
        with self.assertRaises(APIError) as error:
            validate(True)
        self.assertEqual(error.exception.status, 400)

    def test_006(self):
        data = {"name": "API", "url": "https://example.test"}
        del data['name']
        with self.assertRaises(APIError):
            validate(data)

    def test_007(self):
        data = {"name": "API", "url": "https://example.test"}
        del data['url']
        with self.assertRaises(APIError):
            validate(data)

    def test_008(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'name': ' '})

    def test_009(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'name': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'})

    def test_010(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'category': ''})

    def test_011(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'category': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'})

    def test_012(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'name': 5})

    def test_013(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'category': []})

    def test_014(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'url': None})

    def test_015(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'url': 'https://example.test/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'})

    def test_016(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'ftp://example.test'})

    def test_017(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'file:///tmp/key'})

    def test_018(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'https://user:password@example.test'})

    def test_019(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'https://user@example.test'})

    def test_020(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'https://example.test/#section'})

    def test_021(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'http://example.test:70000'})

    def test_022(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'http://example.test:abc'})

    def test_023(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'https://'})

    def test_024(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'https://пример.рф'})

    def test_025(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": 'https://example.test/a b'})

    def test_026(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'interval': 9})

    def test_027(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'interval': 86401})

    def test_028(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'timeout': 0})

    def test_029(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'timeout': 61})

    def test_030(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'expected_code': 99})

    def test_031(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'expected_code': 600})

    def test_032(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'interval': True})

    def test_033(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'timeout': 1.5})

    def test_034(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'expected_code': '200'})

    def test_035(self):
        with self.assertRaises(APIError):
            validate({"name": "API", "url": "https://example.test", 'enabled': 'false'})

    def test_036(self):
        data = validate({"name": "x"*100, "url": "http://[::1]:8080/health", "category": "x"*50,
            "interval": 10, "timeout": 60, "expected_code": 599, "enabled": False})
        self.assertEqual((data["interval"], data["timeout"], data["expected_code"], data["enabled"]), (10, 60, 599, 0))

    def test_037(self):
        data = validate({"name": " API ", "url": " https://example.test ", "category": " Backend "})
        self.assertEqual((data["name"], data["url"], data["category"]), ("API", "https://example.test", "Backend"))

    def test_038(self):
        data = validate({"name": "API", "url": "https://example.test"})
        self.assertEqual((data["interval"], data["timeout"], data["expected_code"], data["enabled"]), (60, 5, 200, 1))

    def test_039(self):
        url = "https://xn--e1afmkfd.xn--p1ai/health?ready=1"
        self.assertEqual(validate({"name": "API", "url": url})["url"], url)

    def test_040(self):
        data = validate({"name": "API", "url": "http://localhost", "interval": 86400, "timeout": 1, "expected_code": 100})
        self.assertEqual((data["interval"], data["timeout"], data["expected_code"]), (86400, 1, 100))

    def test_041(self):
        status, body, _ = self.request("/api/health")
        self.assertEqual((status, body), (200, {"status": "ok"}))

    def test_042(self):
        self.assertEqual(self.request("/api/services")[:2], (200, []))

    def test_043(self):
        status, body, _ = self.request("/api/services", "POST", {"name": "API", "url": "https://example.test"})
        self.assertEqual(status, 201)
        self.assertEqual(self.db.service(body["id"])["name"], "API")

    def test_044(self):
        sid = self.add(category="Backend")
        status, body, _ = self.request(f"/api/services/{sid}")
        self.assertEqual((status, body["category"], body["timeout"]), (200, "Backend", 5))

    def test_045(self):
        self.assertEqual(self.request('/api/services/9999')[0], 404)

    def test_046(self):
        self.assertEqual(self.request('/api/services/not-a-number')[0], 404)

    def test_047(self):
        self.assertEqual(self.request('/api/services/-1/history')[0], 404)

    def test_048(self):
        self.assertEqual(self.request('/api/missing')[0], 404)

    def test_049(self):
        self.assertEqual(self.request("/api/services?hours=0")[0], 400)

    def test_050(self):
        self.assertEqual(self.request("/api/services?hours=721")[0], 400)

    def test_051(self):
        self.assertEqual(self.request("/api/services?hours=abc")[0], 400)

    def test_052(self):
        self.assertEqual(self.request("/api/services?hours=1.5")[0], 400)

    def test_053(self):
        self.assertEqual(self.request("/api/services?hours=720")[0], 200)

    def test_054(self):
        self.assertEqual(self.request("/api/services", "POST", {}, {"Origin": "https://other.test"})[0], 403)
        self.assertEqual(self.rows("SELECT * FROM services"), [])

    def test_055(self):
        self.assertEqual(self.request("/api/services", "POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, raw=b"name=API")[0], 415)

    def test_056(self):
        self.assertEqual(self.request("/api/services", "POST", raw=b'{broken')[0], 400)
        self.assertEqual(self.rows("SELECT * FROM services"), [])

    def test_057(self):
        self.assertEqual(self.request("/api/services", "POST", raw=b" "*16385)[0], 400)

    def test_058(self):
        self.assertEqual(self.request("/api/services", "POST", [1, 2])[0], 400)

    def test_059(self):
        sid = self.add()
        with self.db.connect() as conn:
            conn.execute("UPDATE services SET next_check=9999999999 WHERE id=?", (sid,))
        self.assertEqual(self.request(f"/api/services/{sid}", "PUT", {"name": "Изменён", "url": "https://new.test"})[0], 200)
        self.assertEqual(self.db.service(sid)["next_check"], 0)

    def test_060(self):
        sid = self.add()
        self.assertEqual(self.request(f"/api/services/{sid}", "PUT", {"name": ""})[0], 400)
        self.assertEqual(self.db.service(sid)["name"], "Сервис")

    def test_061(self):
        sid = self.add()
        self.assertEqual(self.request(f"/api/services/{sid}/check", "POST", {})[0], 202)
        self.monitor.submit.assert_called_once()
        self.assertEqual(self.monitor.submit.call_args.args[0]["id"], sid)

    def test_062(self):
        sid = self.add()
        self.monitor.submit.return_value = False
        self.assertEqual(self.request(f"/api/services/{sid}/check", "POST", {})[0], 409)

    def test_063(self):
        self.add()
        service = self.request("/api/services")[1][0]
        self.assertEqual((service["status"], service["uptime"], service["total"]), ("pending", None, 0))

    def test_064(self):
        self.record(self.add())
        self.assertEqual(self.request("/api/services")[1][0]["status"], "up")

    def test_065(self):
        self.record(self.add(), False)
        self.assertEqual(self.request("/api/services")[1][0]["status"], "down")

    def test_066(self):
        self.record(self.add(enabled=False), False)
        self.assertEqual(self.request("/api/services?status=paused")[1][0]["status"], "paused")

    def test_067(self):
        self.add(url="https://Backend.example.test")
        self.add(url="https://other.test")
        self.assertEqual(len(self.request("/api/services?q=BACKEND")[1]), 1)

    def test_068(self):
        self.add(category="Backend")
        self.add(category="Frontend")
        self.assertEqual([s["category"] for s in self.request("/api/services?category=Backend")[1]], ["Backend"])

    def test_069(self):
        sid = self.add()
        for ok in (True, False, True):
            self.record(sid, ok)
        service = self.request("/api/services")[1][0]
        self.assertEqual((service["total"], service["successful"], service["uptime"]), (3, 2, 66.67))

    def test_070(self):
        sid = self.add()
        self.record(sid, response_ms=10)
        self.record(sid, response_ms=30)
        self.assertEqual(self.request("/api/services")[1][0]["avg_ms"], 20)

    def test_071(self):
        sid = self.add()
        self.record(sid)
        self.record(self.add(), False)
        history = self.request(f"/api/services/{sid}/history")[1]
        self.assertEqual([c["service_id"] for c in history["checks"]], [sid])
        self.assertEqual(history["incidents"], [])

    def test_072(self):
        sid = self.add()
        with self.db.connect() as conn:
            conn.executemany("INSERT INTO checks(service_id,checked_at,ok,response_ms) VALUES(?,?,1,1)",
                [(sid, "2099-01-01T00:00:00+00:00")]*505)
        self.assertEqual(len(self.request(f"/api/services/{sid}/history")[1]["checks"]), 500)

    def test_073(self):
        status, body, headers = self.request("/api/report.csv")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_074(self):
        _, _, headers = self.request("/api/health")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_075(self):
        self.assertEqual(self.request("/../monitor/database.py")[0], 404)

    def test_076(self):
        self.record(123456, False)
        self.assertEqual(self.rows("SELECT * FROM checks"), [])
        self.assertEqual(self.rows("SELECT * FROM incidents"), [])

    def test_077(self):
        sid = self.add()
        self.record(sid, False)
        rows = self.rows("SELECT * FROM incidents")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["resolved_at"])

    def test_078(self):
        sid = self.add()
        for _ in range(5):
            self.record(sid, False)
        self.assertEqual(len(self.rows("SELECT * FROM incidents")), 1)
        self.assertEqual(len(self.rows("SELECT * FROM checks")), 5)

    def test_079(self):
        sid = self.add()
        self.record(sid, False)
        self.record(sid)
        self.assertIsNotNone(self.rows("SELECT * FROM incidents")[0]["resolved_at"])

    def test_080(self):
        sid = self.add()
        for _ in range(3):
            self.record(sid)
        self.assertEqual(self.rows("SELECT * FROM incidents"), [])

    def test_081(self):
        sid = self.add()
        for ok in (False, True, False):
            self.record(sid, ok)
        rows = self.rows("SELECT * FROM incidents ORDER BY id")
        self.assertEqual(len(rows), 2)
        self.assertIsNotNone(rows[0]["resolved_at"])
        self.assertIsNone(rows[1]["resolved_at"])

    def test_082(self):
        first, second = self.add(), self.add()
        self.record(first, False)
        self.record(second, False)
        self.record(first)
        self.assertIsNone(self.rows("SELECT * FROM incidents WHERE service_id=?", (second,))[0]["resolved_at"])

    def test_083(self):
        sid = self.add()
        self.record(sid, False, error="DNS failure")
        self.record(sid, False, error="Timeout")
        self.assertEqual(self.rows("SELECT * FROM incidents")[0]["reason"], "DNS failure")

    def test_084(self):
        self.record(self.add(), False, error=None)
        self.assertTrue(self.rows("SELECT * FROM incidents")[0]["reason"])

    def test_085(self):
        self.record(self.add(), False, status_code=None, error="Timeout")
        row = self.rows("SELECT * FROM checks")[0]
        self.assertIsNone(row["status_code"])
        self.assertEqual(row["error"], "Timeout")

    def test_086(self):
        self.record(self.add(), response_ms=0.125)
        self.assertEqual(self.rows("SELECT * FROM checks")[0]["response_ms"], .125)

    def test_087(self):
        sid = self.add()
        self.record(sid, False)
        reopened = Database(self.db.path)
        self.assertEqual(reopened.service(sid)["name"], "Сервис")
        with reopened.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM checks").fetchone()[0], 1)

    def test_088(self):
        sid = self.add()
        with self.assertRaises(RuntimeError):
            with self.db.connect() as conn:
                conn.execute("UPDATE services SET name='Повреждён' WHERE id=?", (sid,))
                raise RuntimeError("rollback")
        self.assertEqual(self.db.service(sid)["name"], "Сервис")

    def test_089(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect() as conn:
                conn.execute("INSERT INTO checks(service_id,checked_at,ok,response_ms) VALUES(999,'2026',1,1)")

    def test_090(self):
        sid = self.add()
        self.record(sid, False)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM services WHERE id=?", (sid,))
        self.assertEqual(self.rows("SELECT * FROM checks"), [])
        self.assertEqual(self.rows("SELECT * FROM incidents"), [])

    def test_091(self):
        first, second = self.add(), self.add()
        self.record(first)
        self.record(second, False)
        self.request(f"/api/services/{first}", "DELETE")
        self.assertEqual([r["service_id"] for r in self.rows("SELECT * FROM checks")], [second])

    def test_092(self):
        self.add(name='=SUM(1)')
        body = self.request("/api/report.csv")[1]
        rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig")), delimiter=";"))
        self.assertTrue(rows[1][0].startswith("'" + '='))

    def test_093(self):
        self.add(name='+SUM(1)')
        body = self.request("/api/report.csv")[1]
        rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig")), delimiter=";"))
        self.assertTrue(rows[1][0].startswith("'" + '+'))

    def test_094(self):
        self.add(name='-SUM(1)')
        body = self.request("/api/report.csv")[1]
        rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig")), delimiter=";"))
        self.assertTrue(rows[1][0].startswith("'" + '-'))

    def test_095(self):
        self.add(name='@SUM(1)')
        body = self.request("/api/report.csv")[1]
        rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig")), delimiter=";"))
        self.assertTrue(rows[1][0].startswith("'" + '@'))

    def test_096(self):
        self.add(name='Сервис; "API"')
        rows = list(csv.reader(io.StringIO(self.request("/api/report.csv")[1].decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[1][0], 'Сервис; "API"')

    def test_097(self):
        sid = self.add()
        self.record(sid)
        with self.db.connect() as conn:
            conn.execute("INSERT INTO checks(service_id,checked_at,ok,response_ms) VALUES(?,'2000-01-01',0,999)", (sid,))
        row = self.request("/api/services?hours=1")[1][0]
        self.assertEqual((row["total"], row["uptime"]), (1, 100))

    def test_098(self):
        sid = self.add()
        with self.db.connect() as conn:
            conn.execute("INSERT INTO incidents(service_id,started_at,reason) VALUES(?,'2000-01-01','old failure')", (sid,))
        self.assertEqual(len(self.request(f"/api/services/{sid}/history?hours=1")[1]["incidents"]), 1)

