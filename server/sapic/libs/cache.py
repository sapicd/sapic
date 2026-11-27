# -*- coding: utf-8 -*-
"""sapic.libs.cache

Small JSON/string cache used by ``/raw``.

Redis is optional: set ``sapic_redisurl`` to share the cache between workers, and
leave it empty to keep everything in this process. A missing package, an
unreachable server or a mid-request error all fall back to the in-process store,
because losing a cache line must never turn an image into a 500.

Only derived, short-lived data belongs here (currently the resolved ``/raw``
target). Authentication and hotlink decisions stay per request: they depend on
the caller, not just the image.
"""

from __future__ import annotations

import logging
from threading import Lock
from time import monotonic

from flask import Flask, current_app, has_app_context

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency
    redis = None

logger = logging.getLogger(__name__)

#: Upper bound for the in-process store; rotating keys must not grow forever.
MAX_ENTRIES = 5000
#: Key prefix, so a shared Redis can be inspected without guessing what is ours.
PREFIX = "sapic:"
#: Resolved ``/raw`` target: ``{sha}:{0|1}`` (the flag is the thumbnail request).
RAW_KEY = PREFIX + "raw:%s:%d"


class Cache:
    """Best-effort string cache with a Redis backend and a local fallback."""

    def __init__(self, url: str = ""):
        self.backend = "memory"
        self._redis = None
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = Lock()
        if url and redis is not None:
            try:
                client = redis.Redis.from_url(
                    url,
                    socket_connect_timeout=0.3,
                    socket_timeout=0.3,
                    decode_responses=True,
                )
                client.ping()
                self._redis = client
                self.backend = "redis"
            except Exception:
                #: 配了地址但连不上时降级，不阻止应用启动。
                logger.warning("redis cache unavailable, using memory", exc_info=True)

    def get(self, key: str) -> str | None:
        client = self._redis
        if client is not None:
            try:
                return client.get(key)
            except Exception:
                self._degrade()
        moment = monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            if item[0] <= moment:
                self._data.pop(key, None)
                return None
            return item[1]

    def set(self, key: str, value: str, ttl: int) -> None:
        ttl = max(1, int(ttl))
        client = self._redis
        if client is not None:
            try:
                client.set(key, value, ex=ttl)
                return
            except Exception:
                self._degrade()
        moment = monotonic()
        with self._lock:
            if len(self._data) >= MAX_ENTRIES:
                for expired in [
                    name for name, item in self._data.items() if item[0] <= moment
                ]:
                    self._data.pop(expired, None)
                if len(self._data) >= MAX_ENTRIES:
                    self._data.clear()
            self._data[key] = (moment + ttl, value)

    def delete(self, *keys: str) -> None:
        if not keys:
            return
        client = self._redis
        if client is not None:
            try:
                client.delete(*keys)
                return
            except Exception:
                self._degrade()
        with self._lock:
            for key in keys:
                self._data.pop(key, None)

    def clear_prefix(self, prefix: str) -> None:
        """Drop every entry under ``prefix`` (backend changes, bulk invalidation)."""
        client = self._redis
        if client is not None:
            try:
                for key in client.scan_iter(match=prefix + "*", count=500):
                    client.delete(key)
                return
            except Exception:
                self._degrade()
        with self._lock:
            for key in [name for name in self._data if name.startswith(prefix)]:
                self._data.pop(key, None)

    def _degrade(self) -> None:
        """Fall back to memory for the rest of this process."""
        logger.warning("redis cache failed, falling back to memory", exc_info=True)
        self._redis = None
        self.backend = "memory"


def init_app(app: Flask) -> None:
    """Attach the cache configured by ``REDIS_URL`` (empty = memory only)."""
    app.extensions["cache"] = Cache(app.config.get("REDIS_URL") or "")


#: Used when no app context exists (CLI / background job invalidation).
_FALLBACK: Cache | None = None


def get_cache() -> Cache:
    """The app bound cache, or a throwaway in-process one outside a request."""
    global _FALLBACK
    #: 后台任务/CLI 里也可能调用（删图时失效缓存），没有上下文就用进程内兜底。
    if not has_app_context():
        if _FALLBACK is None:
            _FALLBACK = Cache()
        return _FALLBACK
    cache = current_app.extensions.get("cache")
    if cache is None:
        #: 没有走 init_app 的场景（单测直接建 Cache）也要能读。
        cache = Cache()
        current_app.extensions["cache"] = cache
    return cache


def invalidate_raw(sha: str) -> None:
    """Forget both the normal and the thumbnail target of one image."""
    get_cache().delete(RAW_KEY % (sha, 0), RAW_KEY % (sha, 1))


def invalidate_all_raw() -> None:
    """Drop every resolved target (backend priority / visibility changes)."""
    get_cache().clear_prefix(PREFIX + "raw:")
