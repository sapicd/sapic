# -*- coding: utf-8 -*-
"""Per-client API rate limiting.

Every ``/api/`` request is counted against the site setting
``api_rate_limit`` (requests per minute, ``0`` disables it). The counter is a
fixed one-minute window kept in this process: multi-worker deployments therefore
allow ``limit`` requests *per worker*, because sharing the window would need a
store (Redis) that sapic v2 deliberately does not require.

Clients are identified by their signed-in user id, or by IP for anonymous
requests. ``/api/v2/health`` and non-API paths (``/raw/``) are never counted, so
health probes and image delivery keep working when the limit is exhausted.
"""

from __future__ import annotations

import logging
from threading import Lock
from time import monotonic

from flask import current_app, g, request

from ..basis.errors import ApiError, ErrorCode
from .settings import get_setting

logger = logging.getLogger(__name__)

#: Window length in seconds; the setting is expressed per minute.
WINDOW = 60.0
#: How long a saved limit may take to reach the other workers. The worker that
#: handled the settings write applies it immediately via :func:`forget_rate_limit`.
CONFIG_TTL = 5.0
#: Upper bound for tracked clients: rotating addresses must not grow the dict
#: without limit.
MAX_KEYS = 10000
#: Sweep expired windows every N hits instead of on every request.
PRUNE_EVERY = 1024
#: Health checks come from load balancers and must never be throttled.
HEALTH_PATH = "/api/v2/health"


class RateLimiter:
    """Fixed-window counters keyed by client (user id or IP)."""

    def __init__(
        self,
        window: float = WINDOW,
        config_ttl: float = CONFIG_TTL,
        max_keys: int = MAX_KEYS,
    ):
        self._window = float(window)
        self._config_ttl = float(config_ttl)
        self._max_keys = max(1, int(max_keys))
        #: ``key -> [window_index, count]``; the window index makes stale rows
        #: distinguishable without storing timestamps per entry.
        self._buckets: dict[str, list[int]] = {}
        self._hits = 0
        self._limit = 0
        self._limit_at = 0.0
        self._lock = Lock()

    def forget(self, reset: bool = False) -> None:
        """Drop the cached limit; ``reset`` also clears the current counters."""
        with self._lock:
            self._limit_at = 0.0
            if reset:
                self._buckets.clear()
                self._hits = 0

    def limit(self) -> int:
        """The configured requests-per-minute, cached for a few seconds."""
        moment = monotonic()
        with self._lock:
            if moment - self._limit_at < self._config_ttl:
                return self._limit

        #: Read outside the lock: this is a database query, and two workers
        #: racing on a refresh is harmless.
        try:
            value = int(get_setting("api_rate_limit"))
        except (TypeError, ValueError):
            logger.warning("invalid api_rate_limit setting, rate limiting disabled")
            value = 0
        value = max(0, value)
        with self._lock:
            self._limit = value
            self._limit_at = monotonic()
            return value

    def check(
        self, key: str, limit: int, now: float | None = None
    ) -> tuple[bool, int]:
        """Count one hit; return ``(allowed, retry_after_seconds)``."""
        moment = monotonic() if now is None else float(now)
        if limit <= 0:
            return True, 0
        window = int(moment // self._window)
        retry_after = max(1, int(self._window - (moment % self._window)) + 1)

        with self._lock:
            self._hits += 1
            if self._hits % PRUNE_EVERY == 0 or len(self._buckets) >= self._max_keys:
                self._prune(window)
            bucket = self._buckets.get(key)
            if bucket is None or bucket[0] != window:
                if len(self._buckets) >= self._max_keys and self._buckets:
                    #: Still full of live windows: evict the oldest entry instead
                    #: of letting the dict grow. That client starts over, which
                    #: is preferable to unbounded memory under address rotation.
                    self._buckets.pop(next(iter(self._buckets)), None)
                self._buckets[key] = [window, 1]
                return True, 0
            if bucket[1] >= limit:
                return False, retry_after
            bucket[1] += 1
            return True, 0

    def _prune(self, window: int) -> None:
        stale = [key for key, bucket in self._buckets.items() if bucket[0] != window]
        for key in stale:
            self._buckets.pop(key, None)


def client_key() -> str:
    """Limit key: the signed-in user, or the IP for anonymous requests."""
    user = getattr(g, "user", None)
    if user is not None:
        return "u:%s" % getattr(user, "id", 0)
    return "ip:%s" % (request.remote_addr or "-")


def forget_rate_limit(reset: bool = False) -> None:
    """Apply a just-saved limit on this worker (see ``views/settings.py``)."""
    limiter = current_app.extensions.get("rate_limiter")
    if limiter is not None:
        limiter.forget(reset=reset)


def init_app(app) -> None:
    """Register the limiter and its ``before_request`` guard."""
    limiter = RateLimiter()
    app.extensions["rate_limiter"] = limiter

    @app.before_request
    def _api_rate_limit():
        if request.method == "OPTIONS":
            return None
        if not request.path.startswith("/api/") or request.path == HEALTH_PATH:
            return None
        limit = limiter.limit()
        if limit <= 0:
            return None
        allowed, retry_after = limiter.check(client_key(), limit)
        if allowed:
            return None
        g.rate_limit_retry_after = retry_after
        raise ApiError("rate limit exceeded", ErrorCode.RATE_LIMITED, 429)

    @app.after_request
    def _rate_limit_headers(response):
        retry_after = getattr(g, "rate_limit_retry_after", 0)
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response
