import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch
from urllib.parse import parse_qs

from monitor.checker import Monitor
from monitor.database import Database, now
from monitor.notifications import load_notifier, send_email, send_vk


class NotificationTests(unittest.TestCase):
    def test_monitor_notifies_only_when_incident_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "pulse.db")
            with database.connect() as db:
                service_id = db.execute("""INSERT INTO services
                    (name, url, interval, timeout, expected_code, created_at)
                    VALUES ('Сервис', 'https://example.test', 10, 3, 200, ?)""", (now(),)).lastrowid
            service = database.service(service_id)
            notify = Mock()
            monitor = Monitor(database, notify)
            failure = {"ok": False, "error": "HTTP 503", "status_code": 503, "response_ms": 10}
            success = {"ok": True, "error": None, "status_code": 200, "response_ms": 10}
            try:
                with patch("monitor.checker.probe", side_effect=[success, failure, failure, success, success]):
                    for _ in range(5):
                        monitor.run(service)
            finally:
                monitor.pool.shutdown(wait=True)
                monitor.notifications.shutdown(wait=True)
            self.assertEqual(notify.call_args_list, [call(service, failure), call(service, success)])

    def test_vk_posts_message_and_checks_api_response(self):
        with patch("monitor.notifications.urlopen", return_value=io.BytesIO(b'{"response": 12}')) as open_url:
            send_vk("test-token", "42", "Сбой", "Сервис недоступен")
        self.assertEqual(open_url.call_args.args, ("https://api.vk.com/method/messages.send",))
        fields = parse_qs(open_url.call_args.kwargs["data"].decode())
        self.assertEqual(fields["access_token"], ["test-token"])
        self.assertEqual(fields["peer_id"], ["42"])
        self.assertEqual(fields["message"], ["Сбой\nСервис недоступен"])
        self.assertGreater(int(fields["random_id"][0]), 0)

        with patch("monitor.notifications.urlopen", return_value=io.BytesIO(b'{"error": {"error_code": 15}}')):
            with self.assertRaises(RuntimeError):
                send_vk("test-token", "42", "Сбой", "Сервис недоступен")

    def test_smtp_uses_tls_before_login(self):
        for port, constructor in [(465, "SMTP_SSL"), (587, "SMTP")]:
            with self.subTest(port=port), patch(f"monitor.notifications.smtplib.{constructor}") as connect:
                send_email("smtp.example.test", port, "user", "password",
                           "from@example.test", "to@example.test", "Сбой", "Сервис недоступен")
                smtp = connect.return_value.__enter__.return_value
                methods = [action[0] for action in smtp.method_calls]
                self.assertEqual(methods, ["login", "send_message"] if port == 465 else
                                 ["starttls", "login", "send_message"])
                smtp.login.assert_called_once_with("user", "password")
                message = smtp.send_message.call_args.args[0]
                self.assertEqual(message["From"], "from@example.test")
                self.assertEqual(message["To"], "to@example.test")
                self.assertEqual(message["Subject"], "Сбой")
                self.assertEqual(message.get_content().strip(), "Сервис недоступен")

    def test_email_is_sent_if_vk_fails(self):
        settings = {"PULSE_VK_TOKEN": "test-token", "PULSE_VK_PEER_ID": "42",
                    "PULSE_SMTP_HOST": "smtp.example.test", "PULSE_SMTP_USER": "from@example.test",
                    "PULSE_SMTP_PASSWORD": "password", "PULSE_EMAIL_TO": "to@example.test"}
        with patch.dict("os.environ", settings, clear=True), \
                patch("monitor.notifications.send_vk", side_effect=OSError("test-token")), \
                patch("monitor.notifications.send_email") as email, self.assertLogs(level="WARNING") as log:
            notify = load_notifier()
            notify({"name": "API"}, {"ok": False, "error": "HTTP 503"})
        email.assert_called_once_with("smtp.example.test", 465, "from@example.test", "password",
                                      "from@example.test", "to@example.test",
                                      "Пульс — сервис недоступен", "Сервис: API\nПричина: HTTP 503")
        self.assertNotIn("test-token", "\n".join(log.output))
