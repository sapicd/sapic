# -*- coding: utf-8 -*-
"""sapic.libs.release

Update check for the admin console: current version against the newest GitHub
release.

The lookup is opt-in by nature (it leaves the server), so it is fetched lazily,
cached per process for a day and never raises: the console shows "unknown"
instead of breaking when GitHub is unreachable.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from ..utils.common import is_newer_version
from ..version import __version__

logger = logging.getLogger(__name__)

#: A release changes a few times a month at most; one fetch per day is plenty.
CACHE_TTL = 24 * 3600

#: Keep the console responsive when the network is down.
FETCH_TIMEOUT = 8

_cache_lock = RLock()
_cache: dict = {"data": None, "ts": 0.0}


def _timestamp(value) -> int:
    """GitHub's ISO-8601 timestamp as a 10-digit epoch; ``0`` when unknown."""
    try:
        return int(
            datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        )
    except (TypeError, ValueError, OSError):
        return 0


def _fetch(url: str) -> dict:
    """Read the latest release payload; raises on any transport problem."""
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "sapic-update-check",
        },
    )
    with urlopen(request, timeout=FETCH_TIMEOUT) as response:
        raw = response.read(256 * 1024)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("unexpected release payload")
    return data


def release_info(refresh: bool = False) -> dict:
    """Current version plus the newest release, cached in this process."""
    url = str(current_app.config.get("UPDATE_CHECK_URL") or "").strip()
    current = __version__

    def payload(
        latest: str = "",
        released_at: int = 0,
        link: str = "",
        error: str = "",
        checked_at: int = 0,
        cached: bool = False,
    ) -> dict:
        return {
            "enabled": bool(url),
            "current": current,
            "latest": latest,
            "has_update": is_newer_version(latest, current) if latest else False,
            "released_at": released_at,
            "url": link,
            "checked_at": checked_at,
            "cached": cached,
            "error": error,
        }

    if not url:
        #: 置空即关闭检测：私有部署不想让服务器访问外网。
        return payload()

    now = time.time()
    with _cache_lock:
        cached_data = _cache["data"]
        cached_ts = _cache["ts"]
    if not refresh and cached_data is not None and now - cached_ts < CACHE_TTL:
        return {**cached_data, "checked_at": int(cached_ts), "cached": True}

    try:
        data = _fetch(url)
        latest = str(data.get("tag_name") or "").strip()
        result = payload(
            latest=latest,
            released_at=_timestamp(data.get("published_at")),
            link=str(data.get("html_url") or "").strip(),
            checked_at=int(time.time()),
        )
    except (HTTPError, URLError, OSError, ValueError) as exc:
        logger.warning("Update check failed: %s", exc)
        return payload(error="failed to reach the release feed")

    with _cache_lock:
        _cache["data"] = result
        _cache["ts"] = time.time()
    return result


def clear_cache() -> None:
    """Drop the cached release (tests and manual refresh)."""
    with _cache_lock:
        _cache["data"] = None
        _cache["ts"] = 0.0
