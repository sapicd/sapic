# -*- coding: utf-8 -*-
"""Site settings API (admin only)."""

from __future__ import annotations

from flask import Blueprint, g, request

from ..basis.common import as_bool
from ..basis.errors import ApiError, ErrorCode
from ..libs import release
from ..libs.auth import admin_required
from ..libs.mail import SMTP_DEFAULTS, send_test_mail, smtp_ready
from ..libs.settings import DEFAULTS, get_setting, set_setting
from ..utils.common import parse_proxy_url
from ..utils.web import ok

bp = Blueprint("settings", __name__)

#: 前端把这个占位符原样回传时表示「密码没改」，服务端保留库里的旧值；
#: 读取设置时也用它替换真实密码，密钥永远不会出现在响应里。
SMTP_PASSWORD_MASK = "********"

_SMTP_FIELDS = {"host", "port", "user", "password", "from", "tls"}

#: Editable string settings.
_STR_KEYS = {
    "external_base_url",
    "forbidden_username",
    "login_notice",
    "site_announcement",
    "site_background",
    "site_background_mobile",
    "site_description",
    "site_footer",
    "site_icp",
    "site_keywords",
    "site_logo",
    "site_name",
    "upload_allowed_ext",
    "upload_fetch_proxy",
    "upload_notice",
}

#: 代理地址长度上限，与其它字符串设置保持一致。
MAX_PROXY_LENGTH = 500

#: Integer settings and their inclusive bounds.
_INT_KEYS = {
    "upload_count_limit": (1, 100),
    "upload_image_max_size": (1, 1024),
    "upload_video_max_size": (1, 1024),
    "user_backend_limit": (1, 20),
    #: 0 表示不启用（永久 / 不限制上限）。
    "image_expire_default_days": (0, 3650),
    "image_expire_max_days": (0, 3650),
}

_BOOL_KEYS = {
    "allow_anonymous_upload",
    "allow_register",
    "allow_user_backends",
    "allow_video",
    "password_login",
    "plaza_enabled",
    "storage_replica",
    "register_review",
    "upload_enabled",
}

_FLOAT_KEYS = {"site_background_opacity": (0.0, 1.0)}

#: Keys the admin UI may write; everything else in ``DEFAULTS`` is internal.
EDITABLE_KEYS = sorted(
    _STR_KEYS | set(_INT_KEYS) | _BOOL_KEYS | set(_FLOAT_KEYS) | {"smtp"}
)


def _smtp_payload() -> dict:
    """SMTP config with the password replaced by a mask."""
    config = dict(SMTP_DEFAULTS)
    config.update(get_setting("smtp", {}) or {})
    config["password"] = SMTP_PASSWORD_MASK if config.get("password") else ""
    return config


def _payload_of_settings() -> dict:
    items = {key: get_setting(key) for key in DEFAULTS}
    items["smtp"] = _smtp_payload()
    return {"items": items, "editable": EDITABLE_KEYS}


def _clean_proxy(value: str) -> str:
    """Accept ``http(s)://[user:pass@]host[:port]``; empty disables the proxy."""
    try:
        return parse_proxy_url(value)[:MAX_PROXY_LENGTH]
    except ValueError as exc:
        raise ApiError(
            "invalid upload_fetch_proxy: %s" % exc, ErrorCode.PARAM_ERROR
        ) from exc


def _clean_smtp(value) -> dict:
    """Normalise the SMTP block, keeping the stored password on mask echo."""
    if not isinstance(value, dict):
        raise ApiError("smtp must be an object", ErrorCode.PARAM_ERROR)
    unknown = set(value) - _SMTP_FIELDS
    if unknown:
        raise ApiError(
            "unknown smtp field: %s" % sorted(unknown)[0], ErrorCode.PARAM_ERROR
        )

    current = dict(get_setting("smtp", {}) or {})

    def pick(key: str, default):
        return value[key] if key in value else current.get(key, default)

    try:
        port = int(pick("port", 25))
    except (TypeError, ValueError) as exc:
        raise ApiError("smtp.port must be an integer", ErrorCode.PARAM_ERROR) from exc
    if not 1 <= port <= 65535:
        raise ApiError(
            "smtp.port must be between 1 and 65535", ErrorCode.PARAM_ERROR
        )

    tls = pick("tls", False)
    if not isinstance(tls, bool):
        raise ApiError("smtp.tls must be a boolean", ErrorCode.PARAM_ERROR)

    password = pick("password", "")
    password = "" if password is None else str(password)
    #: 掩码原样回传表示不改密码，否则前端每次保存都会把密钥清空。
    if password == SMTP_PASSWORD_MASK:
        password = str(current.get("password") or "")

    return {
        "host": str(pick("host", "") or "").strip()[:255],
        "port": port,
        "user": str(pick("user", "") or "").strip()[:255],
        "password": password[:255],
        "from": str(pick("from", SMTP_DEFAULTS["from"]) or "").strip()[:255],
        "tls": tls,
    }


def _clean(key: str, value):
    """Validate one setting value, raising ``ApiError`` when out of contract."""
    if key == "smtp":
        return _clean_smtp(value)

    if key in _STR_KEYS:
        if not isinstance(value, str):
            raise ApiError("%s must be a string" % key, ErrorCode.PARAM_ERROR)
        if key == "upload_fetch_proxy":
            return _clean_proxy(value)
        return value.strip()[:500]

    if key in _INT_KEYS:
        low, high = _INT_KEYS[key]
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ApiError(
                "%s must be an integer" % key, ErrorCode.PARAM_ERROR
            ) from exc
        if not low <= number <= high:
            raise ApiError(
                "%s must be between %d and %d" % (key, low, high),
                ErrorCode.PARAM_ERROR,
            )
        return number

    if key in _BOOL_KEYS:
        if not isinstance(value, bool):
            raise ApiError("%s must be a boolean" % key, ErrorCode.PARAM_ERROR)
        return value

    if key in _FLOAT_KEYS:
        low, high = _FLOAT_KEYS[key]
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ApiError(
                "%s must be a number" % key, ErrorCode.PARAM_ERROR
            ) from exc
        if not low <= number <= high:
            raise ApiError(
                "%s must be between %s and %s" % (key, low, high),
                ErrorCode.PARAM_ERROR,
            )
        return number

    raise ApiError("unknown setting: %s" % key, ErrorCode.PARAM_ERROR)


@bp.get("/settings")
@admin_required
def read_settings():
    return ok(_payload_of_settings())


@bp.put("/settings")
@admin_required
def write_settings():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ApiError("settings must be a JSON object", ErrorCode.PARAM_ERROR)

    updated = {}
    for key, value in data.items():
        updated[key] = _clean(key, value)
    for key, value in updated.items():
        set_setting(key, value)
    return ok(_payload_of_settings())


@bp.get("/settings/version")
@admin_required
def check_version():
    """Current version against the newest release; ``?refresh=1`` skips the cache."""
    return ok(release.release_info(refresh=as_bool(request.args.get("refresh"))))


@bp.post("/settings/smtp/test")
@admin_required
def test_smtp():
    """Send a probe mail so the operator can verify the SMTP settings."""
    data = request.get_json(silent=True) or {}
    to = str(data.get("to") or "").strip() or (getattr(g.user, "email", "") or "")
    if not to:
        raise ApiError("email is required", ErrorCode.PARAM_ERROR)
    if not smtp_ready():
        raise ApiError(
            "mail service is not configured", ErrorCode.SERVICE_UNAVAILABLE, 503
        )
    send_test_mail(to)
    return ok({"sent": True, "to": to})
