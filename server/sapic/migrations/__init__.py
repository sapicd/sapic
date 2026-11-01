# -*- coding: utf-8 -*-
"""Minimal versioned migration runner.

``playhouse.migrate`` is used for future ALTERs. DDL is transactional on
PostgreSQL but not on MySQL, so every migration must be idempotent and safe
to re-run after a partial failure.

Migrations are applied automatically when the application boots (see
:func:`auto_upgrade`); ``flask sa upgrade`` stays available for operators.
"""

from __future__ import annotations

import logging
from time import sleep

from peewee import (
    BooleanField,
    CharField,
    IntegrityError,
    IntegerField,
    OperationalError,
)
from playhouse.migrate import SchemaMigrator, migrate

from ..basis.db import db
from ..models import ALL_MODELS, Album, Image, User
from ..models.base import BaseModel, now

#: Substrings identifying transient lock errors raised by concurrent workers.
_LOCK_ERRORS = ("locked", "busy", "deadlock")

logger = logging.getLogger(__name__)


class SchemaVersion(BaseModel):
    version = IntegerField(primary_key=True)
    name = CharField(max_length=64)
    applied_at = IntegerField(default=now)

    class Meta:
        table_name = "schema_version"


def _v001_initial() -> None:
    db.create_tables(ALL_MODELS, safe=True)


#: Pinned snapshots: migrations must not follow later constant changes.
_DEFAULT_ALBUM_NAME = "默认相册"
_SYSTEM_ALBUM_NAME = "公共相册"
_ALBUM_VISIBILITY = "public"


def _v002_album_ownership() -> None:
    """Make every image belong to an album.

    ``albums.owner_id`` becomes nullable so the system album can collect
    anonymous uploads, ``is_default`` marks each user's fallback album, and
    images created before the rule are moved into the matching album.
    """
    columns = {column.name: column for column in db.get_columns("albums")}
    operations = []
    migrator = SchemaMigrator.from_database(db)
    owner_column = columns.get("owner_id")
    if owner_column is not None and not owner_column.null:
        operations.append(migrator.drop_not_null("albums", "owner_id"))
    if "is_default" not in columns:
        operations.append(
            migrator.add_column(
                "albums", "is_default", BooleanField(default=False)
            )
        )
    if operations:
        migrate(*operations)

    for user in User.select():
        album = Album.get_or_none((Album.owner == user) & Album.is_default)
        if album is None:
            album = Album.get_or_none(
                (Album.owner == user) & (Album.name == _DEFAULT_ALBUM_NAME)
            )
        if album is None:
            album = Album.create(
                owner=user,
                name=_DEFAULT_ALBUM_NAME,
                visibility=_ALBUM_VISIBILITY,
                description="未指定相册时上传到这里",
                is_default=True,
                created_at=now(),
                updated_at=now(),
            )
        elif not album.is_default:
            album.is_default = True
            album.save(only=[Album.is_default])
        Image.update(album=album).where(
            Image.album.is_null() & (Image.owner == user)
        ).execute()

    orphans = Image.select().where(
        Image.album.is_null() & Image.owner.is_null()
    )
    if orphans.exists():
        system = Album.get_or_none(Album.owner.is_null())
        if system is None:
            system = Album.create(
                owner=None,
                name=_SYSTEM_ALBUM_NAME,
                visibility=_ALBUM_VISIBILITY,
                description="匿名上传的公共相册",
                created_at=now(),
                updated_at=now(),
            )
        Image.update(album=system).where(
            Image.album.is_null() & Image.owner.is_null()
        ).execute()


MIGRATIONS = [
    (1, "initial", _v001_initial),
    (2, "album_ownership", _v002_album_ownership),
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
        try:
            SchemaVersion.create(version=version, name=name, applied_at=now())
        except IntegrityError:
            #: Another worker recorded the same version first; nothing to do.
            continue
        executed.append(version)
    return executed


def _is_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(key in message for key in _LOCK_ERRORS)


def auto_upgrade(retries: int = 5, delay: float = 0.5) -> list[int]:
    """Bring the schema up to date at startup, tolerating concurrent boots.

    Several workers (gunicorn) may migrate at the same time, so transient lock
    errors are retried; migrations are idempotent, which makes this safe.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            applied = upgrade()
        except OperationalError as exc:
            if attempt >= retries or not _is_lock_error(exc):
                raise
            logger.warning(
                "database is busy, retrying migration (%d/%d)", attempt, retries
            )
            sleep(delay)
            continue
        break
    if applied:
        logger.info("applied migrations: %s", ", ".join(map(str, applied)))
    return applied


__all__ = ["MIGRATIONS", "SchemaVersion", "auto_upgrade", "upgrade"]
