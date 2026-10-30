# -*- coding: utf-8 -*-
"""API blueprint registration.

Blueprints under ``API_PREFIX`` are the native v2 API; ``public`` and
``legacy`` keep stable URLs (``/i/<sha>``, ``/api/upload``, ``/api/sha``).
"""

from __future__ import annotations

API_PREFIX = "/api/v1"


def register_blueprints(app) -> None:
    from .albums import bp as albums_bp
    from .auth import bp as auth_bp
    from .health import bp as health_bp
    from .images import bp as images_bp
    from .legacy import bp as legacy_bp
    from .public import bp as public_bp
    from .uploads import bp as uploads_bp

    for blueprint in (health_bp, auth_bp, uploads_bp, images_bp, albums_bp):
        app.register_blueprint(blueprint, url_prefix=API_PREFIX)

    app.register_blueprint(public_bp)
    app.register_blueprint(legacy_bp)
