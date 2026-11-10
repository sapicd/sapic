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

#: 系统级后端：管理员维护，可授权给用户使用（站点默认存储）。
SCOPE_SYSTEM = "system"
#: 用户自定义后端：归属 ``owner``，只有本人可用（预留能力，需站点开关放开）。
SCOPE_USER = "user"
#: 兼容早期数据：v2 早期把系统级写作 ``global``，迁移里已归一为 ``system``。
SCOPE_GLOBAL = "global"
#: 视为「系统后端」的 scope 取值（读路径同时接受旧值，部署期间不会读丢）。
SYSTEM_SCOPES = (SCOPE_SYSTEM, SCOPE_GLOBAL)

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
    scope = CharField(max_length=16, default=SCOPE_SYSTEM)
    owner = ForeignKeyField(
        User, backref="storage_backends", column_name="owner_id", null=True
    )
    #: ``public``: the driver's URL is world-readable (bucket ACL + CDN), so public
    #: images link straight to it. ``private``: the bucket rejects anonymous reads,
    #: every access goes through ``/raw/<sha>`` and the driver hands out a
    #: temporary read address (``upimg_url``) for the relay.
    visibility = CharField(max_length=16, default=VISIBILITY_PUBLIC)
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
