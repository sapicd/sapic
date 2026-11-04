# -*- coding: utf-8 -*-
"""Native upload endpoint (logged-in or anonymous)."""

from __future__ import annotations

from os.path import splitext

from flask import Blueprint, current_app, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.albums import can_write
from ..libs.auth import SCOPE_UPLOAD, current_user, require_scope
from ..libs.images import (
    VIDEO_EXTS,
    create_image,
    download_image,
    serialize_image,
)
from ..libs.settings import get_setting
from ..models import Album
from ..models.user import STATUS_DISABLED, STATUS_PENDING, STATUS_REJECTED
from ..utils.web import ok

bp = Blueprint("uploads", __name__)

BLOCKED_STATUS = (STATUS_REJECTED, STATUS_PENDING, STATUS_DISABLED)


def anonymous_upload_allowed() -> bool:
    """Anonymous uploads are on when either the deploy flag or the site setting is."""
    if current_app.config.get("ALLOW_ANONYMOUS_UPLOAD", False):
        return True
    return bool(get_setting("allow_anonymous_upload", False))


def _allowed_suffixes() -> set[str]:
    """Site-level extension whitelist; empty means "no extra restriction"."""
    raw = str(get_setting("upload_allowed_ext", "") or "")
    return {
        "." + item.strip().lower().lstrip(".")
        for item in raw.split(",")
        if item.strip()
    }


def _check_upload_limits(filename: str, size: int) -> None:
    """Enforce the site settings that apply to every native upload."""
    suffix = splitext(filename)[-1].lower()
    allowed = _allowed_suffixes()
    if allowed and suffix not in allowed:
        raise ApiError("file type is not allowed", ErrorCode.PARAM_ERROR)
    if suffix in VIDEO_EXTS and not get_setting("allow_video", True):
        raise ApiError("video upload is disabled", ErrorCode.FORBIDDEN, 403)

    limit_mb = int(get_setting("upload_max_size", 20) or 20)
    if size > limit_mb * 1024 * 1024:
        raise ApiError("file exceeds %d MB" % limit_mb, ErrorCode.PARAM_ERROR, 413)


@bp.post("/uploads")
def upload():
    #: 上传接口允许匿名，没有 login_required 兜底，令牌的 scope 在这里单独校验。
    require_scope(SCOPE_UPLOAD)
    user = current_user()
    if user is None:
        if not anonymous_upload_allowed():
            raise ApiError(
                "anonymous upload is disabled", ErrorCode.FORBIDDEN, 403
            )
    elif user.status in BLOCKED_STATUS:
        raise ApiError("account cannot upload", ErrorCode.FORBIDDEN, 403)

    file = request.files.get("file")
    if file is not None and not file.filename:
        file = None
    remote_url = (request.form.get("url") or "").strip()
    if file is None and not remote_url:
        raise ApiError("file or url is required", ErrorCode.PARAM_ERROR)

    if file is not None:
        filename = file.filename
        mime = file.mimetype or ""
        stream = file.stream.read()
    else:
        #: URL 上传由服务端抓取，下载阶段就按大小上限截断，避免把整段内容读进内存。
        limit_mb = int(get_setting("upload_max_size", 20) or 20)
        stream, filename, mime = download_image(remote_url, limit_mb * 1024 * 1024)

    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)
    _check_upload_limits(filename, len(stream))

    album = None
    album_id = request.form.get("album_id")
    if album_id:
        if user is None:
            raise ApiError("album requires login", ErrorCode.FORBIDDEN, 403)
        try:
            album_id = int(album_id)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid album_id", ErrorCode.PARAM_ERROR) from exc
        album = Album.get_or_none(Album.id == album_id)
        #: 相册所有者和被授予 write 的共享成员都可以往里上传。
        if album is None or not can_write(user, album):
            raise ApiError("album not found", ErrorCode.NOT_FOUND, 404)

    expire = 0
    if request.form.get("expire"):
        try:
            expire = int(request.form.get("expire"))
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid expire", ErrorCode.PARAM_ERROR) from exc

    image = create_image(
        owner=user,
        filename=filename,
        stream=stream,
        mime=mime,
        album=album,
        title=request.form.get("title") or "",
        expire=expire,
    )
    return ok({"image": serialize_image(image)}, status=201)
