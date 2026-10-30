# -*- coding: utf-8 -*-
"""Image listing and metadata management."""

from __future__ import annotations

from flask import Blueprint, g, request

from ..errors import ApiError, ErrorCode
from ..models import Album, Image
from ..models.base import now
from ..models.image import STATUS_ENABLED
from ..responses import ok, paginate
from ..security import current_user, login_required
from ..services.images import (
    can_view,
    delete_image,
    serialize_image,
    visible_query,
)

bp = Blueprint("images", __name__)


def _get_image(sha: str) -> Image:
    image = Image.get_or_none(
        (Image.sha == sha) & (Image.status == STATUS_ENABLED)
    )
    if image is None:
        raise ApiError("image not found", ErrorCode.NOT_FOUND, 404)
    return image


@bp.get("/images")
def list_images():
    query = visible_query(current_user())

    album_id = request.args.get("album_id")
    if album_id:
        try:
            query = query.where(Image.album == int(album_id))
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid album_id", ErrorCode.PARAM_ERROR) from exc

    keyword = (request.args.get("keyword") or "").strip()
    if keyword:
        query = query.where(
            (Image.filename.contains(keyword)) | (Image.title.contains(keyword))
        )

    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid limit", ErrorCode.PARAM_ERROR) from exc

    return ok(
        paginate(
            query,
            Image,
            serialize_image,
            limit=limit,
            cursor=request.args.get("cursor"),
        )
    )


@bp.get("/images/<sha>")
def read_image(sha: str):
    image = _get_image(sha)
    user = current_user()
    if not can_view(user, image):
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    data = serialize_image(image)
    data["replicas"] = [
        {
            "backend": replica.backend.name,
            "state": replica.state,
            "is_primary": replica.is_primary,
            "size": replica.size,
            "etag": replica.etag,
        }
        for replica in image.replicas
    ]
    return ok({"image": data})


@bp.patch("/images/<sha>")
@login_required
def update_image(sha: str):
    image = _get_image(sha)
    if image.owner_id != g.user.id and not g.user.is_admin:
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    data = request.get_json(silent=True) or request.form.to_dict()

    if "title" in data:
        image.title = (data.get("title") or "")[:255]
    if "album_id" in data:
        album_id = data.get("album_id")
        if album_id in (None, "", 0):
            image.album = None
        else:
            album = Album.get_or_none(
                (Album.id == album_id) & (Album.owner == image.owner)
            )
            if album is None:
                raise ApiError("album not found", ErrorCode.NOT_FOUND, 404)
            image.album = album
    if "visibility" in data:
        visibility = data.get("visibility")
        if visibility not in (None, "public", "private", "shared"):
            raise ApiError("invalid visibility", ErrorCode.PARAM_ERROR)
        image.visibility = visibility

    image.updated_at = now()
    image.save(
        only=[Image.title, Image.album, Image.visibility, Image.updated_at]
    )
    return ok({"image": serialize_image(image)})


@bp.delete("/images/<sha>")
@login_required
def remove_image(sha: str):
    image = _get_image(sha)
    if image.owner_id != g.user.id and not g.user.is_admin:
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)
    delete_image(image)
    return ok({"deleted": True})
