# -*- coding: utf-8 -*-
"""Album resolution: the system album and each user's default album.

Permissions are album-scoped, so every upload has to land in an album. Callers
that do not name one fall back to :func:`resolve_album`, which keeps anonymous
uploads in the system album and logged-in uploads in the owner's default album.
"""

from __future__ import annotations

from ..models import Album
from ..models.album import VISIBILITY_PUBLIC
from ..models.base import now
from .settings import get_setting

DEFAULT_ALBUM_NAME = "默认相册"
SYSTEM_ALBUM_NAME = "公共相册"


def system_album() -> Album:
    """The album holding anonymous uploads, created on first use."""
    album = Album.get_or_none(
        (Album.owner.is_null()) & (Album.name == SYSTEM_ALBUM_NAME)
    )
    if album is not None:
        return album
    return Album.create(
        owner=None,
        name=SYSTEM_ALBUM_NAME,
        visibility=VISIBILITY_PUBLIC,
        description="匿名上传的公共相册",
        created_at=now(),
        updated_at=now(),
    )


def default_album(user) -> Album:
    """Return the user's fallback album, creating it when missing."""
    album = Album.get_or_none((Album.owner == user) & Album.is_default)
    if album is None:
        #: Albums created before ``is_default`` existed are recognised by name.
        album = Album.get_or_none(
            (Album.owner == user) & (Album.name == DEFAULT_ALBUM_NAME)
        )
        if album is not None and not album.is_default:
            album.is_default = True
            album.save(only=[Album.is_default])
    if album is not None:
        return album

    visibility = get_setting("default_album_visibility", VISIBILITY_PUBLIC)
    return Album.create(
        owner=user,
        name=DEFAULT_ALBUM_NAME,
        visibility=visibility,
        description="未指定相册时上传到这里",
        is_default=True,
        created_at=now(),
        updated_at=now(),
    )


def resolve_album(owner) -> Album:
    """The album an upload without an explicit target belongs to."""
    return system_album() if owner is None else default_album(owner)
