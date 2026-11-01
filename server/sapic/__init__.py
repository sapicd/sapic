# -*- coding: utf-8 -*-
"""Sapic v2 backend application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .version import __version__

if TYPE_CHECKING:
    from flask import Flask


def create_app(config: dict | None = None) -> Flask:
    """Create the Flask application."""
    #: Imports are deferred so that ``import sapic`` stays cheap and
    #: side-effect free (e.g. reading ``sapic.__version__`` for packaging).
    import logging
    from uuid import uuid4

    from flask import Flask, g, request
    from werkzeug.middleware.proxy_fix import ProxyFix

    from .basis.conf import load_config
    from .basis.db import init_app as init_db
    from .basis.errors import register_error_handlers
    from .cli import sa_cli
    from .libs.auth import init_app as init_auth
    from .libs.hook import init_app as init_hooks
    from .migrations import auto_upgrade
    from .views import register_blueprints

    app = Flask(__name__)
    app.config.from_mapping(load_config())
    if config:
        app.config.update(config)

    if not app.config.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required (config: sapic_db_url)")

    app.logger.setLevel(getattr(logging, app.config.get("LOG_LEVEL", "INFO")))

    if app.config.get("PROXY_FIX"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    init_db(app)
    auto_upgrade()
    init_auth(app)
    init_hooks(app)
    register_blueprints(app)
    register_error_handlers(app)
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
