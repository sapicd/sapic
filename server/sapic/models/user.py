# -*- coding: utf-8 -*-
"""User and per-user settings."""

from __future__ import annotations

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    ForeignKeyField,
    IntegerField,
)

from .base import BaseModel, JSONTextField, now

#: v1 status semantics are kept for a smooth migration.
STATUS_REJECTED = -2
STATUS_PENDING = -1
STATUS_DISABLED = 0
STATUS_NORMAL = 1


class User(BaseModel):
    id = AutoField()
    username = CharField(max_length=32, unique=True, index=True)
    email = CharField(max_length=128, null=True, unique=True)
    password_hash = CharField(max_length=255)
    nickname = CharField(max_length=64, default="")
    avatar = CharField(max_length=255, default="")
    is_admin = BooleanField(default=False)
    status = IntegerField(default=STATUS_NORMAL)
    labels = JSONTextField(null=True)
    email_verified = BooleanField(default=False)
    #: Incremented to revoke all existing cookie sessions for this user.
    session_version = IntegerField(default=0)
    #: Reserved for the passportd OIDC integration.
    oidc_issuer = CharField(max_length=255, null=True)
    oidc_subject = CharField(max_length=255, null=True)
    created_at = IntegerField(default=now)
    updated_at = IntegerField(default=now)

    class Meta:
        table_name = "users"
        indexes = ((("oidc_issuer", "oidc_subject"), True),)

    @property
    def label_list(self) -> list[str]:
        return list(self.labels or [])


class UserSetting(BaseModel):
    id = AutoField()
    user = ForeignKeyField(User, backref="settings", column_name="user_id")
    key = CharField(max_length=64)
    value = JSONTextField(null=True)
    updated_at = IntegerField(default=now)

    class Meta:
        table_name = "user_settings"
        indexes = ((("user", "key"), True),)
