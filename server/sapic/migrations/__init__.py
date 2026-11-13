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
from ..models import ALL_MODELS, Album, Image, StorageBackend, User
from ..models.base import BaseModel, JSONTextField, now
from ..models.storage import SCOPE_SYSTEM, VISIBILITY_PUBLIC

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


def _v003_image_tags() -> None:
    """Add the free-form ``images.tags`` column (JSON array in TEXT)."""
    columns = {column.name for column in db.get_columns("images")}
    if "tags" in columns:
        return
    migrate(
        SchemaMigrator.from_database(db).add_column(
            "images", "tags", JSONTextField(null=True)
        )
    )


def _v004_image_visibility_without_shared() -> None:
    """Drop the meaningless ``shared`` value from single-image overrides.

    Sharing is granted per album (``album_shares``), so an image-level
    ``shared`` either equals ``public`` or collapses to "follow the album".
    Such rows fall back to the album visibility (``NULL``).
    """
    Image.update(visibility=None, updated_at=now()).where(
        Image.visibility == "shared"
    ).execute()


def _v005_plaza() -> None:
    """Add the plaza publishing flags.

    ``albums.plaza`` is the album-level switch, ``images.plaza`` the per-image
    override (``NULL`` follows the album). Publishing never widens the
    visibility rules, it only decides what the public plaza lists.
    """
    migrator = SchemaMigrator.from_database(db)
    album_columns = {column.name for column in db.get_columns("albums")}
    image_columns = {column.name for column in db.get_columns("images")}
    operations = []
    if "plaza" not in album_columns:
        operations.append(
            migrator.add_column("albums", "plaza", BooleanField(default=False))
        )
    if "plaza" not in image_columns:
        operations.append(
            migrator.add_column("images", "plaza", BooleanField(null=True))
        )
    if operations:
        migrate(*operations)


def _v006_image_source_url() -> None:
    """Add ``images.source_url`` for external links that are not downloaded.

    Imported links keep their bytes at the origin: the row only records the
    URL, and ``/raw/<sha>`` redirects (public) or relays (private) to it.
    """
    columns = {column.name for column in db.get_columns("images")}
    if "source_url" in columns:
        return
    migrate(
        SchemaMigrator.from_database(db).add_column(
            "images", "source_url", CharField(max_length=1024, null=True)
        )
    )


def _v007_storage_scope_system() -> None:
    """Rename the system backend scope from ``global`` to ``system``.

    ``scope`` is where "system default" and "user defined" part ways: system
    rows are the admin maintained defaults (optionally granted to users), user
    rows belong to their owner. The rename is data only and idempotent.
    """
    StorageBackend.update(scope=SCOPE_SYSTEM).where(
        StorageBackend.scope == "global"
    ).execute()


def _index_columns(index) -> tuple:
    """Index columns across Peewee versions (``IndexMetadata`` or a tuple)."""
    columns = getattr(index, "columns", None)
    if columns is None and isinstance(index, (tuple, list)):
        columns = index[1]
    return tuple(columns or ())


def _v008_image_expire_at() -> None:
    """Make the expiry sweep cheap: index ``images.expire_at``.

    Old databases may predate the column entirely (it only existed in the
    model), so the column is added first and both steps stay idempotent.
    Fresh databases already get the index from ``Meta.indexes``; the check is
    by column (not name) because the auto-generated names differ between
    ``create_tables`` and the migrator.
    """
    migrator = SchemaMigrator.from_database(db)
    columns = {column.name for column in db.get_columns("images")}
    if "expire_at" not in columns:
        migrate(migrator.add_column("images", "expire_at", IntegerField(null=True)))
    indexed = {_index_columns(index) for index in db.get_indexes("images")}
    if ("expire_at",) not in indexed:
        migrate(migrator.add_index("images", ("expire_at",), False))


def _v009_image_dimensions() -> None:
    """Record the intrinsic pixel size measured at upload time."""
    columns = {column.name for column in db.get_columns("images")}
    migrator = SchemaMigrator.from_database(db)
    operations = []
    for name in ("width", "height"):
        if name not in columns:
            operations.append(
                migrator.add_column("images", name, IntegerField(null=True))
            )
    if operations:
        migrate(*operations)


def _v010_user_status_reason() -> None:
    """Keep the rejection reason so the applicant can be told why.

    v1 stored it in the account hash; v2 needs a column before the review mail
    can quote it.
    """
    columns = {column.name for column in db.get_columns("users")}
    if "status_reason" in columns:
        return
    migrator = SchemaMigrator.from_database(db)
    migrate(migrator.add_column("users", "status_reason", CharField(null=True)))


def _v011_storage_visibility() -> None:
    """Make ``storage_backends.visibility`` meaningful.

    The column existed since v001 but nothing read it, so every row still holds
    the old default (``private``). Rows become ``public`` to keep the behaviour
    deployments already have — public images link straight to the driver URL —
    and new rows default to ``public`` as well. ``private`` is now an explicit
    per-backend choice.
    """
    columns = {column.name for column in db.get_columns("storage_backends")}
    if "visibility" not in columns:
        migrate(
            SchemaMigrator.from_database(db).add_column(
                "storage_backends",
                "visibility",
                CharField(max_length=16, default=VISIBILITY_PUBLIC),
            )
        )
    StorageBackend.update(visibility=VISIBILITY_PUBLIC).execute()


def _v012_api_token_album() -> None:
    """Let a PAT remember the album its uploads should land in.

    The column stays nullable: tokens issued before this feature (and tokens
    without a preference) keep using the owner's default album.
    """
    columns = {column.name for column in db.get_columns("api_tokens")}
    if "album_id" in columns:
        return
    migrate(
        SchemaMigrator.from_database(db).add_column(
            "api_tokens", "album_id", IntegerField(null=True)
        )
    )


MIGRATIONS = [
    (1, "initial", _v001_initial),
    (2, "album_ownership", _v002_album_ownership),
    (3, "image_tags", _v003_image_tags),
    (4, "image_visibility", _v004_image_visibility_without_shared),
    (5, "plaza", _v005_plaza),
    (6, "image_source_url", _v006_image_source_url),
    (7, "storage_scope_system", _v007_storage_scope_system),
    (8, "image_expire_at", _v008_image_expire_at),
    (9, "image_dimensions", _v009_image_dimensions),
    (10, "user_status_reason", _v010_user_status_reason),
    (11, "storage_visibility", _v011_storage_visibility),
    (12, "api_token_album", _v012_api_token_album),
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
