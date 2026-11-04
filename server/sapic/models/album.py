# -*- coding: utf-8 -*-
"""Album model: the permission boundary for images.

Every image belongs to exactly one album, which is what decides who may view
it. Two kinds of album are special:

* the **system album** (``owner`` is NULL) collects anonymous uploads;
* each user's **default album** (``is_default``) is the fallback target for
  uploads that do not name an album, and cannot be deleted.
"""

from __future__ import annotations

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    ForeignKeyField,
    IntegerField,
    TextField,
)

from .base import BaseModel, now
from .user import User

VISIBILITY_PUBLIC = "public"
VISIBILITY_PRIVATE = "private"
VISIBILITY_SHARED = "shared"
VISIBILITIES = (VISIBILITY_PUBLIC, VISIBILITY_PRIVATE, VISIBILITY_SHARED)


class Album(BaseModel):
    id = AutoField()
    #: NULL for the system album that holds anonymous uploads.
    owner = ForeignKeyField(
        User, backref="albums", column_name="owner_id", null=True
    )
    name = CharField(max_length=100)
    visibility = CharField(max_length=16, default=VISIBILITY_PRIVATE)
    description = TextField(default="")
    #: Cover image is referenced by sha to avoid a circular foreign key.
    cover_sha = CharField(max_length=64, null=True)
    #: The per-user fallback album; it may be renamed but never deleted.
    is_default = BooleanField(default=False)
    #: Owner published this album to the public plaza (visibility still applies).
    plaza = BooleanField(default=False)
    created_at = IntegerField(default=now)
    updated_at = IntegerField(default=now)

    class Meta:
        table_name = "albums"
        indexes = (
            (("owner", "name"), True),
            (("visibility", "created_at"), False),
        )

    @property
    def is_system(self) -> bool:
        return self.owner_id is None
