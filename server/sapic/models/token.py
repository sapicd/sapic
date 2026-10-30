# -*- coding: utf-8 -*-
"""Upload tickets and personal access tokens.

Both store only a SHA-256 hash of the secret; plaintext is returned once at
creation time and never persisted.
"""

from __future__ import annotations

from peewee import (
    AutoField,
    BigIntegerField,
    CharField,
    ForeignKeyField,
    IntegerField,
)

from .album import Album
from .base import BaseModel, JSONTextField, now
from .storage import StorageBackend
from .user import User


class UploadTicket(BaseModel):
    """Short-lived, capability-limited credential for third-party uploads."""

    id = AutoField()
    token_hash = CharField(max_length=64, unique=True)
    owner = ForeignKeyField(User, backref="upload_tickets", column_name="owner_id")
    album = ForeignKeyField(
        Album, backref="upload_tickets", column_name="album_id", null=True
    )
    backend = ForeignKeyField(
        StorageBackend, backref="upload_tickets", column_name="backend_id", null=True
    )
    #: Optional browser origin allow-list (comma separated).
    origin = CharField(max_length=255, default="")
    allow_ip = CharField(max_length=64, null=True)
    max_size = BigIntegerField(null=True)
    content_types = CharField(max_length=255, default="")
    max_uses = IntegerField(default=1)
    uses = IntegerField(default=0)
    expires_at = IntegerField()
    last_used_at = IntegerField(null=True)
    revoked_at = IntegerField(null=True)
    created_at = IntegerField(default=now)

    class Meta:
        table_name = "upload_tickets"
        indexes = ((("owner", "created_at"), False),)


class ApiToken(BaseModel):
    """Long-lived token for API clients (PicGo, uPic, CLI)."""

    id = AutoField()
    owner = ForeignKeyField(User, backref="api_tokens", column_name="owner_id")
    name = CharField(max_length=64, default="")
    token_hash = CharField(max_length=64, unique=True)
    #: First characters of the token, shown in the UI for identification.
    prefix = CharField(max_length=16, default="")
    scopes = JSONTextField(null=True)
    expires_at = IntegerField(null=True)
    last_used_at = IntegerField(null=True)
    revoked_at = IntegerField(null=True)
    created_at = IntegerField(default=now)

    class Meta:
        table_name = "api_tokens"
        indexes = ((("owner", "created_at"), False),)

    @property
    def scope_list(self) -> list[str]:
        return list(self.scopes or [])
