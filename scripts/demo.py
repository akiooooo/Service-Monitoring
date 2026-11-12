"""локальные HTTP-ресурсы для демонстрации реальных проверок"""
import argparse
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor.database import Database, now


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        code = 200
        if self.path == "/slow":
            time.sleep(.6)
        elif self.path == "/fail":
            code = 503
        elif self.path == "/unstable":
            code = 503 if int(time.time()) % 60 < 30 else 200
        elif self.path != "/ok":
            code = 404
        body = f"Demo service: HTTP {code}\n".encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="Демо-стенд Пульса")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--seed", action="store_true", help="Добавить четыре демо-сервиса в базу")
    parser.add_argument("--db", default=str(ROOT / "data" / "pulse.db"))
    args = parser.parse_args()
    if args.seed:
        database = Database(args.db)
        with database.connect() as db:
            for name, endpoint in (("API магазина", "ok"), ("Платёжный шлюз", "fail"),
                                   ("Каталог товаров", "slow"), ("Сервис уведомлений", "unstable")):
                url = f"http://127.0.0.1:{args.port}/{endpoint}"
                if not db.execute("SELECT 1 FROM services WHERE url=?", (url,)).fetchone():
                    db.execute("""INSERT INTO services(name,url,category,interval,timeout,expected_code,created_at)
                        VALUES (?,?,'Демо',10,3,200,?)""", (name, url, now()))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    print(f"Demo: http://127.0.0.1:{args.port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
