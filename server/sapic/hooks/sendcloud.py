# -*- coding: utf-8 -*-
"""sendcloud — deliver mail through the SendCloud HTTP API.

The core prefers an enabled ``__catalog__ = "mail"`` hook over its built-in SMTP
client (see :mod:`sapic.libs.mail`), so this module only sends one plain-text
message: ``send_mail(config, to, subject, body)``. ``mail_ready(config)`` tells
the core whether the admin has filled in the required fields; until then SMTP
keeps working, so enabling the hook without configuring it is harmless.

Failures raise ``ValueError`` with the API message: the core logs them for
verification mail and turns them into an API error for the admin test action.
"""

from __future__ import annotations

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None

__version__ = "0.1.0"
__author__ = "staugur"
__description__ = "使用 SendCloud 发送邮件"

__catalog__ = "mail"

#: Official endpoint; ``api_url`` overrides it for private deployments.
API_URL = "https://api.sendcloud.net/apiv2/mail/send"
TIMEOUT = 10

#: (key, node type, label, hint)；``input`` 的 hint 是占位文案。
FIELDS = (
    ("api_user", "input", "API User", "SendCloud 后台「API 用户」里的 API USER"),
    ("api_key", "password", "API Key", "与 API USER 对应的 API KEY"),
    ("from", "input", "发件人地址", "已在 SendCloud 验证的发件域邮箱"),
    ("from_name", "input", "发件人名称", "可选，留空则用 SendCloud 默认"),
    ("api_url", "input", "API 地址", "留空用官方地址，私有部署可改"),
)
REQUIRED = ("api_user", "api_key", "from")
LABELS = {key: label for key, _, label, _ in FIELDS}


def hook_manifest():
    return {
        "title": "SendCloud 邮件",
        "title_key": "hooks.sendcloud.title",
        "description_key": "hooks.sendcloud.description",
        "catalog": "mail",
        "config_schema": [
            {
                "type": kind,
                "key": key,
                "label": label,
                "label_key": "hooks.sendcloud.fields.%s.label" % key,
                "placeholder": hint,
                "placeholder_key": "hooks.sendcloud.fields.%s.hint" % key,
                "required": key in REQUIRED,
            }
            for key, kind, label, hint in FIELDS
        ],
    }


def _value(config, key: str) -> str:
    return str((config or {}).get(key) or "").strip()


def mail_ready(config=None) -> bool:
    """Whether the saved config can actually deliver a message."""
    return all(_value(config, key) for key in REQUIRED)


def _is_true(value) -> bool:
    """SendCloud answers ``result`` as bool, ``"true"`` or ``1``."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _excerpt(payload) -> str:
    """Single-line body preview so the error names the failing reason."""
    return " ".join(str(payload or "").split())[:200]


def send_mail(config=None, to="", subject="", body="") -> None:
    """Deliver one plain-text message through SendCloud.

    The API takes ``plain`` for a pure-text body (``html`` is for rich mail),
    and a failed run answers HTTP 200 with ``result: false``, so both the status
    code and that flag are checked.
    """
    missing = [LABELS[key] for key in REQUIRED if not _value(config, key)]
    if missing:
        raise ValueError("sendcloud is not configured: %s" % ", ".join(missing))
    if requests is None:
        raise ValueError("Please install requests module")

    recipient = str(to or "").strip()
    if not recipient:
        raise ValueError("recipient is missing")

    payload = {
        "apiUser": _value(config, "api_user"),
        "apiKey": _value(config, "api_key"),
        "from": _value(config, "from"),
        "to": recipient,
        "subject": subject,
        "plain": body,
    }
    from_name = _value(config, "from_name")
    if from_name:
        payload["fromName"] = from_name

    url = _value(config, "api_url") or API_URL
    try:
        response = requests.post(url, data=payload, timeout=TIMEOUT)
    except Exception as exc:
        raise ValueError("sendcloud request failed: %s" % exc) from exc

    try:
        data = response.json() or {}
    except ValueError as exc:
        raise ValueError(
            "sendcloud returned HTTP %s: %s"
            % (response.status_code, _excerpt(response.text))
        ) from exc
    if response.status_code != 200 or not _is_true(data.get("result")):
        raise ValueError(
            "sendcloud rejected the message (HTTP %s): %s"
            % (
                data.get("statusCode") or response.status_code,
                data.get("message") or "unknown error",
            )
        )
