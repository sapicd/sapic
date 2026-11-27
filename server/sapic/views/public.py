# -*- coding: utf-8 -*-
"""Public image delivery: ``/raw/<sha>``.

With ``link_mode=raw`` (the default) this endpoint is the single published
address of every image, so the site-wide access rules — rate limit, IP control
and hotlink protection — cover all of them. Public replicas on a world-readable
backend are redirected (``302``, never cached, because the target may change);
local replicas are streamed with range support; ``private`` backends get a
server-signed temporary address (``upimg_url``) that sapic relays, so the origin
URL never reaches the browser.

``link_mode=direct`` restores the older behaviour for public images (the bucket
link is published directly); this endpoint stays the fallback for the rest.
"""

from __future__ import annotations

import json
import logging
from os.path import splitext
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    redirect,
    request,
    send_file,
    stream_with_context,
)

from ..basis.common import as_bool
from ..basis.errors import ApiError, ErrorCode
from ..libs.access import ip_allowed
from ..libs.auth import current_user
from ..libs.cache import RAW_KEY, get_cache
from ..libs.hotlink import HOTLINK_BLOCK, HOTLINK_PASS, hotlink_verdict
from ..libs.images import (
    REMOTE_CHUNK_SIZE,
    can_view,
    effective_visibility,
    open_remote,
)
from ..libs.storage import (
    local_path,
    object_url,
    public_src,
    replicas_for,
    thumb_suffix,
)
from ..models import Image
from ..models.album import VISIBILITY_PUBLIC
from ..models.image import live_condition

logger = logging.getLogger(__name__)

bp = Blueprint("public", __name__)

#: Objects behind a sha URL never change; private ones may only live in the
#: browser cache, never in a shared one.
CACHE_SECONDS = 31536000
#: How long a resolved public target (local path / redirect) may be reused.
#: Short on purpose: disabling a backend or deleting a file must take effect
#: quickly even though invalidations also happen on write.
TARGET_TTL = 30


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
    """Access rejection: ``/raw`` normally caches for a year, a 403 never does."""
    response = Response(status=403, content_type="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "no-store"
    return response


def _redirect(url: str):
    """Temporary redirect to a bucket link, never stored by any cache.

    The target depends on the current replica list and on the hotlink decision,
    so caching the ``302`` would freeze a decision that must be re-evaluated on
    the next request (and would let a blocked referer keep the old target).
    """
    response = redirect(url, code=302)
    response.headers["Cache-Control"] = "no-store"
    return response


def _is_svg(row) -> bool:
    """Whether these bytes are SVG, the one image format that runs scripts."""
    if (row.mime or "").lower() == "image/svg+xml":
        return True
    return splitext(row.filename or "")[-1].lower() == ".svg"


def _as_download(response):
    """Serve a scriptable payload as a download, never inline on this origin.

    Browsers execute ``<script>`` inside a same-origin SVG document, so an
    upload that predates the default whitelist change (or a site that put
    ``svg`` back) must not be rendered here. ``nosniff`` keeps the browser from
    guessing its way back to an image type.
    """
    response.headers["Content-Type"] = "application/octet-stream"
    response.headers["Content-Disposition"] = "attachment"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _served(response, svg: bool):
    return _as_download(response) if svg else response


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


def _media_type(remote_type: str, fallback: str, media_only: bool) -> str:
    """Pick the ``Content-Type`` a relayed body is served with.

    ``media_only`` is for bytes nobody vetted (an imported external link):
    whatever the origin claims, only image/video types may be rendered, so a
    ``text/html`` (or a mislabelled) answer cannot become script/html on this
    origin. Storage relays keep the origin type, since we stored those bytes.
    """
    fallback = (fallback or "").lower()
    if not media_only:
        return remote_type or fallback or "application/octet-stream"
    if remote_type.startswith(("image/", "video/")):
        return remote_type
    if fallback.startswith(("image/", "video/")):
        return fallback
    return "application/octet-stream"


def _proxy(
    url: str,
    mime: str,
    headers: dict | None = None,
    allow_private: bool = False,
    media_only: bool = False,
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
        content_type=_media_type(
            (remote.headers.get_content_type() or "").lower(), mime, media_only
        ),
    )
    for header in ("Content-Length", "Content-Range"):
        value = remote.headers.get(header)
        if value:
            response.headers[header] = value
    if media_only:
        #: 类型已被改写，别让浏览器再嗅探回去。
        response.headers["X-Content-Type-Options"] = "nosniff"
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


def _targets(row, public: bool, thumb: bool):
    """Yield what to serve, in read order (backend priority).

    A local replica wins immediately; otherwise each remote replica is offered
    in turn so a broken one falls through to the next (the relay failure of one
    bucket must not 404 an image that has another healthy copy). ``object_url``
    is only asked when that replica is actually reached, which keeps a signing
    round-trip out of the common path.
    """
    replicas = replicas_for(row)
    #: 本地副本最便宜：Range 与缓存都由 send_file 处理，不必走网络。
    for replica in replicas:
        path = local_path(replica)
        if path is not None:
            yield {"kind": "local", "path": str(path)}
            return
    for replica in replicas:
        direct = public_src(replica)
        if direct is not None:
            if thumb:
                direct = direct + thumb_suffix(replica.backend)
            #: 公开桶：公开图直接 302 到直链；私有图由 sapic 转发隐藏源站。
            if public:
                yield {"kind": "redirect", "url": direct}
                return
            yield {"kind": "relay", "url": direct}
            continue
        #: 私有桶：直链会 403，只能问驱动要临时读地址后再转发。
        signed = object_url(replica)
        if signed is None:
            continue
        yield {
            "kind": "relay",
            "url": signed["url"],
            "headers": signed["headers"],
        }


def _serve_target(target: dict, row, svg: bool, public: bool, protected: bool):
    kind = target.get("kind")
    if kind == "local":
        path = target.get("path") or ""
        if not path or not Path(path).is_file():
            return None
        return _cached(
            _served(send_file(path, conditional=True), svg), public, protected
        )
    if kind == "redirect":
        return _redirect(target["url"])
    if kind == "relay":
        response = _relay(target["url"], row.mime, target.get("headers"))
        if response is None:
            return None
        return _cached(_served(response, svg), public=False)
    return None


def _cached_target(key: str) -> dict | None:
    """A previously resolved target, when it is still usable.

    Cached entries are only ``local`` and ``redirect``: both are decided without
    touching a bucket, and a stale local path is detected by the file check in
    :func:`_serve_target`.
    """
    raw = get_cache().get(key)
    if not raw:
        return None
    try:
        target = json.loads(raw)
    except ValueError:
        get_cache().delete(key)
        return None
    return target if isinstance(target, dict) else None


@bp.get("/raw/<sha>")
def image(sha: str):
    #: IP 规则最便宜，放在最前面：被挡的请求连一次数据库查询都不做。
    if not ip_allowed():
        return _denied()

    #: 过期图片在清理任务跑之前也必须 404，不能继续对外输出。
    row = Image.get_or_none((Image.sha == sha) & live_condition())
    if row is None:
        raise ApiError("image not found", ErrorCode.NOT_FOUND, 404)
    if not can_view(current_user(), row):
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    public = effective_visibility(row) == VISIBILITY_PUBLIC
    #: SVG 不能在本站源下当文档渲染，否则其中的脚本会以同源身份执行。
    svg = _is_svg(row)
    #: 防盗链只对公开图生效：私有图已经过 can_view，且跨站引用带不上会话 Cookie。
    verdict = hotlink_verdict(row, public)
    if verdict == HOTLINK_BLOCK:
        return _denied()
    protected = verdict == HOTLINK_PASS
    #: 列表页缩略图：参数跟在 /raw 上，302 目标由后端后缀决定。
    thumb = as_bool(request.args.get("thumb"))
    #: 外链登记：公开图交给浏览器直连源站，私有图由 sapic 转发（不暴露源站）。
    if row.source_url:
        if public:
            return _redirect(row.source_url)
        #: 源站字节没人校验过，只按图片/视频类型转发（见 ``_media_type``）。
        return _cached(
            _served(
                _proxy(row.source_url, row.mime, media_only=True), svg
            ),
            public=False,
        )

    cache_key = RAW_KEY % (sha, 1 if thumb else 0)
    target = _cached_target(cache_key) if public else None
    if target is not None:
        cached = _serve_target(target, row, svg, public, protected)
        if cached is not None:
            return cached
        #: 目标已不可用（本地文件被删、后端换过）：丢掉缓存重新解析一次。
        get_cache().delete(cache_key)

    for target in _targets(row, public, thumb):
        response = _serve_target(target, row, svg, public, protected)
        if response is None:
            continue
        #: 只缓存不依赖远端请求的决策：relay 每次都要重新取签名地址。
        if public and target.get("kind") in ("local", "redirect"):
            get_cache().set(cache_key, json.dumps(target), TARGET_TTL)
        return response

    raise ApiError("image data is unavailable", ErrorCode.NOT_FOUND, 404)


#: 历史别名：头像等已入库的 URL 存的是 ``/i/<sha>``，保留它避免旧链接 404。
bp.add_url_rule("/i/<sha>", endpoint="legacy_image", view_func=image)
