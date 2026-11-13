# -*- coding: utf-8 -*-
"""Hard-coded constants that do not change between deployments."""

from __future__ import annotations

from os.path import abspath, dirname, join
from typing import Literal

#: Environment variable prefix for config overrides.
ENV_PREFIX = "sapic_"

#: Environment switch selecting the dev/prod config class.
ENV_NAME = ENV_PREFIX + "env"

#: Project root (``server/``), three levels above this module.
BASE_DIR = dirname(dirname(dirname(abspath(__file__))))

#: Local config file, read before environment variables.
CFG_FILE = join(BASE_DIR, ".cfg")

#: Runtime data directory (default SQLite file and uploads); created on start.
DATA_DIR = join(BASE_DIR, "data")

#: Fallback ``SECRET_KEY``: long enough to start without configuring anything.
#: It is public (it lives in this repository), so a public multi-user deployment
#: should still override it via ``sapic_secretkey``; empty values fall back here.
DEFAULT_SECRET_KEY = "BD1E2CF7DF9CD6971D641C115EE72871BEDA2806"

#: String values treated as ``True`` by :func:`sapic.basis.common.as_bool`.
TRUE_VALUES = ("1", "true", "yes", "on")

#: Legal log levels; the annotation is the single source of truth.
LOG_LEVEL_TYPE = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

#: Session cookie name; part of the app identity, never per-deployment.
SESSION_COOKIE_NAME = "sapic_sid"

#: Salt isolating the signed login-state cookie from other signed payloads.
SESSION_COOKIE_SALT = "sapic-login-state"

#: Hook directory rescan interval, in seconds.
HOOK_RELOAD_TIME = 600

#: Official third-party hook listing (a JSON array hosted on GitHub).
DEFAULT_HOOK_MARKET_URL = (
    "https://api.github.com/repos/sapicd/awesome/contents/list.json"
)

#: Latest release feed used by the admin update check; empty disables it.
DEFAULT_RELEASE_URL = "https://api.github.com/repos/sapicd/sapic/releases/latest"

#: Documentation root used by front-end help links.
DOCS_BASE_URL = "https://sapic.rtfd.vip/zh_cn/latest/"
