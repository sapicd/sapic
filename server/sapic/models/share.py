# -*- coding: utf-8 -*-
"""Album sharing grants (station members)."""

from __future__ import annotations

from peewee import AutoField, CharField, ForeignKeyField, IntegerField

from .album import Album
from .base import BaseModel, now
from .user import User

PERMISSION_READ = "read"
PERMISSION_WRITE = "write"


class AlbumShare(BaseModel):
    id = AutoField()
    album = ForeignKeyField(Album, backref="shares", column_name="album_id")
    grantee = ForeignKeyField(User, backref="shared_albums", column_name="user_id")
    permission = CharField(max_length=16, default=PERMISSION_READ)
    expires_at = IntegerField(null=True)
    created_at = IntegerField(default=now)

    class Meta:
        table_name = "album_shares"
        indexes = ((("album", "grantee"), True),)
