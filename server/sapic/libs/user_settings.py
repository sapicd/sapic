# -*- coding: utf-8 -*-
"""sapic.libs.user_settings

Per-user preferences backed by the ``user_settings`` key/value table.

v1 kept these in ``ucfg_*`` fields of its single user hash; v2 stores one row
per key so a new preference never needs a schema change. :data:`DEFAULTS` is
the single source of truth: it holds the value used when the row is missing and
also drives type/range validation, so an unknown key is rejected instead of
being silently stored and never read.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ..basis.db import db
from ..basis.errors import ApiError, ErrorCode
from ..models import UserSetting
from ..models.base import now
from ..utils.common import validate_allow_hosts

#: 个人设置默认值：既是「未设置」时的取值，也是该键的类型与校验依据。
DEFAULTS: dict[str, object] = {
    #: 油猴脚本开关：关掉后 ``/api/v2/userscript.user.js`` 对该用户 404。
    "userscript_enabled": False,
    #: 个人背景图：外链 http(s) 或站内以 / 开头的路径，空表示跟随站点背景。
    "bg_image": "",
    "bg_image_mobile": "",
    #: 背景遮罩透明度，``None`` 表示跟随站点设置。
    "bg_opacity": None,
    #: 防盗链：只拦截公开图在 ``/raw/<sha>`` 上的外站引用；走存储直链（配置了
    #: 加速域名）的图片不经过 sapic，需要在 CDN/nginx 上另外配置。
    "hotlink_enabled": False,
    #: 额外放行的引用域名，逗号分隔，支持 ``*.example.com``；本站域名永远放行。
    "hotlink_allow_hosts": "",
    #: 没有 ``Referer`` 的请求（直接打开、聊天工具预览等）是否放行。
    "hotlink_allow_empty": True,
}


def _clean_bool(key: str, value) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1, "0", "1"):
        return bool(int(value))
    raise ApiError("%s must be a boolean" % key, ErrorCode.PARAM_ERROR)


def _clean_url(key: str, value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 512:
        raise ApiError("%s is too long" % key, ErrorCode.PARAM_ERROR)
    parsed = urlsplit(text)
    if parsed.scheme:
        #: 只放行外链与站内绝对路径，挡掉 javascript:/data: 这类可执行载荷。
        if parsed.scheme not in ("http", "https"):
            raise ApiError(
                "%s must be an http(s) url" % key, ErrorCode.PARAM_ERROR
            )
    elif not text.startswith("/") or text.startswith("//"):
        raise ApiError(
            "%s must be an http(s) url or a path starting with /" % key,
            ErrorCode.PARAM_ERROR,
        )
    return text


def _clean_opacity(key: str, value):
    if value in (None, ""):
        return None
    try:
        number = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ApiError("%s must be a number" % key, ErrorCode.PARAM_ERROR) from exc
    if not 0 <= number <= 1:
        raise ApiError("%s must be between 0 and 1" % key, ErrorCode.PARAM_ERROR)
    return number


def _clean(key: str, value):
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return _clean_bool(key, value)
    if key == "bg_opacity":
        return _clean_opacity(key, value)
    if key == "hotlink_allow_hosts":
        #: 存的是规范化后的域名列表，不是 URL，不能走 _clean_url。
        return validate_allow_hosts(value)
    return _clean_url(key, value)


def get_user_settings(user) -> dict:
    """All preferences of ``user``, missing rows filled with defaults."""
    values = dict(DEFAULTS)
    if user is None:
        return values
    for row in UserSetting.select().where(UserSetting.user == user):
        if row.key in values:
            values[row.key] = row.value
    return values


def user_setting(user, key: str, default=None):
    """One preference of ``user`` (defaults apply when nothing is stored)."""
    if user is None:
        return DEFAULTS.get(key, default)
    row = UserSetting.get_or_none(
        (UserSetting.user == user) & (UserSetting.key == key)
    )
    if row is None or row.value is None:
        return DEFAULTS.get(key, default)
    return row.value


def set_user_settings(user, data) -> dict:
    """Validate and upsert the given keys, returning the merged settings.

    Only the keys present in ``data`` are touched, so the UI can save one block
    without sending the whole document.
    """
    if not isinstance(data, dict) or not data:
        raise ApiError("no settings to update", ErrorCode.PARAM_ERROR)
    unknown = sorted(set(data) - set(DEFAULTS))
    if unknown:
        raise ApiError("unknown setting: %s" % unknown[0], ErrorCode.PARAM_ERROR)

    updates = {key: _clean(key, value) for key, value in data.items()}
    with db.atomic():
        for key, value in updates.items():
            row = UserSetting.get_or_none(
                (UserSetting.user == user) & (UserSetting.key == key)
            )
            if row is None:
                UserSetting.create(user=user, key=key, value=value, updated_at=now())
                continue
            row.value = value
            row.updated_at = now()
            row.save(only=[UserSetting.value, UserSetting.updated_at])
    return get_user_settings(user)
