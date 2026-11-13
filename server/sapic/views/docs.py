# -*- coding: utf-8 -*-
"""Interactive API documentation.

``/openapi.json`` serves the generated document (see :mod:`sapic.libs.openapi`)
and ``/docs`` renders it with Swagger UI, so the "try it out" buttons talk to
this very instance. The UI assets come from a public CDN: on an intranet the
page falls back to a link to the JSON, which can still be imported into
Apifox / Postman.
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, url_for

from ..libs.openapi import build_spec

bp = Blueprint("docs", __name__)

#: Swagger UI 静态资源基地址（锁定版本，避免上游发版改变页面行为）；
#: 内网或想避免第三方脚本时改成自建目录即可。
SWAGGER_UI_BASE = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.11.0"

#: 路由在启动时就固定了，文档只在进程内构建一次。
_SPEC_KEY = "sapic_openapi_spec"

_PAGE = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>sapic API 文档</title>
    <link rel="stylesheet" href="__UI_BASE__/swagger-ui.css" />
    <style>
      body { margin: 0; background: #fafafa; }
      .docs-fallback { font: 14px/1.7 system-ui, sans-serif; padding: 24px; }
      .docs-fallback code { background: #eee; padding: 2px 6px; border-radius: 4px; }
    </style>
  </head>
  <body>
    <div id="swagger-ui"></div>
    <div id="docs-fallback" class="docs-fallback" hidden>
      <p>无法从 CDN 加载 Swagger UI（内网环境常见）。</p>
      <p>
        文档源仍然可用：<a href="__SPEC_URL__">__SPEC_URL__</a>，
        可直接导入 Apifox / Postman / Insomnia。
      </p>
    </div>
    <script src="__UI_BASE__/swagger-ui-bundle.js"></script>
    <script>
      (function () {
        var fallback = document.getElementById('docs-fallback')
        if (!window.SwaggerUIBundle) {
          fallback.hidden = false
          return
        }
        var csrf = ''
        //: Cookie 会话的写操作要 CSRF 头（PAT 鉴权不需要），先取一次再同步补上。
        fetch('__SESSION_URL__', { credentials: 'same-origin' })
          .then(function (res) { return res.json() })
          .then(function (body) { csrf = (body && body.data && body.data.csrf) || '' })
          .catch(function () {})
        window.ui = window.SwaggerUIBundle({
          url: '__SPEC_URL__',
          dom_id: '#swagger-ui',
          deepLinking: true,
          persistAuthorization: true,
          withCredentials: true,
          requestInterceptor: function (req) {
            if (csrf && req.method !== 'GET') req.headers['X-CSRF-Token'] = csrf
            return req
          },
        })
      })()
    </script>
  </body>
</html>
"""


def _spec(app) -> dict:
    spec = app.extensions.get(_SPEC_KEY)
    if spec is None:
        spec = build_spec(app)
        app.extensions[_SPEC_KEY] = spec
    return spec


@bp.get("/openapi.json")
def openapi_json():
    """OpenAPI 3.0 document; safe to import into any API client."""
    return jsonify(_spec(current_app._get_current_object()))


@bp.get("/docs")
def swagger_ui():
    """Swagger UI page bound to this instance."""
    html = (
        _PAGE.replace("__UI_BASE__", SWAGGER_UI_BASE)
        .replace("__SPEC_URL__", url_for(".openapi_json"))
        .replace("__SESSION_URL__", url_for("auth.read_session"))
    )
    return Response(html, mimetype="text/html")
