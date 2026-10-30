# -*- coding: utf-8 -*-
"""Storage backends and per-image replicas.

A *driver* is a hook module (``up2local``, ``up2s3`` ...). A *backend* is a
configured instance of a driver, so one driver can serve many buckets or
directories.
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

from .base import BaseModel, JSONTextField, now
from .image import Image
from .user import User

SCOPE_GLOBAL = "global"
SCOPE_USER = "user"

VISIBILITY_PUBLIC = "public"
VISIBILITY_PRIVATE = "private"

STATE_STORING = "storing"
STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_DELETING = "deleting"


class StorageBackend(BaseModel):
    id = AutoField()
    name = CharField(max_length=64, unique=True)
    #: Hook module name providing ``upimg_save`` / ``upimg_delete``.
    hook_name = CharField(max_length=64)
    #: Driver specific options; secret values are encrypted before storage.
    config = JSONTextField(null=True)
    scope = CharField(max_length=16, default=SCOPE_GLOBAL)
    owner = ForeignKeyField(
        User, backref="storage_backends", column_name="owner_id", null=True
    )
    visibility = CharField(max_length=16, default=VISIBILITY_PRIVATE)
    #: Lower value means higher read/write priority.
    priority = IntegerField(default=100)
    enabled = BooleanField(default=True)
    created_at = IntegerField(default=now)
    updated_at = IntegerField(default=now)

    class Meta:
        table_name = "storage_backends"
        indexes = ((("scope", "priority"), False),)


class UserBackend(BaseModel):
    """Which global backends a user may use, and their personal ordering."""

    id = AutoField()
    user = ForeignKeyField(User, backref="user_backends", column_name="user_id")
    backend = ForeignKeyField(
        StorageBackend, backref="user_grants", column_name="backend_id"
    )
    priority = IntegerField(default=100)
    enabled = BooleanField(default=True)
    created_at = IntegerField(default=now)

    class Meta:
        table_name = "user_backends"
        indexes = ((("user", "backend"), True),)


class ImageBackend(BaseModel):
    """One replica of an image on a storage backend."""

    id = AutoField()
    image = ForeignKeyField(
        Image, backref="replicas", column_name="image_id"
    )
    backend = ForeignKeyField(
        StorageBackend, backref="replicas", column_name="backend_id"
    )
    object_key = CharField(max_length=512, default="")
    #: Original URL returned by the driver, used by redirect mode only.
    url = CharField(max_length=1024, null=True)
    size = BigIntegerField(default=0)
    etag = CharField(max_length=64, null=True)
    is_primary = BooleanField(default=False)
    state = CharField(max_length=16, default=STATE_STORING)
    last_error = CharField(max_length=255, null=True)
    checked_at = IntegerField(null=True)
    created_at = IntegerField(default=now)

    class Meta:
        table_name = "image_backends"
        indexes = (
            (("image", "backend"), True),
            (("backend", "state"), False),
        )
