import json
import logging
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from functools import partial
from urllib.parse import urlencode
from urllib.request import urlopen


def send_vk(token, peer_id, subject, body):
    data = urlencode({
        "access_token": token,
        "v": "5.199",
        "peer_id": peer_id,
        "random_id": secrets.randbelow(2**31 - 1) + 1,
        "message": f"{subject}\n{body}",
    }).encode()
    with urlopen("https://api.vk.com/method/messages.send", data=data, timeout=5) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or "response" not in payload or "error" in payload:
        raise RuntimeError("VK API вернул ошибку")


def send_email(host, port, user, password, sender, recipient, subject, body):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    if port == 465:
        connection = smtplib.SMTP_SSL(host, port, timeout=5, context=context)
    else:
        connection = smtplib.SMTP(host, port, timeout=5)
    with connection as smtp:
        if port != 465:
            smtp.starttls(context=context)
        smtp.login(user, password)
        smtp.send_message(message)


def load_notifier():
    channels = {}
    token = os.getenv("PULSE_VK_TOKEN")
    peer_id = os.getenv("PULSE_VK_PEER_ID")
    if token and peer_id:
        channels["VK"] = partial(send_vk, token, peer_id)
    elif token or peer_id:
        logging.warning("Для VK нужны PULSE_VK_TOKEN и PULSE_VK_PEER_ID")

    host = os.getenv("PULSE_SMTP_HOST")
    user = os.getenv("PULSE_SMTP_USER")
    password = os.getenv("PULSE_SMTP_PASSWORD")
    recipient = os.getenv("PULSE_EMAIL_TO")
    if all((host, user, password, recipient)):
        try:
            port = int(os.getenv("PULSE_SMTP_PORT") or "465")
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            logging.warning("Укажите допустимый порт в PULSE_SMTP_PORT")
        else:
            sender = os.getenv("PULSE_EMAIL_FROM") or user
            channels["почта"] = partial(send_email, host, port, user, password, sender, recipient)
    elif any((host, user, password, recipient)):
        logging.warning("Для почты нужны PULSE_SMTP_HOST, PULSE_SMTP_USER, PULSE_SMTP_PASSWORD и PULSE_EMAIL_TO")

    if not channels:
        return None

    def notify(service, result):
        subject = "Пульс — сервис восстановился" if result["ok"] else "Пульс — сервис недоступен"
        body = f"Сервис: {service['name']}"
        if not result["ok"]:
            body += f"\nПричина: {result['error'] or 'Неожиданный HTTP-код'}"
        for name, send in channels.items():
            try:
                send(subject, body)
            except (OSError, ValueError, RuntimeError) as exc:
                logging.warning("Не удалось отправить уведомление (%s): %s", name, type(exc).__name__)

    return notify
