# -*- coding: utf-8 -*-
"""Native upload endpoint."""

from __future__ import annotations

from flask import Blueprint, g, request

from ..errors import ApiError, ErrorCode
from ..models import Album
from ..models.user import STATUS_DISABLED, STATUS_PENDING, STATUS_REJECTED
from ..responses import ok
from ..security import login_required
from ..services.images import create_image, serialize_image

bp = Blueprint("uploads", __name__)


@bp.post("/uploads")
@login_required
def upload():
    user = g.user
    if user.status in (STATUS_REJECTED, STATUS_PENDING, STATUS_DISABLED):
        raise ApiError("account cannot upload", ErrorCode.FORBIDDEN, 403)

    file = request.files.get("file") or request.files.get("picbed")
    if file is None or not file.filename:
        raise ApiError("file is required", ErrorCode.PARAM_ERROR)
    stream = file.stream.read()
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)

    album = None
    album_id = request.form.get("album_id")
    if album_id:
        try:
            album_id = int(album_id)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid album_id", ErrorCode.PARAM_ERROR) from exc
        album = Album.get_or_none(
            (Album.id == album_id) & (Album.owner == user)
        )
        if album is None:
            raise ApiError("album not found", ErrorCode.NOT_FOUND, 404)

    expire = 0
    if request.form.get("expire"):
        try:
            expire = int(request.form.get("expire"))
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid expire", ErrorCode.PARAM_ERROR) from exc

    image = create_image(
        owner=user,
        filename=file.filename,
        stream=stream,
        mime=file.mimetype or "",
        album=album,
        title=request.form.get("title") or "",
        expire=expire,
    )
    return ok({"image": serialize_image(image)}, status=201)
