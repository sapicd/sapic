# -*- coding: utf-8 -*-
"""Image lifecycle: create, publish, query, delete."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha1
from mimetypes import guess_type
from os.path import splitext
from uuid import uuid4

from flask import current_app, url_for
from peewee import JOIN, SQL, fn
from werkzeug.utils import secure_filename

from ..basis.db import db
from ..basis.errors import ApiError, ErrorCode
from ..models import Album, AlbumShare, Image, ImageBackend
from ..models.album import VISIBILITY_PUBLIC
from ..models.base import now
from ..models.image import STATUS_DELETED, STATUS_ENABLED
from ..models.storage import STATE_OK
from .albums import resolve_album
from .hook import get_hook_manager
from .storage import (
    delete_object,
    driver_backend,
    list_backends,
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


def serialize_image(image: Image, album: Album | None = None) -> dict:
    return {
        "sha": image.sha,
        "filename": image.filename,
        "title": image.title,
        "size": image.size,
        "mime": image.mime,
        "is_video": bool(image.is_video),
        "visibility": image.visibility,
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
        "src": public_url(image.sha),
    }


def album_serializer():
    """Serializer that annotates each image with its album.

    Album names are resolved lazily and cached per call, so a page costs at most
    one extra query per distinct album (usually one).
    """
    cache: dict[int, Album | None] = {}

    def serialize(image: Image) -> dict:
        if image.album_id and image.album_id not in cache:
            cache[image.album_id] = Album.get_or_none(Album.id == image.album_id)
        return serialize_image(image, cache.get(image.album_id))

    return serialize


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
    filename = secure_filename(filename or "") or "image"
    suffix = splitext(filename)[-1].lower()
    if suffix not in IMAGE_EXTS and suffix not in VIDEO_EXTS:
        raise ApiError("unsupported file type", ErrorCode.PARAM_ERROR)
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)

    stream, filename, mime = process_stream(stream, filename, mime)
    suffix = splitext(filename)[-1].lower()
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)

    sha = make_sha(filename)
    upload_path = upload_path or upload_path_for(owner)
    backends = list_backends(owner)
    primary = backends[0]

    result = save_object(primary, sha, filename, stream, upload_path)
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
    if visibility == "shared" and image.album is not None and user is not None:
        return (
            AlbumShare.get_or_none(
                (AlbumShare.album == image.album)
                & (AlbumShare.grantee == user)
            )
            is not None
        )
    return False


def visible_query(user):
    """Images visible to ``user`` (owners, public, shared albums)."""
    query = (
        Image.select(Image)
        .join(Album, JOIN.LEFT_OUTER, on=(Image.album == Album.id))
        .where(Image.status == STATUS_ENABLED)
    )

    public_condition = (Image.visibility == VISIBILITY_PUBLIC) | (
        Image.visibility.is_null()
        & ((Image.album.is_null()) | (Album.visibility == VISIBILITY_PUBLIC))
    )

    if user is None:
        return query.where(public_condition)
    if user.is_admin:
        return query
    shared_albums = AlbumShare.select(AlbumShare.album).where(
        AlbumShare.grantee == user
    )
    return query.where(
        (Image.owner == user)
        | public_condition
        | (Image.album.in_(shared_albums))
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
