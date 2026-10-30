# -*- coding: utf-8 -*-
"""Application configuration.

Priority: built-in defaults -> ``server/.cfg`` -> environment (``sapic_``).
"""

from __future__ import annotations

import os
from os.path import abspath, dirname, exists, join

BASE_DIR = dirname(dirname(abspath(__file__)))
CFG_FILE = join(BASE_DIR, ".cfg")

DEFAULT_SECRET_KEY = "BD1E2CF7DF9CD6971D641C115EE72871BEDA2806"

_TRUE_VALUES = ("1", "true", "yes", "on")


def as_bool(value) -> bool:
    """Parse a truthy config value."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUE_VALUES


def as_int(value, default: int) -> int:
    """Parse an int config value with fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_cfg_file(path: str) -> dict:
    data = {}
    if not exists(path):
        return data
    with open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def load_envs() -> dict:
    """Read ``.cfg`` first, then let environment variables win."""
    envs = _read_cfg_file(CFG_FILE)
    for key, value in os.environ.items():
        if key.startswith("sapic_"):
            envs[key] = value
    return envs


def load_config(envs: dict | None = None) -> dict:
    """Build the Flask config mapping."""
    envs = load_envs() if envs is None else envs

    def get(key: str, default=None):
        return envs.get(key, default)

    max_upload = as_int(get("sapic_maxupload"), 20)
    storagedir = get("sapic_storagedir") or join(BASE_DIR, "data", "upload")
    if not os.path.isabs(storagedir):
        storagedir = join(BASE_DIR, storagedir)

    return {
        "SECRET_KEY": get("sapic_secretkey") or DEFAULT_SECRET_KEY,
        "DATABASE_URL": get("sapic_db_url", ""),
        "REDIS_URL": get("sapic_redis_url", ""),
        "MAX_UPLOAD": max_upload,
        "MAX_CONTENT_LENGTH": max_upload * 1024 * 1024,
        "STORAGE_DIR": storagedir,
        "EXTERNAL_BASE_URL": (get("sapic_external_base_url") or "").rstrip("/"),
        "PROXY_FIX": as_bool(get("sapic_proxyfix")),
        "LOG_LEVEL": (get("sapic_loglevel") or "INFO").upper(),
        "HOOK_RELOAD_TIME": as_int(get("sapic_hookreloadtime"), 600),
        "HOOK_PKG_STORAGE_DIR": get("sapic_hookpkgstoragedir", ""),
        "SESSION_COOKIE_NAME": get("sapic_session_cookie") or "sapic_sid",
        "SESSION_TTL": as_int(get("sapic_session_ttl"), 7 * 24 * 3600),
        "ALLOW_REGISTER": as_bool(get("sapic_allow_register", "true")),
        "ALLOW_ANONYMOUS_UPLOAD": as_bool(
            get("sapic_allow_anonymous_upload", "false")
        ),
        "DOCS_BASE_URL": get(
            "sapic_docs_base_url", "https://sapic.rtfd.vip/zh_cn/latest/"
        ),
    }
