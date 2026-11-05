# -*- coding: utf-8 -*-
"""Public image delivery: ``/raw/<sha>``.

Public images normally link straight to the storage backend, so this endpoint
is the canonical fallback: local replicas are streamed with range support,
backends without a public domain are redirected, and private images are
authorised by sapic first (remote ones are relayed, never redirected, so the
origin URL is not exposed).
"""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    redirect,
    request,
    send_file,
    stream_with_context,
)

from ..basis.errors import ApiError, ErrorCode
from ..libs.auth import current_user
from ..libs.images import (
    REMOTE_CHUNK_SIZE,
    can_view,
    effective_visibility,
    open_remote,
)
from ..libs.storage import local_path, replicas_for
from ..models import Image
from ..models.album import VISIBILITY_PUBLIC
from ..models.image import STATUS_ENABLED

bp = Blueprint("public", __name__)

#: Objects behind a sha URL never change; private ones may only live in the
#: browser cache, never in a shared one.
CACHE_SECONDS = 31536000


def _cached(response, public: bool):
    cache = response.cache_control
    cache.max_age = CACHE_SECONDS
    cache.immutable = True
    if public:
        cache.public = True
    else:
        cache.private = True
    return response


def _body(response):
    """Relay a remote body chunk by chunk and close it when done."""
    try:
        while True:
            chunk = response.read(REMOTE_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        response.close()


def _proxy(url: str, mime: str):
    headers = {}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]
    remote = open_remote(url, headers=headers)
    response = Response(
        stream_with_context(_body(remote)),
        status=remote.status,
        content_type=(
            remote.headers.get_content_type()
            or mime
            or "application/octet-stream"
        ),
    )
    for header in ("Content-Length", "Content-Range"):
        value = remote.headers.get(header)
        if value:
            response.headers[header] = value
    response.headers["Accept-Ranges"] = "bytes"
    return response


@bp.get("/raw/<sha>")
def image(sha: str):
    row = Image.get_or_none(
        (Image.sha == sha) & (Image.status == STATUS_ENABLED)
    )
    if row is None:
        raise ApiError("image not found", ErrorCode.NOT_FOUND, 404)
    if not can_view(current_user(), row):
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    public = effective_visibility(row) == VISIBILITY_PUBLIC
    #: 外链登记：公开图交给浏览器直连源站，私有图由 sapic 转发（不暴露源站）。
    if row.source_url:
        if public:
            return redirect(row.source_url)
        return _cached(_proxy(row.source_url, row.mime), public=False)
    for replica in replicas_for(row):
        path = local_path(replica)
        if path is not None:
            return _cached(send_file(path, conditional=True), public)
        if not replica.url:
            continue
        if public:
            return redirect(replica.url)
        return _cached(_proxy(replica.url, row.mime), public=False)

    raise ApiError("image data is unavailable", ErrorCode.NOT_FOUND, 404)


#: 历史别名：头像等已入库的 URL 存的是 ``/i/<sha>``，保留它避免旧链接 404。
bp.add_url_rule("/i/<sha>", endpoint="legacy_image", view_func=image)
