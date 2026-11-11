# -*- coding: utf-8 -*-
"""Public image delivery: ``/raw/<sha>``.

Public images normally link straight to the storage backend, so this endpoint
is the canonical fallback: local replicas are streamed with range support,
world-readable backends are redirected, and private images are authorised by
sapic first (remote ones are relayed, never redirected, so the origin URL is not
exposed). Objects on a ``private`` backend are never linked directly: the driver
signs a temporary read address (``upimg_url``) and sapic relays the body.
"""

from __future__ import annotations

import logging

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
from ..libs.hotlink import HOTLINK_BLOCK, HOTLINK_PASS, hotlink_verdict
from ..libs.images import (
    REMOTE_CHUNK_SIZE,
    can_view,
    effective_visibility,
    open_remote,
)
from ..libs.storage import local_path, object_url, public_src, replicas_for
from ..models import Image
from ..models.album import VISIBILITY_PUBLIC
from ..models.image import live_condition

logger = logging.getLogger(__name__)

bp = Blueprint("public", __name__)

#: Objects behind a sha URL never change; private ones may only live in the
#: browser cache, never in a shared one.
CACHE_SECONDS = 31536000


def _cached(response, public: bool, protected: bool = False):
    cache = response.cache_control
    cache.max_age = CACHE_SECONDS
    cache.immutable = True
    if protected:
        #: 防盗链判定依赖 Referer，共享缓存必须按它分区，否则一次命中就绕过校验。
        cache.private = True
        response.vary.add("Referer")
    elif public:
        cache.public = True
    else:
        cache.private = True
    return response


def _denied():
    """Hotlink rejection: ``/raw`` normally caches for a year, a 403 never does."""
    response = Response(status=403, content_type="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "no-store"
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


def _proxy(
    url: str,
    mime: str,
    headers: dict | None = None,
    allow_private: bool = False,
):
    request_headers = dict(headers or {})
    if request.headers.get("Range"):
        request_headers["Range"] = request.headers["Range"]
    remote = open_remote(
        url, headers=request_headers, allow_private=allow_private
    )
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


def _relay(url: str, mime: str, headers: dict | None = None):
    """Relay a backend object; ``None`` when it refuses so the next replica runs."""
    try:
        return _proxy(url, mime, headers, allow_private=True)
    except ApiError:
        #: 不打 URL：私有桶的读地址是带签名的临时地址。
        logger.warning("storage relay failed, trying the next replica")
        return None


@bp.get("/raw/<sha>")
def image(sha: str):
    #: 过期图片在清理任务跑之前也必须 404，不能继续对外输出。
    row = Image.get_or_none((Image.sha == sha) & live_condition())
    if row is None:
        raise ApiError("image not found", ErrorCode.NOT_FOUND, 404)
    if not can_view(current_user(), row):
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    public = effective_visibility(row) == VISIBILITY_PUBLIC
    #: 防盗链只对公开图生效：私有图已经过 can_view，且跨站引用带不上会话 Cookie。
    verdict = hotlink_verdict(row, public)
    if verdict == HOTLINK_BLOCK:
        return _denied()
    protected = verdict == HOTLINK_PASS
    #: 外链登记：公开图交给浏览器直连源站，私有图由 sapic 转发（不暴露源站）。
    if row.source_url:
        if public:
            return redirect(row.source_url)
        return _cached(_proxy(row.source_url, row.mime), public=False)
    replicas = replicas_for(row)
    #: 本地副本最便宜：Range 与缓存都由 send_file 处理，不必走网络。
    for replica in replicas:
        path = local_path(replica)
        if path is not None:
            return _cached(send_file(path, conditional=True), public, protected)

    #: 远程副本按优先级尝试，某个失败就换下一个（旧实现失败即 404）。
    #: 公开桶：公开图直接 302 到直链；私有图由 sapic 转发隐藏源站。
    #: 私有桶：直链会 403，只能问驱动要临时读地址后再转发。
    for replica in replicas:
        direct = public_src(replica)
        if direct is not None:
            if public:
                return redirect(direct)
            response = _relay(direct, row.mime)
        else:
            signed = object_url(replica)
            if signed is None:
                continue
            response = _relay(signed["url"], row.mime, signed["headers"])
        if response is not None:
            return _cached(response, public=False)

    raise ApiError("image data is unavailable", ErrorCode.NOT_FOUND, 404)


#: 历史别名：头像等已入库的 URL 存的是 ``/i/<sha>``，保留它避免旧链接 404。
bp.add_url_rule("/i/<sha>", endpoint="legacy_image", view_func=image)
