# -*- coding: utf-8 -*-
"""Image metadata.

``sha`` is the public identifier (``/raw/<sha>``) and stays stable across
storage backends, so external links survive backend changes.
"""

from __future__ import annotations

from peewee import (
    AutoField,
    BigIntegerField,
    BooleanField,
    CharField,
    ForeignKeyField,
    IntegerField,
)

from .album import Album
from .base import BaseModel, JSONTextField, now
from .user import User

STATUS_ENABLED = "enabled"
STATUS_DELETED = "deleted"


class Image(BaseModel):
    id = AutoField()
    #: Format: ``sha1.<timestamp>.<sha1(filename)>``, same as v1.
    sha = CharField(max_length=64, unique=True)
    #: NULL for anonymous uploads.
    owner = ForeignKeyField(
        User, backref="images", column_name="owner_id", null=True
    )
    album = ForeignKeyField(
        Album, backref="images", column_name="album_id", null=True
    )
    filename = CharField(max_length=255)
    title = CharField(max_length=255, default="")
    size = BigIntegerField(default=0)
    mime = CharField(max_length=64, default="")
    is_video = BooleanField(default=False)
    #: Intrinsic pixel size; NULL for external links / unparsable payloads.
    width = IntegerField(null=True)
    height = IntegerField(null=True)
    status = CharField(max_length=16, default=STATUS_ENABLED)
    #: NULL means "inherit from album".
    visibility = CharField(max_length=16, null=True)
    #: NULL inherits the album's plaza flag; True/False overrides it.
    plaza = BooleanField(null=True)
    #: Free-form labels, stored as a JSON array; NULL means "no tags".
    tags = JSONTextField(null=True)
    #: External link registered without downloading; NULL for stored objects.
    source_url = CharField(max_length=1024, null=True)
    created_at = IntegerField(default=now)
    updated_at = IntegerField(default=now)
    #: NULL means "never expires"; otherwise the unix ts when the image dies.
    expire_at = IntegerField(null=True)
    deleted_at = IntegerField(null=True)

    class Meta:
        table_name = "images"
        indexes = (
            (("owner", "created_at", "id"), False),
            (("album", "created_at", "id"), False),
            (("status",), False),
            (("expire_at",), False),
        )


def not_expired(reference: int | None = None):
    """``expire_at`` NULL is permanent; otherwise it must still be ahead."""
    pivot = now() if reference is None else reference
    return Image.expire_at.is_null() | (Image.expire_at > pivot)


def live_condition():
    """Rows that exist and have not reached their expiry."""
    return (Image.status == STATUS_ENABLED) & not_expired()


def is_expired(image: Image, reference: int | None = None) -> bool:
    """Whether ``image`` is past its expiry at ``reference`` (default: now)."""
    if image.expire_at is None:
        return False
    return image.expire_at <= (now() if reference is None else reference)
