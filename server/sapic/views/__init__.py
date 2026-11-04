# -*- coding: utf-8 -*-
"""View layer: blueprint registration and route modules.

Blueprints under ``API_PREFIX`` are the native v2 API; ``public`` keeps the
stable image URL (``/raw/<sha>``).
"""

from __future__ import annotations

API_PREFIX = "/api/v2"


def register_blueprints(app) -> None:
    from .albums import bp as albums_bp
    from .auth import bp as auth_bp
    from .health import bp as health_bp
    from .hooks import bp as hooks_bp
    from .images import bp as images_bp
    from .plaza import bp as plaza_bp
    from .public import bp as public_bp
    from .settings import bp as settings_bp
    from .site import bp as site_bp
    from .uploads import bp as uploads_bp
    from .users import bp as users_bp

    for blueprint in (
        health_bp,
        site_bp,
        auth_bp,
        uploads_bp,
        images_bp,
        albums_bp,
        plaza_bp,
        settings_bp,
        hooks_bp,
        users_bp,
    ):
        app.register_blueprint(blueprint, url_prefix=API_PREFIX)

    app.register_blueprint(public_bp)
