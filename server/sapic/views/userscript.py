# -*- coding: utf-8 -*-
"""Uploader userscript delivery (``/api/v2/userscript.user.js``).

It lives under the API prefix so one reverse-proxy rule (``/api/``) is enough;
managers only care about the ``.user.js`` suffix. The body is script rather than
the usual JSON envelope, and authentication happens in the view (see below).
"""

from __future__ import annotations

from flask import Blueprint, Response, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.auth import current_user
from ..libs.user_settings import user_setting
from ..libs.userscript import build_userscript

bp = Blueprint("userscript", __name__)


@bp.get("/userscript.user.js")
def script():
    """Serve the uploader script for the personal switch.

    Authenticated by session cookie or by ``?token=`` with the ``upload`` scope
    (installers cannot set headers). ``login_required`` is not used on purpose:
    a GET would demand ``read``, while the installer only needs ``upload``.

    The body embeds no credential, so turning the switch off really revokes
    access: further install/update requests get 404.
    """
    user = current_user()
    if user is None:
        raise ApiError("authentication required", ErrorCode.UNAUTHORIZED, 401)
    if not user_setting(user, "userscript_enabled", False):
        raise ApiError("userscript is disabled", ErrorCode.NOT_FOUND, 404)

    body = build_userscript(request.url_root, request.host, user.username)
    response = Response(body, mimetype="text/javascript")
    #: 开关随时可能关掉，装脚本的人不该拿到缓存副本。
    response.headers["Cache-Control"] = "no-store"
    return response
