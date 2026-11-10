import argparse
import logging
import os
from pathlib import Path

from monitor.checker import Monitor
from monitor.database import Database
from monitor.server import Server, make_handler


def main():
    parser = argparse.ArgumentParser(description="Пульс — мониторинг доступности сервисов")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=os.environ.get("PULSE_DB", str(Path(__file__).parent / "data" / "pulse.db")))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    database = Database(args.db)
    monitor = Monitor(database)
    server = Server((args.host, args.port), make_handler(database, monitor))
    monitor.start()
    print(f"Пульс запущен: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        monitor.stop()


if __name__ == "__main__":
    main()
