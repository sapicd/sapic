# -*- coding: utf-8 -*-
"""View layer: blueprint registration and route modules.

Blueprints under ``API_PREFIX`` are the native v2 API, including the userscript
installer: putting it at ``/api/v2/userscript.user.js`` lets a reverse proxy
cover it with the same ``/api/`` rule as everything else, while managers only
care about the ``.user.js`` suffix. Only ``public`` (``/raw/<sha>``) stays
outside the prefix, because published image links point at the site root.
"""

from __future__ import annotations

API_PREFIX = "/api/v2"


def register_blueprints(app) -> None:
    from .albums import bp as albums_bp
    from .auth import bp as auth_bp
    from .backends import bp as backends_bp
    from .health import bp as health_bp
    from .hooks import bp as hooks_bp
    from .images import bp as images_bp
    from .plaza import bp as plaza_bp
    from .public import bp as public_bp
    from .settings import bp as settings_bp
    from .site import bp as site_bp
    from .uploads import bp as uploads_bp
    from .userscript import bp as userscript_bp
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
        backends_bp,
        hooks_bp,
        users_bp,
        userscript_bp,
    ):
        app.register_blueprint(blueprint, url_prefix=API_PREFIX)

    #: 根路径只留图片直链：已发布的 ``/raw/<sha>`` 链接由它兜底。
    app.register_blueprint(public_bp)
