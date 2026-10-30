# -*- coding: utf-8 -*-
"""Site settings persisted in the ``settings`` table."""

from __future__ import annotations

from ..models import Setting
from ..models.base import now

DEFAULTS = {
    "site_name": "sapic",
    "site_description": "",
    "allow_register": True,
    "default_album_visibility": "private",
    "allow_anonymous_upload": False,
    "upload_max_size": 20,
    "external_base_url": "",
    "smtp": {},
}


def get_setting(key: str, default=None):
    """Read a setting, falling back to built-in defaults."""
    row = Setting.get_or_none(Setting.key == key)
    if row is None:
        return DEFAULTS.get(key, default)
    return row.value


def set_setting(key: str, value):
    """Create or update a setting."""
    row = Setting.get_or_none(Setting.key == key)
    if row is None:
        return Setting.create(key=key, value=value, updated_at=now())
    row.value = value
    row.updated_at = now()
    row.save(only=[Setting.value, Setting.updated_at])
    return row
