# -*- coding: utf-8 -*-
"""Minimal versioned migration runner.

``playhouse.migrate`` is used for future ALTERs. DDL is transactional on
PostgreSQL but not on MySQL, so every migration must be idempotent and safe
to re-run after a partial failure.
"""

from __future__ import annotations

from peewee import CharField, IntegerField

from ..extensions import db
from ..models import ALL_MODELS
from ..models.base import BaseModel, now


class SchemaVersion(BaseModel):
    version = IntegerField(primary_key=True)
    name = CharField(max_length=64)
    applied_at = IntegerField(default=now)

    class Meta:
        table_name = "schema_version"


def _v001_initial() -> None:
    db.create_tables(ALL_MODELS, safe=True)


MIGRATIONS = [
    (1, "initial", _v001_initial),
]


def _ensure_connected() -> None:
    if db.is_closed():
        db.connect()


def upgrade(target: int | None = None) -> list[int]:
    """Apply pending migrations, returning the versions applied."""
    _ensure_connected()
    db.create_tables([SchemaVersion], safe=True)
    applied = {row.version for row in SchemaVersion.select()}
    executed = []
    for version, name, func in MIGRATIONS:
        if version in applied:
            continue
        if target is not None and version > target:
            break
        func()
        SchemaVersion.create(version=version, name=name, applied_at=now())
        executed.append(version)
    return executed
