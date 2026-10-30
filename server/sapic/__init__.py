# -*- coding: utf-8 -*-
"""Sapic v2 backend application factory."""

from __future__ import annotations

import logging
from uuid import uuid4

from flask import Flask, g, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import load_config
from .errors import register_error_handlers
from .version import __version__


def create_app(config: dict | None = None) -> Flask:
    """Create the Flask application."""
    app = Flask(__name__)
    app.config.from_mapping(load_config())
    if config:
        app.config.update(config)

    if not app.config.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required (config: sapic_db_url)")

    app.logger.setLevel(getattr(logging, app.config.get("LOG_LEVEL", "INFO")))

    if app.config.get("PROXY_FIX"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    app.config.setdefault(
        "PERMANENT_SESSION_LIFETIME", app.config.get("SESSION_TTL", 7 * 24 * 3600)
    )
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    from . import extensions

    extensions.init_app(app)

    from . import security

    security.init_app(app)

    from .libs.hook import init_app as init_hooks

    init_hooks(app)

    from .api import register_blueprints

    register_blueprints(app)
    register_error_handlers(app)

    from .cli import sa_cli

    app.cli.add_command(sa_cli)

    @app.before_request
    def _request_id():
        g.request_id = request.headers.get("X-Request-Id") or uuid4().hex[:16]

    @app.after_request
    def _attach_request_id(response):
        response.headers["X-Request-Id"] = getattr(g, "request_id", "")
        return response

    @app.get("/")
    def index():
        return {
            "code": "OK",
            "message": "",
            "data": {"service": "sapic", "version": __version__},
        }

    return app


__all__ = ["create_app", "__version__"]
