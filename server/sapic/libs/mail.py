# -*- coding: utf-8 -*-
"""Mail delivery.

Transport selection is a fixed choice, not a fallback chain: an enabled hook
declaring ``__catalog__ = "mail"`` (see :mod:`sapic.libs.ext`) owns delivery as
soon as its own readiness check passes, otherwise the built-in SMTP client is
used. Retrying the same message through the second transport would just risk
sending it twice when the first one failed halfway.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from flask import current_app, has_app_context

from ..basis.errors import ApiError, ErrorCode
from . import ext
from .hook import get_hook_manager
from .settings import get_setting

SMTP_DEFAULTS = {
    "host": "",
    "port": 25,
    "user": "",
    "password": "",
    "from": "sapic@localhost",
    "tls": False,
}

#: Ports that expect TLS from the first byte (implicit SSL). Plain ``SMTP`` on
#: them deadlocks: the server waits for a handshake while we wait for a banner,
#: so the only symptom is a connect timeout.
SSL_PORTS = frozenset({465, 994})

SMTP_TIMEOUT = 10


def smtp_config() -> dict:
    config = dict(SMTP_DEFAULTS)
    config.update(get_setting("smtp", {}) or {})
    return config


def _hook_config(name: str) -> dict:
    """Hook-wide values managed on the hooks page (``hooks_config``)."""
    saved = get_setting("hooks_config", {}) or {}
    data = saved.get(name) if isinstance(saved, dict) else None
    return dict(data) if isinstance(data, dict) else {}


def _mail_hook():
    """Enabled hook that can deliver mail: ``(name, module, config)`` or ``None``.

    A hook that declares the contract but has not been filled in yet says so
    through ``mail_ready(config)``; skipping it there keeps SMTP usable and
    stops a half-configured transport from swallowing verification mails.
    Hooks are walked in name order, so two configured transports never race.
    """
    if not has_app_context():
        return None
    hooks = get_hook_manager().hooks
    for name in sorted(hooks):
        hook = hooks[name]
        if not hook.enabled or not ext.is_mailer(hook.module):
            continue
        config = _hook_config(name)
        check = getattr(hook.module, ext.MAIL_READY_FUNC, None)
        if callable(check):
            try:
                if not check(config):
                    continue
            except Exception:
                current_app.logger.exception(
                    "mail hook %s readiness check failed", name
                )
                continue
        return name, hook.module, config
    return None


def mail_ready() -> bool:
    """Whether any transport can deliver a message right now.

    The site endpoint uses it to hide "verify email / reset password" entries,
    and the auth views use it to decide whether a token may be echoed back to a
    local client: a configured mail hook counts exactly like an SMTP host.
    """
    return _mail_hook() is not None or bool(smtp_config().get("host"))


def _deliver(to: str, subject: str, body: str) -> None:
    """Hand one message to the selected transport, raising on any failure."""
    provider = _mail_hook()
    if provider is not None:
        _, module, config = provider
        module.send_mail(config=config, to=to, subject=subject, body=body)
        return

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

    host = str(config["host"])
    port = int(config["port"])
    #: The port decides the transport: 465/994 are implicit SSL, everything
    #: else starts in plain text and upgrades only when ``tls`` is set.
    if port in SSL_PORTS:
        smtp = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT)
    else:
        smtp = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
    with smtp:
        if config.get("tls") and port not in SSL_PORTS:
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
    if not mail_ready():
        current_app.logger.warning("mail is not configured, skip mail to %s", to)
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
            "邮件测试",
            "这是一封来自 sapic 的测试邮件，收到即表示邮件配置可用。",
        )
    except ApiError:
        raise
    except Exception as exc:  # pragma: no cover - network dependent
        current_app.logger.exception("send test mail failed: %s", exc)
        raise ApiError(
            "mail delivery failed: %s" % exc, ErrorCode.SERVICE_UNAVAILABLE, 502
        ) from exc
