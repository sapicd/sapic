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
    from .basis.log import init_app as init_log
    from .cli import sa_cli
    from .libs.auth import init_app as init_auth
    from .libs.hook import init_app as init_hooks
    from .libs.images import sweep_expired
    from .libs.ratelimit import init_app as init_rate_limit
    from .libs.scheduler import init_app as init_scheduler
    from .libs.storage import sync_backends
    from .migrations import auto_upgrade
    from .views import register_blueprints

    app = Flask(__name__)
    app.config.from_mapping(load_config())
    if config:
        app.config.update(config)

    if not app.config.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required (config: sapic_db_url)")

    app.logger.setLevel(getattr(logging, app.config.get("LOG_LEVEL", "INFO")))
    init_log(app)

    if app.config.get("PROXY_FIX"):
        #: x_for 让请求拿到真实客户端 IP：容器里 gunicorn 只听 127.0.0.1，
        #: 不信任 X-Forwarded-For 时限速会把全站算成同一个客户端。
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    init_db(app)
    auto_upgrade()
    init_auth(app)
    init_hooks(app)
    #: 启用的存储钩子必须有对应的后端行才能被上传链路选中。
    with app.app_context():
        sync_backends()
    register_blueprints(app)
    register_error_handlers(app)
    app.cli.add_command(sa_cli)
    #: 到期清理与审核扫描由进程内 APScheduler 驱动；多 worker 靠文件锁选主，
    #: 只有抢到锁的那个进程真正跑（见 libs/scheduler.py）。
    init_scheduler(app)

    @app.before_request
    def _request_id():
        g.request_id = request.headers.get("X-Request-Id") or uuid4().hex[:16]

    #: 放在鉴权与 request_id 之后：已登录用户按账号计数、匿名按 IP 计数，
    #: 429 响应也能带上 request_id。
    init_rate_limit(app)

    if not app.config.get("SCHEDULER"):
        #: 关掉调度器时的兜底（老部署/单进程开发也能清理到期图片）：
        #: 节流与批大小在 libs/images.py，每个进程独立计数。
        @app.before_request
        def _purge_expired_images():
            sweep_expired()

    @app.after_request
    def _attach_request_id(response):
        response.headers["X-Request-Id"] = getattr(g, "request_id", "")
        return response

    @app.after_request
    def _security_headers(response):
        #: 对所有响应都成立的三项；CSP 不在这里统一加：Swagger UI 从 CDN 取
        #: 脚本、前端构建产物里也有内联样式，全局策略会把它们一起挡掉。
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
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
