# -*- coding: utf-8 -*-
"""Application configuration.

Defaults live as typed class attributes on ``BaseConfig`` / ``DevConfig`` /
``ProdConfig``. They are overridden by ``server/.cfg``, then by ``sapic_*``
environment variables, and the result is validated before use.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from os import makedirs
from os.path import exists, isabs, join
from typing import Any, get_args

from .common import as_bool, as_int, is_dev
from .vars import (
    BASE_DIR,
    CFG_FILE,
    DATA_DIR,
    DEFAULT_HOOK_MARKET_URL,
    DEFAULT_RELEASE_URL,
    DEFAULT_SECRET_KEY,
    ENV_PREFIX,
    LOG_LEVEL_TYPE,
)

__all__ = ["BaseConfig", "DevConfig", "ProdConfig", "load_config"]

#: Legal log levels, kept in sync with ``vars.LOG_LEVEL_TYPE``.
_LOG_LEVELS = get_args(LOG_LEVEL_TYPE)

#: Env suffixes that differ from ``KEY.lower()`` for historical reasons
#: (``sapic_db_url`` …); they are documented and must not be renamed.
_ENV_SUFFIX = {
    "SECRET_KEY": "secretkey",
    "DATABASE_URL": "db_url",
    "MAX_UPLOAD": "maxupload",
    "STORAGE_DIR": "storagedir",
    "PROXY_FIX": "proxyfix",
    "LOG_LEVEL": "loglevel",
    "HOOK_PKG_STORAGE_DIR": "hookpkgstoragedir",
    "HOOK_MARKET_URL": "hookmarketurl",
    "UPDATE_CHECK_URL": "updatecheckurl",
}


class BaseConfig:
    """Production defaults; every item can be overridden by ``sapic_<suffix>``."""

    #: Runtime environment and debug flag.
    ENV: str = "production"
    DEBUG: bool = False

    #: Cookie signing key, at least 14 bytes, 32+ recommended.
    SECRET_KEY: str = DEFAULT_SECRET_KEY

    #: Database DSN (postgresql / mysql / sqlite); defaults to SQLite in ``data/``.
    DATABASE_URL: str = "sqlite:///" + join(DATA_DIR, "sapic.db")

    #: Whole-request limit, in MB. Must stay above the site's per-type limits
    #: (``upload_video_max_size`` 默认 20）: multipart 有额外开销，留一点余量。
    MAX_UPLOAD: int = 25
    #: Local storage root; relative paths are resolved against ``server/``.
    STORAGE_DIR: str = join(DATA_DIR, "upload")
    #: Public base URL prepended to image links, empty means relative.
    EXTERNAL_BASE_URL: str = ""

    #: Trust ``X-Forwarded-*`` headers from a reverse proxy.
    PROXY_FIX: bool = False
    LOG_LEVEL: LOG_LEVEL_TYPE = "INFO"

    #: Directory holding extra hook packages (``pip install --target`` target and
    #: an extra hook scan path); empty disables web installation entirely.
    HOOK_PKG_STORAGE_DIR: str = join(DATA_DIR, "hooks")

    #: Third-party hook listing consumed by the admin market page.
    HOOK_MARKET_URL: str = DEFAULT_HOOK_MARKET_URL

    #: Latest release feed for the admin update check; empty disables it.
    UPDATE_CHECK_URL: str = DEFAULT_RELEASE_URL

    #: Session lifetime (seconds).
    SESSION_TTL: int = 7 * 24 * 3600

    #: Feature switches.
    ALLOW_REGISTER: bool = True
    ALLOW_ANONYMOUS_UPLOAD: bool = False


class DevConfig(BaseConfig):
    """Development defaults: debug on, verbose logging."""

    ENV = "development"
    DEBUG = True
    LOG_LEVEL = "DEBUG"


class ProdConfig(BaseConfig):
    """Production defaults."""

    ENV = "production"
    DEBUG = False


def _options(config_cls: type[BaseConfig]) -> dict[str, Any]:
    """Collect public config items (``UPPER`` class attributes) along the MRO."""
    options: dict[str, Any] = {}
    for klass in reversed(config_cls.__mro__):
        options.update(
            {name: value for name, value in vars(klass).items() if name.isupper()}
        )
    return options


def _read_cfg_file(path: str) -> dict[str, str]:
    """Parse ``key=value`` lines from the local config file."""
    data: dict[str, str] = {}
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


def _env_overrides(names: Iterable[str]) -> dict[str, str]:
    """Read ``.cfg`` first, then let ``sapic_*`` environment variables win."""
    raw = _read_cfg_file(CFG_FILE)
    raw.update(
        {
            key: value
            for key, value in os.environ.items()
            if key.startswith(ENV_PREFIX)
        }
    )
    overrides: dict[str, str] = {}
    for name in names:
        suffix = _ENV_SUFFIX[name] if name in _ENV_SUFFIX else name.lower()
        value = raw.get(ENV_PREFIX + suffix)
        if value is not None:
            overrides[name] = value
    return overrides


def _cast(value: str, default: Any) -> Any:
    """Cast a string override to the type of its default value."""
    if isinstance(default, bool):
        return as_bool(value)
    if isinstance(default, int):
        return as_int(value, default)
    return str(value)


def _absolute(path: str) -> str:
    """Resolve a relative storage path against ``server/``."""
    return path if isabs(path) else join(BASE_DIR, path)


def _ensure_dir(path: str) -> None:
    """Create ``path`` when missing; runtime data must exist before first write."""
    makedirs(path, exist_ok=True)


def _check_config_value(cfg: dict) -> None:
    """Validate the config mapping, raising ``AssertionError`` when invalid.

    Checks ``LOG_LEVEL`` against :data:`sapic.basis.vars.LOG_LEVEL_TYPE`, the
    positive-integer options (``MAX_UPLOAD`` / ``SESSION_TTL``), the secret key
    length (the built-in default is accepted on purpose) and the absolute
    ``STORAGE_DIR``.
    """
    assert isinstance(cfg, dict), "Config must be a dict"

    assert cfg["LOG_LEVEL"] in _LOG_LEVELS, "LOG_LEVEL must be one of {}".format(
        ", ".join(_LOG_LEVELS)
    )
    assert (
        isinstance(cfg["MAX_UPLOAD"], int) and cfg["MAX_UPLOAD"] >= 1
    ), "MAX_UPLOAD must be a positive integer"
    assert (
        isinstance(cfg["SESSION_TTL"], int) and cfg["SESSION_TTL"] >= 60
    ), "SESSION_TTL must be at least 60 seconds"

    #: 不再强制生产替换：默认值本身足够长，单机自用开箱即用（少一步必填配置）。
    #: 它是公开串——公网多用户站点仍建议用 sapic_secretkey 换成自己的，
    #: 否则读过源码的人可以伪造会话 Cookie；空值一律按默认处理。
    secret_key = cfg["SECRET_KEY"] or DEFAULT_SECRET_KEY
    assert isinstance(secret_key, str), "SECRET_KEY must be a string"
    assert len(secret_key) >= 14, "SECRET_KEY must be at least 14 bytes"
    cfg["SECRET_KEY"] = secret_key

    assert isabs(cfg["STORAGE_DIR"]), "STORAGE_DIR must be an absolute path"


def load_config(overrides: dict | None = None) -> dict:
    """Build the Flask config mapping.

    Items come from the selected config class, then ``server/.cfg``, then the
    environment; ``overrides`` (keyed by config name) bypass both sources.
    """
    defaults = _options(DevConfig if is_dev() else ProdConfig)
    raw = _env_overrides(defaults) if overrides is None else overrides

    config = {
        name: _cast(raw[name], default) if name in raw else default
        for name, default in defaults.items()
    }
    config["MAX_CONTENT_LENGTH"] = config["MAX_UPLOAD"] * 1024 * 1024
    config["STORAGE_DIR"] = _absolute(config["STORAGE_DIR"])
    #: 第三方钩子包目录会被写进 ``sys.path``，相对路径必须先按 ``server/`` 归一。
    if config["HOOK_PKG_STORAGE_DIR"]:
        config["HOOK_PKG_STORAGE_DIR"] = _absolute(config["HOOK_PKG_STORAGE_DIR"])
    config["EXTERNAL_BASE_URL"] = config["EXTERNAL_BASE_URL"].rstrip("/")
    config["LOG_LEVEL"] = config["LOG_LEVEL"].upper()

    _check_config_value(config)
    #: Default SQLite file and uploads live under ``data/``; create it up front.
    _ensure_dir(DATA_DIR)
    return config
