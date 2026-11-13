# -*- coding: utf-8 -*-
"""Image lifecycle: create, publish, query, delete."""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
from contextlib import closing
from datetime import datetime
from hashlib import sha1
from http.client import HTTPException
from mimetypes import guess_type
from os.path import splitext
from posixpath import basename as posix_basename
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from uuid import uuid4

from flask import current_app, url_for
from peewee import JOIN, SQL, fn
from werkzeug.utils import secure_filename

from ..basis.db import db
from ..basis.errors import ApiError, ErrorCode
from ..models import Album, AlbumShare, Image, ImageBackend, StorageBackend
from ..models.album import VISIBILITY_PUBLIC
from ..models.base import now
from ..models.image import (
    STATUS_DELETED,
    STATUS_ENABLED,
    live_condition,
    not_expired,
)
from ..models.storage import STATE_OK
from ..utils.common import parse_proxy_url
from .albums import resolve_album, share_for
from .hook import get_hook_manager
from .media import image_size, strip_metadata
from .settings import get_setting
from .storage import (
    delete_object,
    driver_backend,
    list_backends,
    public_src,
    queue_replicas,
    replicas_for,
    save_object,
    thumb_suffix,
)

logger = logging.getLogger(__name__)

#: 有效期按天配置：``0`` 表示不启用该规则（默认永久 / 不限制上限）。
EXPIRE_DEFAULT_KEY = "image_expire_default_days"
EXPIRE_MAX_KEY = "image_expire_max_days"
DAY_SECONDS = 86400

#: 到期清理节流：每个进程最多每 5 分钟扫一次，单次最多删 200 张。
SWEEP_INTERVAL = 300
SWEEP_BATCH = 200
#: 上次清理的 monotonic 时刻；``None`` 表示本进程还没扫过（首个请求必扫）。
#: 别改回 ``0.0`` 这类哨兵：``monotonic()`` 在刚启动的机器上可能小于节流窗口。
_last_sweep: float | None = None

IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".ico",
    ".svg",
}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".avi"}

#: Tag limits; keep them small, tags are labels rather than a taxonomy.
MAX_TAGS = 10
MAX_TAG_LENGTH = 32


def normalize_tags(values) -> list[str]:
    """Clean a tag list: strip, drop blanks, de-duplicate (case-insensitive)."""
    if values is None:
        return []
    if isinstance(values, str):
        values = values.split(",")
    if not isinstance(values, (list, tuple)):
        raise ApiError("tags must be a list", ErrorCode.PARAM_ERROR)

    tags: list[str] = []
    seen: set[str] = set()
    for item in values:
        name = str(item or "").strip()
        if not name:
            continue
        if len(name) > MAX_TAG_LENGTH:
            raise ApiError(
                "tag must be at most %d characters" % MAX_TAG_LENGTH,
                ErrorCode.PARAM_ERROR,
            )
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(name)
    if len(tags) > MAX_TAGS:
        raise ApiError("at most %d tags" % MAX_TAGS, ErrorCode.PARAM_ERROR)
    return tags


def make_sha(filename: str) -> str:
    """Keep the v1 ``sha1.<timestamp>.<hash>`` shape."""
    timestamp = now()
    digest = sha1(
        ("%s:%s:%s" % (filename, timestamp, uuid4().hex)).encode("utf-8")
    ).hexdigest()
    return "sha1.%s.%s" % (timestamp, digest)


def upload_path_for(owner) -> str:
    today = datetime.now()
    username = getattr(owner, "username", None) or "anonymous"
    return "%s/%04d/%02d/%02d" % (
        username,
        today.year,
        today.month,
        today.day,
    )


def public_url(sha: str) -> str:
    path = url_for("public.image", sha=sha)
    base = (current_app.config.get("EXTERNAL_BASE_URL") or "").rstrip("/")
    return "%s%s" % (base, path) if base else path


def tag_condition(tag: str):
    """Match one element of the JSON tag array exactly.

    Tags live in a TEXT column, so a quoted substring match is the portable
    way to do this; ``JSONTextField.db_value`` would re-encode a plain
    ``contains`` pattern, hence the raw SQL fragment.
    """
    pattern = "%" + json.dumps(tag, ensure_ascii=False) + "%"
    return SQL("tags LIKE ?", (pattern,))


def image_src(
    image: Image,
    album: Album | None = None,
    replicas: list[ImageBackend] | None = None,
) -> str:
    """Direct link for public images, stable ``/raw/<sha>`` for the rest.

    Public payloads link to the highest priority replica whose backend is
    world-readable, which keeps sapic out of the data path; private images — and
    every image living on a ``private`` backend — must stay behind ``/raw/<sha>``
    so the visibility check keeps applying.
    """
    if album is None:
        album = image.album
    visibility = image.visibility or (
        album.visibility if album is not None else VISIBILITY_PUBLIC
    )
    if visibility == VISIBILITY_PUBLIC:
        #: 外链登记的图片字节不在 sapic，公开图直接指向源站。
        if image.source_url:
            return image.source_url
        rows = replicas if replicas is not None else replicas_for(image)
        #: 仍然只看优先级最高的副本（与 /raw 的输出顺序一致）；但它若在私有桶里，
        #: 匿名请求会 403，这种情况回落到 /raw，而不是借用低优先级副本的直链。
        if rows:
            src = public_src(rows[0])
            if src:
                return src
    return public_url(image.sha)


def image_thumb(
    image: Image,
    album: Album | None = None,
    replicas: list[ImageBackend] | None = None,
    src: str | None = None,
) -> str | None:
    """``src`` rewritten through the backend's image-processing suffix.

    Only a direct link can be rewritten: ``/raw/<sha>`` is sapic's own route and
    ``source_url`` points at another site, so neither can carry the bucket's
    parameters. Visibility is left entirely to :func:`image_src` — comparing the
    result with the top replica keeps both in lockstep instead of repeating the
    album/override rules here.
    """
    if image.is_video:
        return None
    if src is None:
        src = image_src(image, album, replicas)
    rows = replicas if replicas is not None else replicas_for(image)
    if not src or not rows or src != public_src(rows[0]):
        return None
    suffix = thumb_suffix(rows[0].backend)
    return "%s%s" % (src, suffix) if suffix else None


def share_templates(
    src: str, filename: str = "", title: str = "", is_video: bool = False
) -> dict:
    """Copy-paste snippets, mirroring v1's ``gen_url_tpl`` output.

    The keys (``URL`` / ``HTML`` / ``Markdown`` / ``rST``) are part of the v1
    contract, so an old template or script keeps working. Video Markdown/rST
    use a ``<figure><iframe>`` like v1 did, because Markdown has no video syntax.
    """
    if is_video:
        frame = (
            "<figure><iframe src='%s' frameborder=0 "
            "allow='allowfullscreen'></iframe></figure>" % src
        )
        return {
            "URL": src,
            "HTML": "<video src='%s' title='%s' controls></video>" % (src, title),
            "rST": ".. raw:: html\n\n\t%s" % frame,
            "Markdown": frame,
        }
    return {
        "URL": src,
        "HTML": "<img src='%s' title='%s' alt='%s'>" % (src, title, filename),
        "rST": ".. image:: %s" % src,
        "Markdown": "![%s](%s)" % (filename, src),
    }


def serialize_image(
    image: Image,
    album: Album | None = None,
    replicas: list[ImageBackend] | None = None,
    with_thumb: bool = False,
) -> dict:
    src = image_src(image, album, replicas)
    return {
        "sha": image.sha,
        "filename": image.filename,
        "title": image.title,
        "size": image.size,
        "mime": image.mime,
        "is_video": bool(image.is_video),
        #: 上传时从文件头解析，外链登记与不可解析的载荷为 NULL。
        "width": image.width,
        "height": image.height,
        "visibility": image.visibility,
        #: NULL means "follow the album"; the effective value is for display.
        "plaza": image.plaza,
        "plaza_effective": effective_plaza(image, album),
        "tags": list(image.tags or []),
        "album_id": image.album_id,
        "album": (
            {
                "id": album.id,
                "name": album.name,
                "visibility": album.visibility,
            }
            if album is not None
            else None
        ),
        "created_at": image.created_at,
        "expire_at": image.expire_at,
        #: 外链登记（未下载）的图片，UI 据此打标并提示删除不影响源站。
        "external": bool(image.source_url),
        "src": src,
        #: 列表页的缩略图直链：只有公开直链且后端配了处理后缀时才有值。
        #: ``src`` / ``tpl`` 始终是原图，分享出去的链接不能被缩小。
        "thumb": image_thumb(image, album, replicas, src=src) if with_thumb else None,
        #: 详情页的「分享代码」区块；模板里的地址就是上面的 src。
        "tpl": share_templates(
            src,
            filename=image.filename,
            title=image.title or "",
            is_video=bool(image.is_video),
        ),
    }


def album_serializer():
    """Serializer for image lists, plus a batch prefetch for its relations.

    Pass ``prefetch`` to :func:`sapic.utils.web.paginate` so a page costs a
    constant number of queries instead of two per row.
    """
    albums: dict[int, Album | None] = {}
    replicas: dict[int, list[ImageBackend]] = {}

    def prefetch(rows: list[Image]) -> None:
        ids = [row.id for row in rows]
        if not ids:
            return
        for album_id in {row.album_id for row in rows if row.album_id}:
            albums[album_id] = Album.get_or_none(Album.id == album_id)
        for replica in (
            ImageBackend.select(ImageBackend, StorageBackend)
            .join(StorageBackend)
            .where(
                (ImageBackend.image.in_(ids))
                & (ImageBackend.state == STATE_OK)
                & (StorageBackend.enabled == True)  # noqa: E712
            )
            .order_by(StorageBackend.priority, ImageBackend.id)
        ):
            replicas.setdefault(replica.image_id, []).append(replica)

    def serialize(image: Image) -> dict:
        if image.album_id and image.album_id not in albums:
            albums[image.album_id] = Album.get_or_none(Album.id == image.album_id)
        #: 列表页与广场共用这个序列化器，缩略图只在这里输出；详情页与上传
        #: 响应走 ``serialize_image`` 的默认参数，只给原图。
        return serialize_image(
            image,
            albums.get(image.album_id),
            replicas.get(image.id),
            with_thumb=True,
        )

    return serialize, prefetch


#: Remote fetches are http(s) only, hop-validated and size/time bounded, so the
#: endpoint cannot be used as a proxy into the intranet.
REMOTE_TIMEOUT = 10
REMOTE_MAX_REDIRECTS = 3
REMOTE_CHUNK_SIZE = 64 * 1024
REMOTE_USER_AGENT = "sapic/url-fetch"

#: 站点设置：URL 上传的服务端抓取直连失败后改走的代理（单个 http(s) 地址）。
UPLOAD_FETCH_PROXY_KEY = "upload_fetch_proxy"

#: Content-Type 兜底：URL 里没有可用后缀时按响应头补一个，供后缀白名单校验。
MIME_EXTS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/x-msvideo": ".avi",
}


class _NoRedirect(HTTPRedirectHandler):
    """Surface 3xx as ``HTTPError`` so every redirect hop gets validated."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _is_private_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Whether an address belongs to a range we never let a user URL reach."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _host_visibility(hostname: str) -> bool | None:
    """``True`` public, ``False`` loopback/private/link-local, ``None`` unknown.

    Only meaningful for direct fetches, where the local resolver is the one that
    will connect. ``None`` means "cannot resolve here", which is exactly the
    case a proxy is configured for, so the caller may retry through it.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return None
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if _is_private_address(address):
            return False
    return bool(infos)


def _is_public_literal(hostname: str) -> bool:
    """No-DNS check for proxied fetches.

    The proxy resolves and connects, so the local resolver is irrelevant (and
    often poisoned for the very sites a proxy is configured for). Only plain IP
    literals can still be judged here: private ones stay blocked, names are
    handed to the proxy as-is.
    """
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return True
    return not _is_private_address(address)


def fetch_proxy() -> str:
    """Proxy used when a direct fetch fails; empty means no proxy configured.

    A malformed value is only logged: settings are validated on write, so a bad
    value here means someone edited the table directly, and uploads must keep
    working (direct) instead of failing on every URL fetch.
    """
    raw = str(get_setting(UPLOAD_FETCH_PROXY_KEY, "") or "")
    try:
        return parse_proxy_url(raw)
    except ValueError as exc:
        logger.warning("ignore invalid %s: %s", UPLOAD_FETCH_PROXY_KEY, exc)
        return ""


class _Unreachable(Exception):
    """An attempt another transport may still get through.

    Besides transport errors (DNS, connect, TLS, timeout) this also covers an
    HTTP error status and an unusable payload: a blocked or intercepted host
    often answers with 403 from an edge node, or with a 200 that carries an HTML
    interstitial instead of the image. The configured proxy is the escape hatch
    for exactly those cases, so they must reach the fallback instead of failing
    the upload. Policy errors (private address, bad scheme, redirect loop) stay
    ``ApiError``: no transport is allowed to fetch them.
    """

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        #: Short machine-readable cause, surfaced in the API error message.
        self.reason = reason


def _open_once(
    url: str,
    timeout: int,
    headers: dict | None,
    allow_private: bool,
    proxy: str,
):
    """Run the redirect chain over one transport (``proxy`` empty = direct)."""
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    opener = build_opener(_NoRedirect(), ProxyHandler(proxies))
    target = url
    for _ in range(REMOTE_MAX_REDIRECTS + 1):
        parsed = urlparse(target)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ApiError("only http(s) url is supported", ErrorCode.PARAM_ERROR)
        if not allow_private:
            if proxy:
                #: 走代理时由代理解析与连接，本地 DNS 结论不可信（外网域名常解析
                #: 失败或被污染），只对 IP 字面量做内网拦截。
                if not _is_public_literal(parsed.hostname):
                    raise ApiError("url host is not allowed", ErrorCode.FORBIDDEN, 403)
            else:
                visibility = _host_visibility(parsed.hostname)
                if visibility is None:
                    #: 本地解析不了（外网域名常见）就交给代理兜底；没配代理时
                    #: 这一跳会对上层表现为「抓取失败」。
                    raise _Unreachable("cannot resolve %s" % parsed.hostname)
                if not visibility:
                    raise ApiError("url host is not allowed", ErrorCode.FORBIDDEN, 403)
        request_headers = {
            "User-Agent": REMOTE_USER_AGENT,
            "Accept": "image/*,video/*",
        }
        request_headers.update(headers or {})
        try:
            return opener.open(
                Request(target, headers=request_headers), timeout=timeout
            )
        except HTTPError as exc:
            location = exc.headers.get("Location")
            code = exc.code
            exc.close()
            if code in (301, 302, 303, 307, 308) and location:
                target = urljoin(target, location)
                continue
            #: 4xx/5xx 也可能是「这一跳被挡了」（反爬、地区限制），换代理再试。
            raise _Unreachable("http %s" % code) from exc
        except (URLError, OSError, ValueError) as exc:
            raise _Unreachable("network error", str(exc)) from exc
    raise ApiError("too many redirects", ErrorCode.PARAM_ERROR)


def _with_proxy_fallback(attempt, allow_private: bool = False):
    """Run ``attempt(proxy)`` directly first, then once through the proxy.

    The proxy is a fallback, not a default route: a reachable source never pays
    for the detour. ``_Unreachable`` means "this transport produced nothing
    usable"; anything else (bad scheme, private address, oversize payload) is a
    final answer and is never retried. Internal backend URLs
    (``allow_private``) stay on the direct path only.
    """
    proxy = "" if allow_private else fetch_proxy()
    try:
        return attempt("")
    except _Unreachable as exc:
        if not proxy:
            raise ApiError(
                "remote fetch failed: %s" % exc.reason, ErrorCode.PARAM_ERROR
            ) from exc
        logger.info("direct url fetch failed (%s), retrying via proxy", exc.reason)
    try:
        return attempt(proxy)
    except _Unreachable as exc:
        raise ApiError(
            "remote fetch failed: %s" % exc.reason, ErrorCode.PARAM_ERROR
        ) from exc


def open_remote(
    url: str,
    timeout: int = REMOTE_TIMEOUT,
    headers: dict | None = None,
    allow_private: bool = False,
):
    """Open an http(s) URL for streaming.

    Redirects are validated hop by hop, so the caller must close the returned
    response when done. ``allow_private`` is for addresses the server produced
    itself (a storage backend read URL): a self-hosted MinIO on ``10.x`` has to
    work there. Never pass it for user supplied URLs — that is the SSRF guard.

    A user supplied URL is fetched directly first; the configured proxy only
    gets a second chance when that attempt produced nothing usable (network
    error or HTTP error status), so reachable sources never pay for the detour.
    Internal backend URLs never take that path at all.
    """

    def attempt(proxy_url: str):
        return _open_once(url, timeout, headers, allow_private, proxy_url)

    return _with_proxy_fallback(attempt, allow_private)


def _read_media(
    url: str, max_bytes: int, timeout: int, proxy: str
) -> tuple[bytes, str, str]:
    """Download and validate one payload over one transport.

    A body that breaks off mid-transfer is reported as ``_Unreachable`` too: the
    direct path often gets a valid ``200`` header and then has the connection
    reset, and that is exactly the case where the proxy has to take over.
    """
    response = _open_once(url, timeout, None, False, proxy)
    parsed = urlparse(response.geturl() or url)
    mime = (response.headers.get_content_type() or "").lower()
    if not mime.startswith(("image/", "video/")):
        response.close()
        #: 被墙/反爬时常见 200 + text/html 的拦截页，这种响应「拿得到但用不了」。
        raise _Unreachable("unexpected content type %s" % (mime or "unknown"))

    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > max_bytes:
        response.close()
        raise ApiError("file exceeds the size limit", ErrorCode.PARAM_ERROR, 413)

    chunks: list[bytes] = []
    total = 0
    with closing(response):
        try:
            while True:
                chunk = response.read(REMOTE_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ApiError(
                        "file exceeds the size limit", ErrorCode.PARAM_ERROR, 413
                    )
                chunks.append(chunk)
        except (OSError, HTTPException) as exc:
            raise _Unreachable("network error", str(exc)) from exc

    name = unquote(parsed.path.rsplit("/", 1)[-1]) or "remote"
    suffix = splitext(name)[-1].lower()
    if suffix not in IMAGE_EXTS and suffix not in VIDEO_EXTS:
        name = "%s%s" % (splitext(name)[0] or "remote", MIME_EXTS.get(mime, ""))
    return b"".join(chunks), name, mime


def download_image(
    url: str, max_bytes: int, timeout: int = REMOTE_TIMEOUT
) -> tuple[bytes, str, str]:
    """Fetch a remote payload as ``(stream, filename, mime)``."""

    def attempt(proxy_url: str):
        return _read_media(url, max_bytes, timeout, proxy_url)

    return _with_proxy_fallback(attempt)


def process_stream(
    stream: bytes, filename: str, mime: str = ""
) -> tuple[bytes, str, str]:
    """Run the ``upimg_stream_processor`` hooks on non-video payloads.

    Mirrors v1: a successful hook may replace the bytes and the suffix (e.g.
    ``pic2webp``), so the stored name and the mime follow the payload that is
    actually written. Video payloads are never processed.
    """
    suffix = splitext(filename)[-1].lower()
    if suffix in VIDEO_EXTS:
        return stream, filename, mime

    processed = stream
    #: 处理器按钩子各自的配置运行（如 pic2webp 的 quality）。
    for result in get_hook_manager().call(
        "upimg_stream_processor",
        stream=processed,
        suffix=suffix,
        with_config=True,
    ):
        data = result.get("data")
        if result.get("code") != 0 or not isinstance(data, dict):
            continue
        payload = data.get("stream")
        if not payload:
            continue
        processed = payload
        new_suffix = str(result.get("suffix") or "").lower()
        if new_suffix and new_suffix != suffix:
            filename = "%s%s" % (filename[: -len(suffix)], new_suffix)
            suffix = new_suffix
            mime = guess_type(filename)[0] or mime
    return processed, filename, mime


def expire_limit_seconds() -> int:
    """Site-wide cap for requested lifetimes; ``0`` means unlimited."""
    try:
        days = int(get_setting(EXPIRE_MAX_KEY, 0) or 0)
    except (TypeError, ValueError):
        return 0
    return days * DAY_SECONDS if days > 0 else 0


def expire_default_seconds() -> int:
    """Lifetime applied when the client does not ask for one."""
    try:
        days = int(get_setting(EXPIRE_DEFAULT_KEY, 0) or 0)
    except (TypeError, ValueError):
        days = 0
    seconds = days * DAY_SECONDS if days > 0 else 0
    limit = expire_limit_seconds()
    if not seconds:
        #: 上限本身已禁止永久图片时，未指定就按上限处理，否则规则形同虚设。
        return limit
    return min(seconds, limit) if limit else seconds


def resolve_expire_seconds(raw) -> int:
    """Validate the ``expire`` upload parameter (seconds, ``0``/empty = default).

    Returns the lifetime in seconds; ``0`` means the image never expires.
    """
    if raw in (None, "", 0, "0"):
        return expire_default_seconds()
    try:
        seconds = int(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid expire", ErrorCode.PARAM_ERROR) from exc
    if seconds <= 0:
        raise ApiError("invalid expire", ErrorCode.PARAM_ERROR)
    limit = expire_limit_seconds()
    if limit and seconds > limit:
        raise ApiError(
            "expire exceeds the site limit of %d days" % (limit // DAY_SECONDS),
            ErrorCode.PARAM_ERROR,
        )
    return seconds


def resolve_expire_at(raw) -> int | None:
    """Validate an absolute ``expire_at`` for PATCH; ``None`` clears it."""
    if raw in (None, "", 0, "0"):
        return None
    try:
        timestamp = int(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid expire_at", ErrorCode.PARAM_ERROR) from exc
    moment = now()
    #: 过去的时间等于「立即删除」，让调用方用 DELETE 表达这个意图。
    if timestamp <= moment:
        raise ApiError("expire_at must be in the future", ErrorCode.PARAM_ERROR)
    limit = expire_limit_seconds()
    if limit and timestamp > moment + limit:
        raise ApiError(
            "expire_at exceeds the site limit of %d days" % (limit // DAY_SECONDS),
            ErrorCode.PARAM_ERROR,
        )
    return timestamp


def uploads_enabled() -> bool:
    """Site-wide kill switch for *new* uploads.

    Only the upload view consults this: reading, editing, deleting existing
    images and the background replicas / purge jobs must keep working while the
    site is frozen, so do not move this check into ``create_image`` or
    ``save_object``.
    """
    return bool(get_setting("upload_enabled", True))


def anonymous_upload_allowed() -> bool:
    """Anonymous uploads are on when either the deploy flag or the site setting is."""
    if current_app.config.get("ALLOW_ANONYMOUS_UPLOAD", False):
        return True
    return bool(get_setting("allow_anonymous_upload", False))


def allowed_suffixes() -> set[str]:
    """Site-level extension whitelist; empty means "no extra restriction"."""
    raw = str(get_setting("upload_allowed_ext", "") or "")
    return {
        "." + item.strip().lower().lstrip(".")
        for item in raw.split(",")
        if item.strip()
    }


def size_limit_mb(filename: str) -> int:
    """Per-type single file limit: videos and images have separate budgets."""
    video = splitext(filename)[-1].lower() in VIDEO_EXTS
    key = "upload_video_max_size" if video else "upload_image_max_size"
    default = 20 if video else 10
    try:
        return int(get_setting(key, default) or default)
    except (TypeError, ValueError):
        return default


def fetch_limit_mb() -> int:
    """Cap for a URL fetch, where the media type is unknown until downloaded."""
    return max(size_limit_mb("probe.mp4"), size_limit_mb("probe.png"))


def check_upload_limits(filename: str, size: int) -> None:
    """Enforce the site settings that apply to every upload."""
    suffix = splitext(filename)[-1].lower()
    allowed = allowed_suffixes()
    if allowed and suffix not in allowed:
        raise ApiError("file type is not allowed", ErrorCode.PARAM_ERROR)
    if suffix in VIDEO_EXTS and not get_setting("allow_video", True):
        raise ApiError("video upload is disabled", ErrorCode.FORBIDDEN, 403)

    limit_mb = size_limit_mb(filename)
    if size > limit_mb * 1024 * 1024:
        raise ApiError("file exceeds %d MB" % limit_mb, ErrorCode.PARAM_ERROR, 413)


def create_image(
    owner,
    filename: str,
    stream: bytes,
    mime: str = "",
    album: Album | None = None,
    title: str = "",
    expire: int = 0,
    upload_path: str | None = None,
) -> Image:
    """Persist an object and its metadata on the primary backend."""
    #: secure_filename 会剥掉中文等非 ASCII 字符（"截图.png" -> "png"），
    #: 主体与后缀分开清洗，避免后缀被一起吞掉导致类型判定失败。
    name, ext = splitext(filename or "")
    stem = secure_filename(name)
    if not stem:
        #: 名字整段被清空时用时间戳+随机串兜底，避免所有中文名都撞成同一个 key。
        stem = "%s%s" % (
            datetime.now().strftime("%Y%m%d%H%M%S"),
            uuid4().hex[:6],
        )
    ext = secure_filename(ext.lstrip(".")).lower()
    filename = f"{stem}.{ext}" if ext else stem
    suffix = f".{ext}" if ext else ""
    if suffix not in IMAGE_EXTS and suffix not in VIDEO_EXTS:
        raise ApiError("unsupported file type", ErrorCode.PARAM_ERROR)
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)

    #: 先剥掉 EXIF/XMP 再处理：落盘的字节里不留拍摄时间、相机与 GPS。
    stream = strip_metadata(stream, suffix)
    stream, filename, mime = process_stream(stream, filename, mime)
    suffix = splitext(filename)[-1].lower()
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)
    #: 尺寸取「实际落盘」的字节：pic2webp 之类的处理器可能换掉格式。
    dimensions = image_size(stream, suffix)

    sha = make_sha(filename)
    #: 同一用户同一天可能上传同名文件，key 里加一段 sha 片段避免互相覆盖。
    object_stem, object_suffix = splitext(filename)
    object_name = "%s-%s%s" % (
        object_stem,
        sha.rsplit(".", 1)[-1][:12],
        object_suffix,
    )
    upload_path = upload_path or upload_path_for(owner)
    backends = list_backends(owner)
    primary = backends[0]

    result = save_object(primary, sha, object_name, stream, upload_path)
    if result.get("code") != 0:
        raise ApiError(
            "storage save failed: %s"
            % (result.get("message") or result.get("msg") or "unknown error"),
            ErrorCode.SERVICE_UNAVAILABLE,
            503,
        )

    #: 权限以相册为维度，任何图片都必须有归属相册。
    album = album if album is not None else resolve_album(owner)

    expire_at = now() + expire if expire and expire > 0 else None
    try:
        with db.atomic():
            image = Image.create(
                sha=sha,
                owner=owner,
                album=album,
                filename=filename,
                title=(title or "")[:255],
                size=len(stream),
                mime=(mime or "")[:64],
                is_video=suffix in VIDEO_EXTS,
                width=dimensions[0] if dimensions else None,
                height=dimensions[1] if dimensions else None,
                status=STATUS_ENABLED,
                visibility=None,
                created_at=now(),
                updated_at=now(),
                expire_at=expire_at,
            )
            ImageBackend.create(
                image=image,
                backend=primary["id"],
                object_key=result.get("path") or "",
                url=result.get("src"),
                size=result.get("size") or len(stream),
                etag=result.get("etag"),
                is_primary=True,
                state=STATE_OK,
                created_at=now(),
            )
    except Exception:
        #: Best-effort compensation to avoid orphaned objects.
        runtime = driver_backend(primary)
        get_hook_manager().call(
            "upimg_delete",
            include=[primary["hook_name"]],
            sha=sha,
            upload_path="",
            filename=filename,
            basedir=(runtime.get("config") or {}).get("root", ""),
            save_result=result,
            backend=runtime,
        )
        raise

    #: 其余启用的后端异步补副本：失败只记录在副本行上，不影响本次上传。
    if len(backends) > 1 and get_setting("storage_replica"):
        queue_replicas(
            current_app._get_current_object(),
            image.id,
            backends[1:],
            sha,
            object_name,
            stream,
            upload_path,
        )
    return image


#: Only absolute http(s) links may be imported as external references.
EXTERNAL_SCHEMES = ("http", "https")


def create_external_image(
    owner,
    url: str,
    filename: str = "",
    title: str = "",
    album: Album | None = None,
) -> Image:
    """Register an external link without downloading the file.

    The bytes stay at the origin: public images link straight to the source and
    private ones are relayed through ``/raw/<sha>``. No replica row is written,
    so deleting the record never touches the source.
    """
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in EXTERNAL_SCHEMES or not parsed.netloc:
        raise ApiError(
            "url must be an absolute http(s) link", ErrorCode.PARAM_ERROR
        )
    if len(url) > 1024:
        raise ApiError("url is too long", ErrorCode.PARAM_ERROR)

    name = secure_filename(filename or posix_basename(parsed.path))
    if not name:
        name = "external"
    mime = guess_type(name)[0] or guess_type(parsed.path)[0] or ""
    suffix = splitext(name)[-1].lower()

    if owner is not None and Image.get_or_none(
        (Image.owner == owner)
        & (Image.source_url == url)
        & (Image.status == STATUS_ENABLED)
        & not_expired()
    ):
        raise ApiError("link already imported", ErrorCode.CONFLICT, 409)

    return Image.create(
        sha=make_sha(name),
        owner=owner,
        album=album if album is not None else resolve_album(owner),
        filename=name[:255],
        title=(title or "")[:255],
        size=0,
        mime=(mime or "")[:64],
        is_video=suffix in VIDEO_EXTS,
        status=STATUS_ENABLED,
        visibility=None,
        source_url=url,
        created_at=now(),
        updated_at=now(),
    )


def effective_visibility(image: Image) -> str:
    """Single-image visibility wins; otherwise the album decides."""
    if image.visibility:
        return image.visibility
    if image.album is not None:
        return image.album.visibility
    return VISIBILITY_PUBLIC


def can_view(user, image: Image) -> bool:
    if user is not None and (user.is_admin or image.owner_id == user.id):
        return True

    visibility = effective_visibility(image)
    if visibility == VISIBILITY_PUBLIC:
        return True
    #: ``shared`` 只来自相册，授权记录按相册发放，单图不会单独共享。
    if visibility == "shared" and image.album is not None:
        return share_for(user, image.album) is not None
    return False


def effective_plaza(image: Image, album: Album | None = None) -> bool:
    """Single-image flag wins; otherwise the album's plaza switch decides."""
    if image.plaza is not None:
        return bool(image.plaza)
    if album is None:
        album = image.album
    return bool(album.plaza) if album is not None else False


def public_condition():
    """Effective visibility is public (image override or album)."""
    return (Image.visibility == VISIBILITY_PUBLIC) | (
        Image.visibility.is_null()
        & ((Image.album.is_null()) | (Album.visibility == VISIBILITY_PUBLIC))
    )


def visible_query(user, all_images: bool = False):
    """Images listed for ``user``: their own plus the albums shared with them.

    Public visibility is deliberately absent: ``GET /api/v2/images`` is the
    personal library, so another user's public album must not leak into it.
    Public exposure is the plaza's job and requires an explicit publish.

    An admin can opt into the whole instance with ``all_images`` (the gallery's
    "show every image" switch), but it is never the default: the moderation view
    must be an explicit click, not what the page opens with. Even there only
    *public* images are listed -- the switch must not turn into a way to browse
    other people's private albums.
    """
    query = (
        Image.select(Image)
        .join(Album, JOIN.LEFT_OUTER, on=(Image.album == Album.id))
        .where(live_condition())
    )

    if user is None:
        #: 接口本身已要求登录，这里只是防御性兜底：匿名没有图库。
        return query.where(False)
    if all_images and user.is_admin:
        #: 全站视图只放大到「公开」这一层，私有/共享相册里的图必须留在库里。
        return query.where(public_condition())
    shared_albums = AlbumShare.select(AlbumShare.album).where(
        (AlbumShare.grantee == user)
        & (AlbumShare.expires_at.is_null() | (AlbumShare.expires_at > now()))
    )
    return query.where(
        (Image.owner == user) | (Image.album.in_(shared_albums))
    )


def plaza_query():
    """Public images the owner published to the plaza.

    Publishing is an exposure switch, not a permission: flagged images keep
    their own visibility, so non-public ones stay out of the listing.
    """
    return (
        Image.select(Image)
        .join(Album, JOIN.LEFT_OUTER, on=(Image.album == Album.id))
        .where(
            live_condition()
            & public_condition()
            & (
                (Image.plaza.is_null(False) & Image.plaza)
                | (Image.plaza.is_null() & Album.plaza)
            )
        )
    )


def album_image_count(album: Album) -> int:
    return (
        Image.select(fn.COUNT(Image.id))
        .where((Image.album == album) & live_condition())
        .scalar()
        or 0
    )


def user_image_counts(user_ids: list[int]) -> dict[int, int]:
    """Live image count per owner, for a batch of user ids in one query.

    Owners without any live image are absent from the mapping, so callers
    should default missing keys to zero.
    """
    ids = [int(uid) for uid in user_ids]
    if not ids:
        return {}
    rows = (
        Image.select(Image.owner.alias("owner_id"), fn.COUNT(Image.id).alias("total"))
        .where(Image.owner.in_(ids) & live_condition())
        .group_by(Image.owner)
    )
    return {row.owner_id: row.total for row in rows}


def delete_image(image: Image) -> None:
    """Soft delete metadata, then remove every replica."""
    image.status = STATUS_DELETED
    image.deleted_at = now()
    image.updated_at = now()
    image.save(only=[Image.status, Image.deleted_at, Image.updated_at])

    for replica in list(image.replicas):
        #: 只有成功的副本才真的有对象要删（storing/failed 的没有落盘）。
        if replica.state == STATE_OK:
            delete_object(image, replica)
        replica.delete_instance()


def expired_query():
    """Enabled images whose ``expire_at`` has been reached."""
    return Image.select(Image).where(
        (Image.status == STATUS_ENABLED)
        & Image.expire_at.is_null(False)
        & (Image.expire_at <= now())
    )


def purge_image(image: Image) -> None:
    """Delete an expired image for good: files first, then the row.

    Expiry means "gone", not "hidden", so the metadata is dropped instead of
    being soft deleted: the sha is never reused, and keeping dead rows only
    makes the sweeper's ``WHERE`` slower.
    """
    delete_image(image)
    image.delete_instance()


def purge_expired(limit: int = SWEEP_BATCH) -> int:
    """Hard delete up to ``limit`` expired images, returning how many went."""
    removed = 0
    for image in list(expired_query().order_by(Image.expire_at).limit(limit)):
        purge_image(image)
        removed += 1
    return removed


def sweep_expired(interval: int = SWEEP_INTERVAL, limit: int = SWEEP_BATCH) -> int:
    """Opportunistic cleanup so expiry works without a cron job.

    Called from a ``before_request`` hook, hence the per-process throttle: at
    most one small batch every ``interval`` seconds. Failures are logged and
    swallowed, a broken storage driver must never break a request.
    """
    global _last_sweep
    moment = monotonic()
    if _last_sweep is not None and moment - _last_sweep < interval:
        return 0
    #: 先记时间戳：清理本身报错也不会让每个请求都重试一次。
    _last_sweep = moment
    try:
        return purge_expired(limit)
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to purge expired images")
        return 0
