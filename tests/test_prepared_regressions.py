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

