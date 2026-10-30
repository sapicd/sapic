# -*- coding: utf-8 -*-
"""Album model: the permission boundary for images."""

from __future__ import annotations

from peewee import AutoField, CharField, ForeignKeyField, IntegerField, TextField

from .base import BaseModel, now
from .user import User

VISIBILITY_PUBLIC = "public"
VISIBILITY_PRIVATE = "private"
VISIBILITY_SHARED = "shared"
VISIBILITIES = (VISIBILITY_PUBLIC, VISIBILITY_PRIVATE, VISIBILITY_SHARED)


class Album(BaseModel):
    id = AutoField()
    owner = ForeignKeyField(User, backref="albums", column_name="owner_id")
    name = CharField(max_length=100)
    visibility = CharField(max_length=16, default=VISIBILITY_PRIVATE)
    description = TextField(default="")
    #: Cover image is referenced by sha to avoid a circular foreign key.
    cover_sha = CharField(max_length=64, null=True)
    created_at = IntegerField(default=now)
    updated_at = IntegerField(default=now)

    class Meta:
        table_name = "albums"
        indexes = (
            (("owner", "name"), True),
            (("visibility", "created_at"), False),
        )
