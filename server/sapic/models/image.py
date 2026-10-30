# -*- coding: utf-8 -*-
"""Image metadata.

``sha`` is the public identifier (``/i/<sha>``) and stays stable across
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
from .base import BaseModel, now
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
    status = CharField(max_length=16, default=STATUS_ENABLED)
    #: NULL means "inherit from album".
    visibility = CharField(max_length=16, null=True)
    created_at = IntegerField(default=now)
    updated_at = IntegerField(default=now)
    expire_at = IntegerField(null=True)
    deleted_at = IntegerField(null=True)

    class Meta:
        table_name = "images"
        indexes = (
            (("owner", "created_at", "id"), False),
            (("album", "created_at", "id"), False),
            (("status",), False),
        )
