# -*- coding: utf-8 -*-
"""Image lifecycle: create, publish, query, delete."""

from __future__ import annotations

import ipaddress
import json
import socket
from contextlib import closing
from datetime import datetime
from hashlib import sha1
from mimetypes import guess_type
from os.path import splitext
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
from ..models.image import STATUS_DELETED, STATUS_ENABLED
from ..models.storage import STATE_OK
from .albums import resolve_album, share_for
from .hook import get_hook_manager
from .storage import (
    delete_object,
    driver_backend,
    list_backends,
    replicas_for,
    save_object,
)

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

    Public payloads link to the highest priority replica that reported a public
    URL, which keeps sapic out of the data path; private images must stay behind
    ``/raw/<sha>`` so the visibility check keeps applying.
    """
    if album is None:
        album = image.album
    visibility = image.visibility or (
        album.visibility if album is not None else VISIBILITY_PUBLIC
    )
    if visibility == VISIBILITY_PUBLIC:
        rows = replicas if replicas is not None else replicas_for(image)
        #: 只看优先级最高的副本，与 /raw/<sha> 的输出顺序保持一致。
        if rows and rows[0].url:
            return rows[0].url
    return public_url(image.sha)


def serialize_image(
    image: Image,
    album: Album | None = None,
    replicas: list[ImageBackend] | None = None,
) -> dict:
    return {
        "sha": image.sha,
        "filename": image.filename,
        "title": image.title,
        "size": image.size,
        "mime": image.mime,
        "is_video": bool(image.is_video),
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
        "src": image_src(image, album, replicas),
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
        return serialize_image(
            image, albums.get(image.album_id), replicas.get(image.id)
        )

    return serialize, prefetch


#: Remote fetches are http(s) only, hop-validated and size/time bounded, so the
#: endpoint cannot be used as a proxy into the intranet.
REMOTE_TIMEOUT = 10
REMOTE_MAX_REDIRECTS = 3
REMOTE_CHUNK_SIZE = 64 * 1024
REMOTE_USER_AGENT = "sapic/url-fetch"

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


def _is_public_host(hostname: str) -> bool:
    """Reject loopback/private/link-local targets before connecting."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False
    return bool(infos)


def open_remote(
    url: str, timeout: int = REMOTE_TIMEOUT, headers: dict | None = None
):
    """Open a validated public http(s) URL for streaming.

    Redirects are validated hop by hop, so the caller must close the returned
    response when done.
    """
    opener = build_opener(_NoRedirect(), ProxyHandler({}))
    target = url
    for _ in range(REMOTE_MAX_REDIRECTS + 1):
        parsed = urlparse(target)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ApiError("only http(s) url is supported", ErrorCode.PARAM_ERROR)
        if not _is_public_host(parsed.hostname):
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
            exc.close()
            if exc.code in (301, 302, 303, 307, 308) and location:
                target = urljoin(target, location)
                continue
            raise ApiError(
                "remote fetch failed: %s" % exc.code, ErrorCode.PARAM_ERROR
            ) from exc
        except (URLError, OSError, ValueError) as exc:
            raise ApiError("remote fetch failed", ErrorCode.PARAM_ERROR) from exc
    raise ApiError("too many redirects", ErrorCode.PARAM_ERROR)


def download_image(
    url: str, max_bytes: int, timeout: int = REMOTE_TIMEOUT
) -> tuple[bytes, str, str]:
    """Fetch a remote payload as ``(stream, filename, mime)``."""
    response = open_remote(url, timeout)
    parsed = urlparse(response.geturl() or url)
    mime = (response.headers.get_content_type() or "").lower()
    if not mime.startswith(("image/", "video/")):
        response.close()
        raise ApiError("remote resource is not an image", ErrorCode.PARAM_ERROR)

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
        except OSError as exc:
            raise ApiError("remote fetch failed", ErrorCode.PARAM_ERROR) from exc

    name = unquote(parsed.path.rsplit("/", 1)[-1]) or "remote"
    suffix = splitext(name)[-1].lower()
    if suffix not in IMAGE_EXTS and suffix not in VIDEO_EXTS:
        name = "%s%s" % (splitext(name)[0] or "remote", MIME_EXTS.get(mime, ""))
    return b"".join(chunks), name, mime


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
    for result in get_hook_manager().call(
        "upimg_stream_processor", stream=processed, suffix=suffix
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

    stream, filename, mime = process_stream(stream, filename, mime)
    suffix = splitext(filename)[-1].lower()
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)

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
            "storage save failed: %s" % (result.get("msg") or "unknown error"),
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
    return image


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


def _public_condition():
    """Effective visibility is public (image override or album)."""
    return (Image.visibility == VISIBILITY_PUBLIC) | (
        Image.visibility.is_null()
        & ((Image.album.is_null()) | (Album.visibility == VISIBILITY_PUBLIC))
    )


def visible_query(user):
    """Images listed for ``user``: their own plus the albums shared with them.

    Public visibility is deliberately absent: ``GET /api/v2/images`` is the
    personal library, so another user's public album must not leak into it.
    Public exposure is the plaza's job and requires an explicit publish.
    """
    query = (
        Image.select(Image)
        .join(Album, JOIN.LEFT_OUTER, on=(Image.album == Album.id))
        .where(Image.status == STATUS_ENABLED)
    )

    if user is None:
        #: 接口本身已要求登录，这里只是防御性兜底：匿名没有图库。
        return query.where(False)
    if user.is_admin:
        return query
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
            (Image.status == STATUS_ENABLED)
            & _public_condition()
            & (
                (Image.plaza.is_null(False) & Image.plaza)
                | (Image.plaza.is_null() & Album.plaza)
            )
        )
    )


def album_image_count(album: Album) -> int:
    return (
        Image.select(fn.COUNT(Image.id))
        .where((Image.album == album) & (Image.status == STATUS_ENABLED))
        .scalar()
        or 0
    )


def delete_image(image: Image) -> None:
    """Soft delete metadata, then remove every replica."""
    image.status = STATUS_DELETED
    image.deleted_at = now()
    image.updated_at = now()
    image.save(only=[Image.status, Image.deleted_at, Image.updated_at])

    for replica in list(image.replicas):
        delete_object(image, replica)
        replica.delete_instance()
