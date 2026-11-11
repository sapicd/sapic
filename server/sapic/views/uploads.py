# -*- coding: utf-8 -*-
"""Native upload endpoint (logged-in or anonymous)."""

from __future__ import annotations

from flask import Blueprint, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.albums import can_write
from ..libs.auth import SCOPE_UPLOAD, current_user, require_scope
from ..libs.images import (
    anonymous_upload_allowed,
    check_upload_limits,
    create_image,
    download_image,
    fetch_limit_mb,
    resolve_expire_seconds,
    serialize_image,
)
from ..models import Album
from ..models.user import STATUS_DISABLED, STATUS_PENDING, STATUS_REJECTED
from ..utils.web import ok

bp = Blueprint("uploads", __name__)

BLOCKED_STATUS = (STATUS_REJECTED, STATUS_PENDING, STATUS_DISABLED)


@bp.post("/upload")
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
        #: URL 上传由服务端抓取：下载前还不知道类型，先按两类里较大的上限截断，
        #: 拿到真实文件名后再走 check_upload_limits 按类型判定。
        stream, filename, mime = download_image(
            remote_url, fetch_limit_mb() * 1024 * 1024
        )

    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)
    check_upload_limits(filename, len(stream))

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

    #: ``expire`` 是秒数（与 v1 一致），空值按站点默认有效期，0 表示永久。
    expire = resolve_expire_seconds(request.form.get("expire"))

    image = create_image(
        owner=user,
        filename=filename,
        stream=stream,
        mime=mime,
        album=album,
        title=request.form.get("title") or "",
        expire=expire,
    )
    #: 未指定 album_id 时 create_image 会兜底到默认/系统相册，这里补上同一份
    #: 相册对象，上传响应才和详情/列表接口的 ``album`` 字段保持一致。
    return ok(
        {"image": serialize_image(image, album if album is not None else image.album)},
        status=201,
    )
