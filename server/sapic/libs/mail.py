# -*- coding: utf-8 -*-
"""SMTP mail delivery."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from flask import current_app

from ..basis.errors import ApiError, ErrorCode
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


def smtp_ready() -> bool:
    """Whether a mail server is configured; without ``host`` mail is skipped."""
    return bool(smtp_config().get("host"))


def _deliver(to: str, subject: str, body: str) -> None:
    """Hand one message to the mail server, raising on any failure."""
    config = smtp_config()
    if not config.get("host"):
        raise ApiError(
            "mail service is not configured", ErrorCode.SERVICE_UNAVAILABLE, 503
        )

    message = EmailMessage()
    message["From"] = config["from"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(config["host"], int(config["port"]), timeout=10) as smtp:
        if config.get("tls"):
            smtp.starttls()
        if config.get("user"):
            smtp.login(config["user"], config.get("password", ""))
        smtp.send_message(message)


def send_mail(to: str, subject: str, body: str) -> bool:
    """Send a plain-text mail. Returns ``False`` when it cannot be delivered.

    Verification codes and password-reset links must not break the request they
    belong to, so failures are only logged here; the admin test action uses
    :func:`send_test_mail` when the caller needs to see the reason.
    """
    if not smtp_ready():
        current_app.logger.warning("SMTP is not configured, skip mail to %s", to)
        return False
    try:
        _deliver(to, subject, body)
    except Exception as exc:  # pragma: no cover - network dependent
        current_app.logger.exception("send mail failed: %s", exc)
        return False
    return True


def send_test_mail(to: str) -> None:
    """Send a probe message, turning delivery failures into API errors."""
    try:
        _deliver(
            to,
            "SMTP 测试邮件",
            "这是一封来自 sapic 的测试邮件，收到即表示邮件配置可用。",
        )
    except ApiError:
        raise
    except Exception as exc:  # pragma: no cover - network dependent
        current_app.logger.exception("send test mail failed: %s", exc)
        raise ApiError(
            "mail delivery failed: %s" % exc, ErrorCode.SERVICE_UNAVAILABLE, 502
        ) from exc
