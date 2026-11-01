# -*- coding: utf-8 -*-
"""Health endpoint used by Kubernetes probes."""

from __future__ import annotations

from flask import Blueprint

from ..basis.db import ping_database, ping_redis
from ..utils.web import json_response
from ..version import __version__

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    database = ping_database()
    redis = ping_redis()
    healthy = database
    payload = {
        "code": "OK" if healthy else "SERVICE_UNAVAILABLE",
        "message": "",
        "data": {
            "status": "ok" if healthy else "degraded",
            "version": __version__,
            "database": database,
            "redis": redis,
        },
    }
    return json_response(payload, 200 if healthy else 503)
