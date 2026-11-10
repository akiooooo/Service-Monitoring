import socket
import logging
import ssl
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(service):
    started = time.perf_counter()
    code, error = None, None
    try:
        # Проверяем сам URL: редирект может скрывать сбой нужного endpoint.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(service["url"], headers={"User-Agent": "PulseMonitor/1.0"})
        with opener.open(request, timeout=service["timeout"]) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
    except (TimeoutError, socket.timeout):
        error = "Превышено время ожидания"
    except urllib.error.URLError as exc:
        error = f"Ошибка соединения: {exc.reason}"
    except (OSError, ssl.SSLError, ValueError) as exc:
        error = f"Ошибка запроса: {exc}"
    ok = code == service["expected_code"] and error is None
    if code is not None and not ok:
        error = f"HTTP {code}, ожидался {service['expected_code']}"
    return {"ok": ok, "status_code": code, "error": error,
            "response_ms": round((time.perf_counter() - started) * 1000, 1)}


class Monitor:
    def __init__(self, database):
        self.db = database
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.running = set()
        self.pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="probe")
        self.thread = threading.Thread(target=self.loop, daemon=True, name="scheduler")

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()
        self.pool.shutdown(wait=True)

    def submit(self, service):
        with self.lock:
            if service["id"] in self.running:
                return False
            self.running.add(service["id"])
        try:
            self.pool.submit(self.run, service)
        except RuntimeError:
            with self.lock:
                self.running.discard(service["id"])
            return False
        return True

    def run(self, service):
        try:
            result = probe(service)
            self.db.record(service["id"], result)
        except Exception:
            logging.exception("Не удалось сохранить проверку сервиса %s", service["id"])
        finally:
            try:
                with self.db.connect() as db:
                    db.execute("UPDATE services SET next_check=?+interval WHERE id=?",
                               (time.time(), service["id"]))
            finally:
                with self.lock:
                    self.running.discard(service["id"])

    def loop(self):
        while not self.stop_event.is_set():
            with self.db.connect() as db:
                rows = db.execute("SELECT * FROM services WHERE enabled=1 AND next_check<=?",
                                  (time.time(),)).fetchall()
            for row in rows:
                self.submit(dict(row))
            self.stop_event.wait(1)
