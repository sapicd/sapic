# -*- coding: utf-8 -*-
"""Image listing and metadata management."""

from __future__ import annotations

from flask import Blueprint, g, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.albums import can_view_album
from ..libs.auth import current_user, login_required
from ..libs.images import (
    album_serializer,
    can_view,
    delete_image,
    normalize_tags,
    serialize_image,
    tag_condition,
    visible_query,
)
from ..models import Album, Image
from ..models.base import now
from ..models.image import STATUS_ENABLED
from ..utils.web import ok, paginate

bp = Blueprint("images", __name__)


def _get_image(sha: str) -> Image:
    image = Image.get_or_none(
        (Image.sha == sha) & (Image.status == STATUS_ENABLED)
    )
    if image is None:
        raise ApiError("image not found", ErrorCode.NOT_FOUND, 404)
    return image


@bp.get("/images")
@login_required
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

    tag = (request.args.get("tag") or "").strip()
    if tag:
        query = query.where(tag_condition(tag))

    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid limit", ErrorCode.PARAM_ERROR) from exc

    serialize, prefetch = album_serializer()
    return ok(
        paginate(
            query,
            Image,
            serialize,
            limit=limit,
            cursor=request.args.get("cursor"),
            prefetch=prefetch,
        )
    )


@bp.get("/images/<sha>")
def read_image(sha: str):
    image = _get_image(sha)
    user = current_user()
    if not can_view(user, image):
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    data = serialize_image(image, image.album)
    #: 单图被覆盖成 public 时，别把别人私有相册的名字一起带出去。
    if image.album is not None and not can_view_album(user, image.album):
        data["album"] = None
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
    #: 只有作者和管理员能改，前端据此决定是否渲染编辑区。
    data["can_edit"] = user is not None and (
        image.owner_id == user.id or user.is_admin
    )
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
        #: 每张图片必须归属相册：置空会让私有图在 effective_visibility 里跌回
        #: public，等于把图片泄成匿名可读。
        if album_id in (None, "", 0):
            raise ApiError("album_id is required", ErrorCode.PARAM_ERROR)
        album = Album.get_or_none(
            (Album.id == album_id) & (Album.owner == image.owner)
        )
        if album is None:
            raise ApiError("album not found", ErrorCode.NOT_FOUND, 404)
        image.album = album
    if "visibility" in data:
        visibility = data.get("visibility")
        #: ``shared`` 只在相册维度有意义（授权是按相册发放的），单图只能
        #: 覆盖为公开/私有，空值表示跟随相册。
        if visibility not in (None, "public", "private"):
            raise ApiError("invalid visibility", ErrorCode.PARAM_ERROR)
        image.visibility = visibility
    if "tags" in data:
        image.tags = normalize_tags(data.get("tags"))
    if "plaza" in data:
        plaza = data.get("plaza")
        #: 三态：空值跟随相册，布尔值强制发布/排除。
        if plaza is not None and not isinstance(plaza, bool):
            raise ApiError("invalid plaza flag", ErrorCode.PARAM_ERROR)
        image.plaza = plaza

    image.updated_at = now()
    image.save(
        only=[
            Image.title,
            Image.album,
            Image.visibility,
            Image.plaza,
            Image.tags,
            Image.updated_at,
        ]
    )
    return ok({"image": serialize_image(image, image.album)})


@bp.delete("/images/<sha>")
@login_required
def remove_image(sha: str):
    image = _get_image(sha)
    if image.owner_id != g.user.id and not g.user.is_admin:
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)
    delete_image(image)
    return ok({"deleted": True})
