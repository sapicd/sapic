# -*- coding: utf-8 -*-
"""Site settings API (admin only)."""

from __future__ import annotations

from flask import Blueprint, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.auth import admin_required
from ..libs.settings import DEFAULTS, get_setting, set_setting
from ..utils.web import ok

bp = Blueprint("settings", __name__)

#: Editable string settings.
_STR_KEYS = {
    "external_base_url",
    "forbidden_username",
    "site_about",
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
    "upload_notice",
}

#: Integer settings and their inclusive bounds.
_INT_KEYS = {"upload_count_limit": (1, 100), "upload_max_size": (1, 1024)}

_BOOL_KEYS = {
    "allow_anonymous_upload",
    "allow_register",
    "allow_video",
    "register_review",
}

_FLOAT_KEYS = {"site_background_opacity": (0.0, 1.0)}

#: Keys the admin UI may write; everything else in ``DEFAULTS`` is internal.
EDITABLE_KEYS = sorted(
    _STR_KEYS | set(_INT_KEYS) | _BOOL_KEYS | set(_FLOAT_KEYS)
)


def _payload_of_settings() -> dict:
    return {
        "items": {key: get_setting(key) for key in DEFAULTS},
        "editable": EDITABLE_KEYS,
    }


def _clean(key: str, value):
    """Validate one setting value, raising ``ApiError`` when out of contract."""
    if key in _STR_KEYS:
        if not isinstance(value, str):
            raise ApiError("%s must be a string" % key, ErrorCode.PARAM_ERROR)
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
