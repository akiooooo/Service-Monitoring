import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Основные',
                    interval INTEGER NOT NULL CHECK(interval BETWEEN 10 AND 86400),
                    timeout INTEGER NOT NULL CHECK(timeout BETWEEN 1 AND 60),
                    expected_code INTEGER NOT NULL CHECK(expected_code BETWEEN 100 AND 599),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, next_check REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY,
                    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
                    checked_at TEXT NOT NULL, ok INTEGER NOT NULL,
                    response_ms REAL NOT NULL, status_code INTEGER, error TEXT
                );
                CREATE INDEX IF NOT EXISTS checks_service_time ON checks(service_id, checked_at DESC);
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY,
                    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
                    started_at TEXT NOT NULL, resolved_at TEXT, reason TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_open_incident
                    ON incidents(service_id) WHERE resolved_at IS NULL;
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def service(self, service_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
            return dict(row) if row else None

    def record(self, service_id, result):
        timestamp = now()
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM services WHERE id=?", (service_id,)).fetchone():
                return False
            db.execute("""INSERT INTO checks(service_id, checked_at, ok, response_ms, status_code, error)
                          VALUES (?, ?, ?, ?, ?, ?)""", (service_id, timestamp, int(result["ok"]),
                          result["response_ms"], result["status_code"], result["error"]))
            if result["ok"]:
                incident = db.execute("UPDATE incidents SET resolved_at=? WHERE service_id=? AND resolved_at IS NULL",
                                      (timestamp, service_id))
            else:
                incident = db.execute("INSERT OR IGNORE INTO incidents(service_id, started_at, reason) VALUES (?, ?, ?)",
                                      (service_id, timestamp, result["error"] or "Неожиданный HTTP-код"))
            return incident.rowcount == 1
