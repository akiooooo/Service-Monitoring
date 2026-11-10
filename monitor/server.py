import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .database import now

STATIC = Path(__file__).parent / "static"
log = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def validate(data):
    if not isinstance(data, dict):
        raise APIError(400, "Ожидался JSON-объект")
    result = {}
    for key, maximum in (("name", 100), ("url", 2000), ("category", 50)):
        value = data.get(key, "Основные" if key == "category" else "")
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise APIError(400, f"Поле {key}: от 1 до {maximum} символов")
        result[key] = value.strip()
    try:
        url = urlsplit(result["url"])
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError()
        if url.fragment or any(c.isspace() or ord(c) < 32 for c in result["url"]):
            raise ValueError()
        url.port
        result["url"].encode("ascii")
    except (ValueError, UnicodeError):
        raise APIError(400, "Укажите HTTP(S) URL без пароля, пробелов и фрагмента; домен — в punycode")
    for key, default, low, high in (("interval", 60, 10, 86400), ("timeout", 5, 1, 60),
                                     ("expected_code", 200, 100, 599)):
        value = data.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise APIError(400, f"Поле {key}: целое число от {low} до {high}")
        result[key] = value
    if type(data.get("enabled", True)) is not bool:
        raise APIError(400, "enabled должен быть true или false")
    result["enabled"] = int(data.get("enabled", True))
    return result


def make_handler(database, monitor):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.info(fmt, *args)

        def send(self, status, body, content_type="application/json; charset=utf-8", attachment=None):
            if content_type.startswith("application/json"):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 16384:
                    raise ValueError()
                return json.loads(self.rfile.read(size))
            except (ValueError, UnicodeError):
                raise APIError(400, "Некорректный JSON или размер запроса")

        def dispatch(self):
            # Запись доступна только с нашего origin, без кросс-сайтовых форм.
            origin = self.headers.get("Origin")
            if self.command != "GET" and origin and origin != f"http://{self.headers.get('Host')}":
                raise APIError(403, "Чужой origin запрещён")
            if self.command in ("POST", "PUT") and not self.headers.get("Content-Type", "").startswith("application/json"):
                raise APIError(415, "Используйте application/json")
            parsed = urlsplit(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            if not path.startswith("/api/"):
                files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                         "/style.css": ("style.css", "text/css")}
                if self.command != "GET" or path not in files:
                    raise APIError(404, "Страница не найдена")
                filename, mime = files[path]
                return self.send(200, (STATIC / filename).read_bytes(), mime + "; charset=utf-8")
            if path == "/api/health" and self.command == "GET":
                return self.send(200, {"status": "ok"})
            try:
                hours = int(query.get("hours", ["24"])[0])
                if not 1 <= hours <= 720:
                    raise ValueError()
            except ValueError:
                raise APIError(400, "Период: от 1 до 720 часов")
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="milliseconds")
            parts = path.split("/")
            service_id = None
            if len(parts) >= 4 and parts[2] == "services":
                try:
                    service_id = int(parts[3])
                except ValueError:
                    raise APIError(404, "Сервис не найден")
                if not database.service(service_id):
                    raise APIError(404, "Сервис не найден")
            with database.connect() as db:
                if service_id is not None and len(parts) == 4 and self.command == "GET":
                    return self.send(200, database.service(service_id))
                if path == "/api/services" and self.command == "POST":
                    data = validate(self.body())
                    cursor = db.execute("""INSERT INTO services(name,url,category,interval,timeout,expected_code,enabled,created_at)
                        VALUES (:name,:url,:category,:interval,:timeout,:expected_code,:enabled,:created_at)""",
                        {**data, "created_at": now()})
                    db.commit()
                    return self.send(201, {"id": cursor.lastrowid})
                if service_id is not None and len(parts) == 4 and self.command == "PUT":
                    data = validate(self.body())
                    db.execute("""UPDATE services SET name=:name,url=:url,category=:category,interval=:interval,
                        timeout=:timeout,expected_code=:expected_code,enabled=:enabled,next_check=0 WHERE id=:id""",
                        {**data, "id": service_id})
                    db.commit()
                    return self.send(200, {"ok": True})
                if service_id is not None and len(parts) == 4 and self.command == "DELETE":
                    db.execute("DELETE FROM services WHERE id=?", (service_id,))
                    db.commit()
                    return self.send(200, {"ok": True})
                if service_id is not None and parts[4:] == ["check"] and self.command == "POST":
                    submitted = monitor.submit(database.service(service_id))
                    return self.send(202 if submitted else 409, {"message": "Проверка запущена" if submitted else "Проверка уже выполняется"})
                if path == "/api/services" and self.command == "GET":
                    rows = db.execute("""SELECT s.*, c.ok, c.checked_at, c.response_ms, c.status_code, c.error,
                        (SELECT COUNT(*) FROM checks WHERE service_id=s.id AND checked_at>=?) AS total,
                        (SELECT SUM(ok) FROM checks WHERE service_id=s.id AND checked_at>=?) AS successful,
                        (SELECT AVG(response_ms) FROM checks WHERE service_id=s.id AND checked_at>=?) AS avg_ms
                        FROM services s LEFT JOIN checks c ON c.id=(SELECT id FROM checks WHERE service_id=s.id
                        ORDER BY checked_at DESC, id DESC LIMIT 1) ORDER BY s.created_at DESC, s.id DESC""",
                        (since, since, since)).fetchall()
                    services = []
                    for row in rows:
                        item = dict(row)
                        item["status"] = "paused" if not item["enabled"] else ("pending" if item["ok"] is None else "up" if item["ok"] else "down")
                        item["uptime"] = round(100 * (item["successful"] or 0) / item["total"], 2) if item["total"] else None
                        services.append(item)
                    search = query.get("q", [""])[0].casefold()
                    status = query.get("status", [""])[0]
                    category = query.get("category", [""])[0]
                    return self.send(200, [s for s in services if search in (s["name"] + " " + s["url"]).casefold()
                        and (not status or s["status"] == status) and (not category or s["category"] == category)])
                if service_id is not None and self.command == "GET" and parts[4:] == ["history"]:
                    checks = db.execute("SELECT * FROM checks WHERE service_id=? AND checked_at>=? ORDER BY checked_at DESC,id DESC LIMIT 500",
                                        (service_id, since)).fetchall()
                    incidents = db.execute("SELECT * FROM incidents WHERE service_id=? AND (resolved_at IS NULL OR resolved_at>=?) ORDER BY id DESC LIMIT 100",
                                           (service_id, since)).fetchall()
                    return self.send(200, {"checks": [dict(r) for r in checks], "incidents": [dict(r) for r in incidents]})
                if path == "/api/report.csv" and self.command == "GET":
                    output = io.StringIO(newline="")
                    writer = csv.writer(output, delimiter=";")
                    writer.writerow(["Сервис", "URL", "Проверок", "Успешных", "Доступность, %", "Средний отклик, мс", "Период, ч"])
                    rows = db.execute("""SELECT s.name,s.url,COUNT(c.id) total,COALESCE(SUM(c.ok),0) successful,
                        AVG(c.response_ms) avg_ms FROM services s LEFT JOIN checks c ON c.service_id=s.id
                        AND c.checked_at>=? GROUP BY s.id ORDER BY s.name""", (since,)).fetchall()
                    for r in rows:
                        # Excel не должен выполнять формулы из пользовательского названия.
                        safe = lambda value: "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
                        writer.writerow([safe(r["name"]), safe(r["url"]), r["total"], r["successful"],
                            round(100*r["successful"]/r["total"], 2) if r["total"] else "", round(r["avg_ms"], 1) if r["avg_ms"] is not None else "", hours])
                    return self.send(200, output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "pulse-report.csv")
            raise APIError(404, "Маршрут не найден")

        def handle_request(self):
            try:
                self.dispatch()
            except APIError as exc:
                self.send(exc.status, {"error": exc.message})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                log.exception("Ошибка обработки запроса")
                self.send(500, {"error": "Внутренняя ошибка сервера"})

        do_GET = do_POST = do_PUT = do_DELETE = handle_request
    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address
