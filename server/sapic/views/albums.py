# -*- coding: utf-8 -*-
"""Album CRUD."""

from __future__ import annotations

from flask import Blueprint, g, request

from ..basis.common import as_bool
from ..basis.errors import ApiError, ErrorCode
from ..libs.auth import login_required
from ..libs.images import album_image_count
from ..libs.users import normalize_username
from ..models import Album, AlbumShare, Image, User
from ..models.base import now
from ..models.image import STATUS_ENABLED
from ..models.share import PERMISSION_READ, PERMISSION_WRITE
from ..models.user import STATUS_NORMAL
from ..utils.web import ok

bp = Blueprint("albums", __name__)

VISIBILITIES = ("public", "private", "shared")
PERMISSIONS = (PERMISSION_READ, PERMISSION_WRITE)


def serialize_album(
    album: Album, role: str = "owner", permission: str | None = None
) -> dict:
    return {
        "id": album.id,
        "name": album.name,
        "description": album.description,
        "visibility": album.visibility,
        "plaza": bool(album.plaza),
        "cover_sha": album.cover_sha,
        "image_count": album_image_count(album),
        "role": role,
        #: 共享相册给出成员的权限（read/write），所有者没有这条记录，故为 None。
        "permission": permission,
        "is_default": bool(album.is_default),
        "is_system": album.owner_id is None,
        "created_at": album.created_at,
        "updated_at": album.updated_at,
    }


def serialize_share(share: AlbumShare) -> dict:
    return {
        "user_id": share.grantee.id,
        "username": share.grantee.username,
        "nickname": share.grantee.nickname,
        "permission": share.permission,
        "expires_at": share.expires_at,
        "created_at": share.created_at,
    }


def _payload() -> dict:
    return request.get_json(silent=True) or request.form.to_dict()


def _share_expiry(data: dict) -> int | None:
    """``expires_in`` seconds until the grant ends; empty means permanent."""
    raw = data.get("expires_in")
    if raw in (None, ""):
        return None
    try:
        seconds = int(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid expires_in", ErrorCode.PARAM_ERROR) from exc
    if seconds <= 0:
        raise ApiError("invalid expires_in", ErrorCode.PARAM_ERROR)
    return now() + seconds


def _owned_album(album_id: int) -> Album:
    """Only the owner manages members; guests get a plain 404."""
    album = Album.get_or_none(
        (Album.id == album_id) & (Album.owner == g.user)
    )
    if album is None:
        raise ApiError("album not found", ErrorCode.NOT_FOUND, 404)
    return album


@bp.get("/albums")
@login_required
def list_albums():
    #: 过期的授权等同于不存在，列表与鉴权保持同一口径。
    live = AlbumShare.select().where(
        (AlbumShare.grantee == g.user)
        & (AlbumShare.expires_at.is_null() | (AlbumShare.expires_at > now()))
    )
    shared = [row.album_id for row in live]
    albums = list(
        Album.select()
        .where((Album.owner == g.user) | (Album.id.in_(shared)))
        .order_by(Album.created_at.desc())
    )
    grants = {row.album_id: row.permission for row in live}
    items = [
        serialize_album(
            album,
            "shared" if album.id in grants else "owner",
            grants.get(album.id),
        )
        for album in albums
    ]
    if g.user.is_admin:
        #: 系统相册收纳匿名上传，管理员要能拿它筛选图片。
        system = Album.get_or_none(Album.owner.is_null())
        if system is not None:
            items.append(serialize_album(system, "system"))
    return ok({"items": items})


@bp.post("/albums")
@login_required
def create_album():
    data = _payload()
    name = (data.get("name") or "").strip()
    if not name or len(name) > 100:
        raise ApiError("invalid album name", ErrorCode.PARAM_ERROR)
    visibility = data.get("visibility") or "private"
    if visibility not in VISIBILITIES:
        raise ApiError("invalid visibility", ErrorCode.PARAM_ERROR)
    if Album.get_or_none((Album.owner == g.user) & (Album.name == name)):
        raise ApiError("album already exists", ErrorCode.CONFLICT, 409)

    album = Album.create(
        owner=g.user,
        name=name,
        visibility=visibility,
        plaza=as_bool(data.get("plaza")),
        description=(data.get("description") or "")[:1000],
        created_at=now(),
        updated_at=now(),
    )
    return ok({"album": serialize_album(album)}, status=201)


@bp.patch("/albums/<int:album_id>")
@login_required
def update_album(album_id: int):
    album = Album.get_or_none(
        (Album.id == album_id) & (Album.owner == g.user)
    )
    if album is None:
        raise ApiError("album not found", ErrorCode.NOT_FOUND, 404)

    data = _payload()
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > 100:
            raise ApiError("invalid album name", ErrorCode.PARAM_ERROR)
        exists = Album.get_or_none(
            (Album.owner == g.user) & (Album.name == name) & (Album.id != album.id)
        )
        if exists:
            raise ApiError("album already exists", ErrorCode.CONFLICT, 409)
        album.name = name
    if "visibility" in data:
        if data.get("visibility") not in VISIBILITIES:
            raise ApiError("invalid visibility", ErrorCode.PARAM_ERROR)
        album.visibility = data["visibility"]
    if "description" in data:
        album.description = (data.get("description") or "")[:1000]
    if "plaza" in data:
        album.plaza = as_bool(data.get("plaza"))

    album.updated_at = now()
    album.save(
        only=[
            Album.name,
            Album.visibility,
            Album.description,
            Album.plaza,
            Album.updated_at,
        ]
    )
    return ok({"album": serialize_album(album)})


@bp.delete("/albums/<int:album_id>")
@login_required
def delete_album(album_id: int):
    album = Album.get_or_none(
        (Album.id == album_id) & (Album.owner == g.user)
    )
    if album is None:
        raise ApiError("album not found", ErrorCode.NOT_FOUND, 404)
    if album.is_default:
        #: 每个账号必须有兜底相册，权限模型才能成立。
        raise ApiError(
            "default album cannot be deleted", ErrorCode.CONFLICT, 409
        )
    count = (
        Image.select()
        .where((Image.album == album) & (Image.status == STATUS_ENABLED))
        .count()
    )
    if count:
        raise ApiError(
            "album is not empty, move or delete its images first",
            ErrorCode.CONFLICT,
            409,
        )
    AlbumShare.delete().where(AlbumShare.album == album).execute()
    album.delete_instance()
    return ok({"deleted": True})


@bp.get("/albums/<int:album_id>/shares")
@login_required
def list_shares(album_id: int):
    album = _owned_album(album_id)
    shares = (
        AlbumShare.select(AlbumShare, User)
        .join(User, on=(AlbumShare.grantee == User.id))
        .where(AlbumShare.album == album)
        .order_by(AlbumShare.created_at.desc())
    )
    return ok({"items": [serialize_share(share) for share in shares]})


@bp.post("/albums/<int:album_id>/shares")
@login_required
def create_share(album_id: int):
    """Grant one station member access to an album, by username."""
    album = _owned_album(album_id)
    data = _payload()

    username = normalize_username(data.get("username") or "")
    if not username:
        raise ApiError("username is required", ErrorCode.PARAM_ERROR)
    permission = data.get("permission") or PERMISSION_READ
    if permission not in PERMISSIONS:
        raise ApiError("invalid permission", ErrorCode.PARAM_ERROR)

    grantee = User.get_or_none(User.username == username)
    #: 不存在与未激活共用一条消息，别让人拿这个接口探测账号状态。
    if grantee is None or grantee.status != STATUS_NORMAL:
        raise ApiError("share target not found", ErrorCode.NOT_FOUND, 404)
    if grantee.id == g.user.id:
        raise ApiError("cannot share with yourself", ErrorCode.PARAM_ERROR)

    expires_at = _share_expiry(data)
    share = AlbumShare.get_or_none(
        (AlbumShare.album == album) & (AlbumShare.grantee == grantee)
    )
    created = share is None
    if created:
        share = AlbumShare.create(
            album=album,
            grantee=grantee,
            permission=permission,
            expires_at=expires_at,
            created_at=now(),
        )
    else:
        share.permission = permission
        share.expires_at = expires_at
        share.save(only=[AlbumShare.permission, AlbumShare.expires_at])

    #: Granting access to a private album turns it into a shared one, so the
    #: visibility label matches what actually happens to the album.
    if album.visibility == "private":
        album.visibility = "shared"
        album.updated_at = now()
        album.save(only=[Album.visibility, Album.updated_at])

    return ok(
        {"share": serialize_share(share), "album": serialize_album(album)},
        status=201 if created else 200,
    )


@bp.patch("/albums/<int:album_id>/shares/<int:user_id>")
@login_required
def update_share(album_id: int, user_id: int):
    """Change the permission or the expiry of an existing member."""
    album = _owned_album(album_id)
    data = _payload()
    permission = data.get("permission")
    if permission is not None and permission not in PERMISSIONS:
        raise ApiError("invalid permission", ErrorCode.PARAM_ERROR)
    if permission is None and "expires_in" not in data:
        raise ApiError("nothing to update", ErrorCode.PARAM_ERROR)

    share = AlbumShare.get_or_none(
        (AlbumShare.album == album) & (AlbumShare.grantee == user_id)
    )
    if share is None:
        raise ApiError("share not found", ErrorCode.NOT_FOUND, 404)

    fields = []
    if permission is not None:
        share.permission = permission
        fields.append(AlbumShare.permission)
    if "expires_in" in data:
        share.expires_at = _share_expiry(data)
        fields.append(AlbumShare.expires_at)
    share.save(only=fields)
    return ok({"share": serialize_share(share)})


@bp.delete("/albums/<int:album_id>/shares/<int:user_id>")
@login_required
def delete_share(album_id: int, user_id: int):
    album = _owned_album(album_id)
    deleted = (
        AlbumShare.delete()
        .where((AlbumShare.album == album) & (AlbumShare.grantee == user_id))
        .execute()
    )
    if not deleted:
        raise ApiError("share not found", ErrorCode.NOT_FOUND, 404)
    return ok({"deleted": True})
