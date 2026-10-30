# -*- coding: utf-8 -*-
"""Album CRUD."""

from __future__ import annotations

from flask import Blueprint, g, request

from ..errors import ApiError, ErrorCode
from ..models import Album, AlbumShare, Image
from ..models.base import now
from ..models.image import STATUS_ENABLED
from ..responses import ok
from ..security import login_required
from ..services.images import album_image_count

bp = Blueprint("albums", __name__)

VISIBILITIES = ("public", "private", "shared")


def serialize_album(album: Album, role: str = "owner") -> dict:
    return {
        "id": album.id,
        "name": album.name,
        "description": album.description,
        "visibility": album.visibility,
        "cover_sha": album.cover_sha,
        "image_count": album_image_count(album),
        "role": role,
        "created_at": album.created_at,
        "updated_at": album.updated_at,
    }


def _payload() -> dict:
    return request.get_json(silent=True) or request.form.to_dict()


@bp.get("/albums")
@login_required
def list_albums():
    shared = (
        AlbumShare.select(AlbumShare.album)
        .where(AlbumShare.grantee == g.user)
    )
    albums = list(
        Album.select()
        .where((Album.owner == g.user) | (Album.id.in_(shared)))
        .order_by(Album.created_at.desc())
    )
    shared_ids = {
        row.album_id
        for row in AlbumShare.select().where(AlbumShare.grantee == g.user)
    }
    return ok(
        {
            "items": [
                serialize_album(
                    album, "shared" if album.id in shared_ids else "owner"
                )
                for album in albums
            ]
        }
    )


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

    album.updated_at = now()
    album.save(
        only=[
            Album.name,
            Album.visibility,
            Album.description,
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
