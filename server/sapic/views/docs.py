# -*- coding: utf-8 -*-
"""Interactive API documentation.

``/openapi.json`` serves the generated document (see :mod:`sapic.libs.openapi`)
and ``/docs`` renders it with Swagger UI, so the "try it out" buttons talk to
this very instance. The UI assets come from a public CDN: on an intranet the
page falls back to a link to the JSON, which can still be imported into
Apifox / Postman.
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request, url_for

from ..libs.openapi import build_spec

bp = Blueprint("docs", __name__)

#: Swagger UI 静态资源基地址（锁定版本，避免上游发版改变页面行为）；
#: 内网或想避免第三方脚本时改成自建目录即可。
SWAGGER_UI_BASE = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.11.0"

#: 路由在启动时就固定了，文档只在进程内构建一次。
_SPEC_KEY = "sapic_openapi_spec"

_PAGE = """<!doctype html>
<html lang="__HTML_LANG__">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>__TITLE__</title>
    <link rel="stylesheet" href="__UI_BASE__/swagger-ui.css" />
    <style>
      body { margin: 0; background: #fafafa; }
      .docs-lang { position: fixed; top: 10px; right: 16px; z-index: 10; font: 13px system-ui, sans-serif;
        padding: 4px 10px; border-radius: 14px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.12); }
      .docs-lang a { color: #3b6fd4; text-decoration: none; }
      .docs-lang a.is-active { color: #333; font-weight: 600; }
      .docs-fallback { font: 14px/1.7 system-ui, sans-serif; padding: 24px; }
      .docs-fallback code { background: #eee; padding: 2px 6px; border-radius: 4px; }
    </style>
  </head>
  <body>
    <nav class="docs-lang">__LANG_LINKS__</nav>
    <div id="swagger-ui"></div>
    <div id="docs-fallback" class="docs-fallback" hidden>
      <p>__FALLBACK__</p>
      <p>
        __FALLBACK_HINT__<a href="__SPEC_URL__">__SPEC_URL__</a>__FALLBACK_TAIL__
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


#: 文档只有中英两版：``?lang=en`` 取英文，其它值都按中文处理。
LANGUAGES = {"zh": "中文", "en": "English"}

#: 页面自身的文案（正文在 ``libs/openapi.py`` 里按条目翻译）。
_PAGE_TEXT = {
    "zh": {
        "html_lang": "zh-CN",
        "title": "sapic API 文档",
        "fallback": "无法从 CDN 加载 Swagger UI（内网环境常见）。",
        "hint": "文档源仍然可用：",
        "tail": "，可直接导入 Apifox / Postman / Insomnia。",
    },
    "en": {
        "html_lang": "en",
        "title": "sapic API documentation",
        "fallback": "Swagger UI could not be loaded from the CDN (common on intranets).",
        "hint": "The document itself is still available: ",
        "tail": ", and imports directly into Apifox / Postman / Insomnia.",
    },
}


def _lang() -> str:
    """Pick the document language.

    An explicit ``?lang=en|zh`` wins; otherwise follow ``Accept-Language`` so an
    English browser opening the page directly is not served Chinese; anything
    unrecognised (or missing) falls back to Chinese.
    """
    requested = (request.args.get("lang") or "").strip().lower()
    if requested in LANGUAGES:
        return requested
    if requested:
        #: 显式给了不支持的语言时不要再去猜浏览器偏好。
        return "zh"
    return request.accept_languages.best_match(list(LANGUAGES)) or "zh"


def _spec(app, lang: str) -> dict:
    #: 两种语言各构建一次，构建结果随进程存活。
    specs = app.extensions.setdefault(_SPEC_KEY, {})
    spec = specs.get(lang)
    if spec is None:
        spec = build_spec(app, lang)
        specs[lang] = spec
    return spec


def _lang_links(lang: str) -> str:
    links = []
    for code, label in LANGUAGES.items():
        active = ' class="is-active"' if code == lang else ""
        links.append(
            '<a href="%s"%s>%s</a>' % (url_for(".swagger_ui", lang=code), active, label)
        )
    return " · ".join(links)


@bp.get("/openapi.json")
def openapi_json():
    """OpenAPI 3.0 document; safe to import into any API client."""
    app = current_app._get_current_object()
    return jsonify(_spec(app, _lang()))


@bp.get("/docs")
def swagger_ui():
    """Swagger UI page bound to this instance."""
    lang = _lang()
    text = _PAGE_TEXT[lang]
    html = _PAGE
    for placeholder, value in (
        ("__UI_BASE__", SWAGGER_UI_BASE),
        ("__HTML_LANG__", text["html_lang"]),
        ("__TITLE__", text["title"]),
        ("__FALLBACK__", text["fallback"]),
        ("__FALLBACK_HINT__", text["hint"]),
        ("__FALLBACK_TAIL__", text["tail"]),
        ("__LANG_LINKS__", _lang_links(lang)),
        ("__SPEC_URL__", url_for(".openapi_json", lang=lang)),
        ("__SESSION_URL__", url_for("auth.read_session")),
    ):
        html = html.replace(placeholder, value)
    return Response(html, mimetype="text/html")
