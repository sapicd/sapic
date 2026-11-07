# -*- coding: utf-8 -*-
"""Image listing and metadata management."""

from __future__ import annotations

from flask import Blueprint, g, request

from ..basis.db import db
from ..basis.errors import ApiError, ErrorCode
from ..libs.albums import can_view_album, can_write
from ..libs.auth import SCOPE_UPLOAD, current_user, login_required, require_scope
from ..libs.images import (
    album_serializer,
    can_view,
    create_external_image,
    delete_image,
    normalize_tags,
    resolve_expire_at,
    serialize_image,
    tag_condition,
    visible_query,
)
from ..models import Album, Image
from ..models.base import now
from ..models.image import live_condition
from ..utils.web import ok, paginate

bp = Blueprint("images", __name__)

#: Caps for the batch endpoints; a browser grid cannot realistically exceed them.
MAX_BATCH = 100
MAX_IMPORT = 50


def _get_image(sha: str) -> Image:
    #: 过期图片等同于不存在：清理任务还没跑时也不能读、不能改。
    image = Image.get_or_none((Image.sha == sha) & live_condition())
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


def _sha_list(raw) -> list[str]:
    """Deduplicated sha list for the batch endpoints."""
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ApiError("shas must be a non-empty list", ErrorCode.PARAM_ERROR)
    shas: list[str] = []
    for item in raw:
        sha = str(item or "").strip()
        if sha and sha not in shas:
            shas.append(sha)
    if not shas:
        raise ApiError("shas must be a non-empty list", ErrorCode.PARAM_ERROR)
    if len(shas) > MAX_BATCH:
        raise ApiError(
            "at most %d images per request" % MAX_BATCH, ErrorCode.PARAM_ERROR
        )
    return shas


def _owned_image(sha: str) -> Image:
    image = _get_image(sha)
    if image.owner_id != g.user.id and not g.user.is_admin:
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)
    return image


def _target_album(raw) -> Album:
    try:
        album_id = int(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid album_id", ErrorCode.PARAM_ERROR) from exc
    album = Album.get_or_none(Album.id == album_id)
    #: 与上传同口径：所有者或被授予 write 的成员才能往里放图。
    if album is None or not can_write(g.user, album):
        raise ApiError("album not found", ErrorCode.NOT_FOUND, 404)
    return album


@bp.post("/images/import")
@login_required
def import_external():
    """Register external links without downloading them."""
    require_scope(SCOPE_UPLOAD)
    data = request.get_json(silent=True) or {}
    raw = data.get("items")
    if isinstance(raw, str):
        raw = [line for line in raw.splitlines() if line.strip()]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ApiError("items must be a non-empty list", ErrorCode.PARAM_ERROR)
    if len(raw) > MAX_IMPORT:
        raise ApiError(
            "at most %d links per request" % MAX_IMPORT, ErrorCode.PARAM_ERROR
        )

    album = _target_album(data["album_id"]) if data.get("album_id") else None

    imported = []
    failed = []
    for item in raw:
        if isinstance(item, dict):
            url = item.get("url")
            filename = item.get("filename") or ""
            title = item.get("title") or ""
        else:
            url, filename, title = item, "", ""
        try:
            image = create_external_image(g.user, url, filename, title, album)
        except ApiError as exc:
            failed.append({"url": str(url or ""), "message": exc.message})
            continue
        imported.append(serialize_image(image, image.album))
    return ok({"imported": imported, "failed": failed})


@bp.post("/images/batch/delete")
@login_required
def batch_delete():
    data = request.get_json(silent=True) or {}
    images = [_owned_image(sha) for sha in _sha_list(data.get("shas"))]
    for image in images:
        delete_image(image)
    return ok({"deleted": len(images)})


@bp.patch("/images/batch")
@login_required
def batch_update():
    """Move, re-publish or re-tag several images in one request."""
    data = request.get_json(silent=True) or {}
    shas = _sha_list(data.get("shas"))

    fields = []
    album = None
    tags: list[str] = []
    if "album_id" in data:
        album = _target_album(data.get("album_id"))
        fields.append(Image.album)
    if "visibility" in data:
        visibility = data.get("visibility")
        #: 与单图 PATCH 同口径：空值表示跟随相册。
        if visibility not in (None, "public", "private"):
            raise ApiError("invalid visibility", ErrorCode.PARAM_ERROR)
        fields.append(Image.visibility)
    if "plaza" in data:
        plaza = data.get("plaza")
        if plaza is not None and not isinstance(plaza, bool):
            raise ApiError("invalid plaza flag", ErrorCode.PARAM_ERROR)
        fields.append(Image.plaza)
    if "tags" in data:
        tags = normalize_tags(data.get("tags"))
        fields.append(Image.tags)
    if not fields:
        raise ApiError("nothing to update", ErrorCode.PARAM_ERROR)
    fields.append(Image.updated_at)

    images = [_owned_image(sha) for sha in shas]

    with db.atomic():
        for image in images:
            if "album_id" in data:
                image.album = album
            if "visibility" in data:
                image.visibility = data.get("visibility")
            if "plaza" in data:
                image.plaza = data.get("plaza")
            if "tags" in data:
                image.tags = tags
            image.updated_at = now()
            image.save(only=fields)
    return ok({"updated": len(images)})


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
    #: 只有作者和管理员能改，前端据此决定是否渲染编辑区。
    can_edit = user is not None and (
        image.owner_id == user.id or user.is_admin
    )
    data["can_edit"] = can_edit
    replicas = []
    for replica in image.replicas:
        item = {
            "backend": replica.backend.name,
            "state": replica.state,
            "is_primary": replica.is_primary,
            "size": replica.size,
            "etag": replica.etag,
        }
        if can_edit:
            #: 对象路径与失败原因只给作者/管理员：核对「云端到底有没有落盘」
            #: 需要知道 key，而对访客暴露内部路径没有意义。
            item["key"] = replica.object_key
            item["url"] = replica.url
            item["error"] = replica.last_error
        replicas.append(item)
    data["replicas"] = replicas
    return ok({"image": data})


@bp.patch("/images/<sha>")
@login_required
def update_image(sha: str):
    image = _get_image(sha)
    if image.owner_id != g.user.id and not g.user.is_admin:
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    data = request.get_json(silent=True) or request.form.to_dict()

    fields = []
    if "title" in data:
        image.title = (data.get("title") or "")[:255]
        fields.append(Image.title)
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
        fields.append(Image.album)
    if "visibility" in data:
        visibility = data.get("visibility")
        #: ``shared`` 只在相册维度有意义（授权是按相册发放的），单图只能
        #: 覆盖为公开/私有，空值表示跟随相册。
        if visibility not in (None, "public", "private"):
            raise ApiError("invalid visibility", ErrorCode.PARAM_ERROR)
        image.visibility = visibility
        fields.append(Image.visibility)
    if "tags" in data:
        image.tags = normalize_tags(data.get("tags"))
        fields.append(Image.tags)
    if "plaza" in data:
        plaza = data.get("plaza")
        #: 三态：空值跟随相册，布尔值强制发布/排除。
        if plaza is not None and not isinstance(plaza, bool):
            raise ApiError("invalid plaza flag", ErrorCode.PARAM_ERROR)
        image.plaza = plaza
        fields.append(Image.plaza)
    if "expire_at" in data:
        #: 绝对值时间戳，空值表示取消有效期（永久保留）。
        image.expire_at = resolve_expire_at(data.get("expire_at"))
        fields.append(Image.expire_at)
    if not fields:
        raise ApiError("nothing to update", ErrorCode.PARAM_ERROR)

    image.updated_at = now()
    fields.append(Image.updated_at)
    image.save(only=fields)
    return ok({"image": serialize_image(image, image.album)})


@bp.delete("/images/<sha>")
@login_required
def remove_image(sha: str):
    image = _get_image(sha)
    if image.owner_id != g.user.id and not g.user.is_admin:
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)
    delete_image(image)
    return ok({"deleted": True})
