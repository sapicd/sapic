# -*- coding: utf-8 -*-
"""SMTP mail delivery."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from flask import current_app

from .settings import get_setting

SMTP_DEFAULTS = {
    "host": "",
    "port": 25,
    "user": "",
    "password": "",
    "from": "sapic@localhost",
    "tls": False,
}


def smtp_config() -> dict:
    config = dict(SMTP_DEFAULTS)
    config.update(get_setting("smtp", {}) or {})
    return config


def send_mail(to: str, subject: str, body: str) -> bool:
    """Send a plain-text mail. Returns ``False`` when SMTP is not configured."""
    config = smtp_config()
    if not config.get("host"):
        current_app.logger.warning(
            "SMTP is not configured, skip mail to %s", to
        )
        return False

    message = EmailMessage()
    message["From"] = config["from"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(
            config["host"], int(config["port"]), timeout=10
        ) as smtp:
            if config.get("tls"):
                smtp.starttls()
            if config.get("user"):
                smtp.login(config["user"], config.get("password", ""))
            smtp.send_message(message)
    except Exception as exc:  # pragma: no cover - network dependent
        current_app.logger.exception("send mail failed: %s", exc)
        return False
    return True
