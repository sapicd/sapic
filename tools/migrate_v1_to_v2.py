# -*- coding: utf-8 -*-
"""Migrate sapic v1 (Redis) data into v2 (Peewee: MySQL / PostgreSQL / SQLite).

v1 layout (all keys are prefixed with ``picbed:``)::

    accounts                set    usernames
    account:<name>          hash   password/is_admin/avatar/nickname/ctime/status/
                                   label/email/email_verified/status_reason
    index:global            set    image sha list
    image:<sha>             hash   sha/album/filename/upload_path/user/ctime/
                                   status/src/sender/title/is_video
    TTL of image:<sha>      int    seconds left before v1 expired the object

v2 target: ``users`` / ``albums`` / ``images`` / ``image_backends`` in **MySQL or
PostgreSQL** (SQLite is allowed for a rehearsal only, see ``--allow-sqlite``).

What is migrated:

* accounts -> ``users`` (password hash is reused as-is, so v1 passwords keep
  working; email + verification flag, labels, admin flag and status carry over);
* image album names -> ``albums`` (per owner, plus the system album for
  anonymous uploads);
* images -> ``images`` with the **original sha**, because ``/raw/<sha>`` is the
  link users already published. Bytes are re-uploaded through the primary
  storage backend; images whose v1 file is gone are registered as external
  links pointing at the old ``src`` instead of being dropped.

What is not migrated (by design):

* v1 LinkTokens / link reports — the format is incompatible with v2 PATs, and
  every login token was a bearer for the whole account. Users create PATs in
  ``/settings`` after the upgrade;
* per-user preferences, hotlink rules and visit statistics — v1 kept them in
  ad-hoc Redis keys and v2 has different defaults;
* images already deleted in v1 (``status != enabled``) — they have no file.

The run is idempotent and resumable: users match on ``username``, albums on
``(owner, name)``, images on ``sha``. Re-running after an interruption only adds
what is missing.

Usage::

    # 1) rehearsal: reads Redis, touches no data (schema is still created)
    python tools/migrate_v1_to_v2.py --dry-run \
        --redis-url redis://127.0.0.1:6379/0 \
        --v2-db-url 'postgresql://sapic:pw@127.0.0.1:5432/sapic'

    # 2) real run, MySQL target
    python tools/migrate_v1_to_v2.py \
        --redis-url redis://127.0.0.1:6379/0 \
        --v1-upload-dir /srv/sapic-v1/src/static/upload \
        --v2-db-url 'mysql://sapic:pw@127.0.0.1:3306/sapic?charset=utf8mb4'

    # 3) after the run: compare both sides
    python tools/migrate_v1_to_v2.py --verify --v2-db-url '...'

Re-run the same command if it was interrupted; nothing is duplicated.

:copyright: (c) 2026 by staugur.
:license: BSD 3-Clause, see LICENSE for more details.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from mimetypes import guess_type
from os.path import splitext
from pathlib import Path
from urllib.parse import urlparse

#: ``sapic`` lives in ``server/`` and is a local package: make it importable when
#: the script is started from the repository root.
SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

#: Migration touches data only, never the secret key; keep dev defaults so the
#: app factory does not refuse to boot on an unconfigured shell.
os.environ.setdefault("sapic_env", "dev")

import redis  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402

from sapic import create_app  # noqa: E402
from sapic.basis.db import db  # noqa: E402
from sapic.basis.errors import ApiError  # noqa: E402
from sapic.libs.albums import default_album, system_album  # noqa: E402
from sapic.libs.hook import get_hook_manager  # noqa: E402
from sapic.libs.images import upload_path_for  # noqa: E402
from sapic.libs.media import image_size  # noqa: E402
from sapic.libs.storage import (  # noqa: E402
    driver_backend,
    list_backends,
    save_object,
)
from sapic.libs.users import validate_username  # noqa: E402
from sapic.models import Album, Image, ImageBackend, User  # noqa: E402
from sapic.models.album import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC  # noqa: E402
from sapic.models.base import now  # noqa: E402
from sapic.models.image import STATUS_ENABLED  # noqa: E402
from sapic.models.storage import STATE_OK  # noqa: E402

KEY_PREFIX = "picbed:"

#: v1 stored ``is_admin``/``is_video``/``email_verified`` as "0"/"1" strings.
TRUTHY = ("1", "true", "yes", "on")

#: Entries read from Redis per ``sscan`` round trip.
DEFAULT_BATCH_SIZE = 500


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in TRUTHY


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _labels(raw) -> list[str]:
    """v1 kept the label list as a comma/space separated string."""
    if not raw:
        return []
    text = str(raw).replace(" ", ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def mask_dsn(url: str) -> str:
    """Hide the password of a DSN before printing it."""
    parsed = urlparse(url)
    if parsed.password is None:
        return url
    return url.replace(":%s@" % parsed.password, ":***@")


def dsn_scheme(url: str) -> str:
    return (urlparse(url).scheme or "").lower()


class Migrator:
    """One migration run; every write is guarded by ``dry_run``."""

    def __init__(self, args):
        self.args = args
        self.dry_run = bool(args.dry_run)
        self.visibility = (
            VISIBILITY_PUBLIC
            if args.visibility == "public"
            else VISIBILITY_PRIVATE
        )
        self.stats = Counter()
        self.failures: list[str] = []
        self.primary = None
        #: Real ``User`` rows, used to attach images to their owner.
        self.users: dict[str, User] = {}
        #: Usernames that exist in v2 (or would, in a dry run). A dry run cannot
        #: hold ``User`` objects, yet it must not report every image as orphaned.
        self.known_users: set[str] = set()
        self.albums: dict[tuple[int | None, str], Album] = {}

    # -- helpers -------------------------------------------------------
    def _fail(self, message: str) -> None:
        self.stats["failed"] += 1
        self.failures.append(message)

    def _album(self, owner, name: str) -> Album:
        """Album for the v1 name, created on first use (system album for anon)."""
        key = (getattr(owner, "id", None), name or "")
        if key in self.albums:
            return self.albums[key]

        if owner is None:
            #: v1 album names had no owner, and v2 has a single system album.
            album = system_album()
        elif not name:
            album = default_album(owner)
        else:
            album = Album.get_or_none(
                (Album.owner == owner) & (Album.name == name)
            )
            if album is None:
                album = Album.create(
                    owner=owner,
                    name=name[:100],
                    visibility=self.visibility,
                    #: 与 v2 内置相册的描述保持一致（库里存的是中文文案）。
                    description="从 v1 迁移",
                    created_at=now(),
                    updated_at=now(),
                )
                self.stats["albums_created"] += 1
            else:
                self.stats["albums_existing"] += 1
        self.albums[key] = album
        return album

    # -- users ---------------------------------------------------------
    def migrate_user(self, username: str, account: dict) -> User | None:
        username = (username or "").strip()
        try:
            username = validate_username(username)
        except ApiError as exc:
            #: v1 pinned the same 4-32 char rule at login, so only hand-edited or
            #: very old data lands here; their images go to the system album.
            self.stats["users_invalid"] += 1
            self.failures.append(
                "user %r: %s (images fall back to the system album)"
                % (username, exc.message)
            )
            return None

        existing = User.get_or_none(User.username == username)
        if existing is not None:
            self.stats["users_existing"] += 1
            self.users[username] = existing
            self.known_users.add(username)
            return existing

        if not account:
            #: ``accounts`` holds the name but the hash is gone: nothing to build
            #: a user from, its images fall back to anonymous.
            self.stats["users_incomplete"] += 1
            self.failures.append("user %s: account hash is missing" % username)
            return None

        if self.dry_run:
            self.stats["users_created"] += 1
            self.known_users.add(username)
            return None

        #: v2 requires a unique email while v1 allowed duplicates; keep the user
        #: and drop the address instead of losing the account.
        email = str(account.get("email") or "").strip().lower()[:128] or None
        email_verified = _truthy(account.get("email_verified"))
        if email:
            clash = User.get_or_none(User.email == email)
            if clash is not None:
                self._fail(
                    "user %s: email %s already used by %s, left empty"
                    % (username, email, clash.username)
                )
                email, email_verified = None, False

        password = str(account.get("password") or "").strip()
        if not password:
            #: Third-party-only v1 accounts have no password; store a throwaway
            #: hash so password login stays impossible.
            password = generate_password_hash(os.urandom(24).hex())
        status = _int(account.get("status"), 1)
        reason = str(account.get("status_reason") or "").strip()[:200] or None
        created_at = _int(account.get("ctime"), now())

        try:
            with db.atomic():
                user = User.create(
                    username=username,
                    email=email,
                    password_hash=password,
                    nickname=(account.get("nickname") or username)[:64],
                    avatar=(account.get("avatar") or "")[:255],
                    is_admin=_truthy(account.get("is_admin")),
                    status=status,
                    status_reason=reason if status < 0 else None,
                    labels=_labels(account.get("label")),
                    email_verified=email_verified,
                    created_at=created_at,
                    updated_at=created_at,
                )
                default_album(user)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the run
            self._fail("user %s: %s" % (username, exc))
            return None

        self.users[username] = user
        self.known_users.add(username)
        self.stats["users_created"] += 1
        return user

    # -- images --------------------------------------------------------
    def _object_name(self, filename: str, sha: str) -> tuple[str, str]:
        """v2 object name: ASCII stem, sha fragment to avoid collisions."""
        stem, ext = splitext(filename or "")
        stem = secure_filename(stem) or "image"
        fragment = sha.rsplit(".", 1)[-1][:12]
        return "%s-%s%s" % (stem, fragment, ext.lower()), ext.lower()

    def _source_file(self, meta: dict, filename: str) -> Path:
        """v1 stored the bytes at ``static/<UPLOAD_FOLDER>/<upload_path>/<name>``."""
        upload_path = str(meta.get("upload_path") or "").strip().lstrip("/\\")
        return Path(self.args.v1_upload_dir) / upload_path / filename

    def _discard_object(self, sha: str, save_result: dict) -> None:
        """Best effort: drop the object when the DB row could not be written."""
        if not self.primary:
            return
        try:
            get_hook_manager().call(
                "upimg_delete",
                include=[self.primary["hook_name"]],
                sha=sha,
                upload_path="",
                filename="",
                basedir="",
                save_result=save_result,
                backend=driver_backend(self.primary),
            )
        except Exception:  # noqa: BLE001 - cleanup must never mask the real error
            pass

    def migrate_image(self, sha: str, meta: dict, ttl: int) -> None:
        if not meta:
            self.stats["images_missing_meta"] += 1
            self.failures.append("image %s: hash is missing in Redis" % sha)
            return

        if Image.get_or_none(Image.sha == sha) is not None:
            self.stats["images_existing"] += 1
            return

        status = str(meta.get("status") or STATUS_ENABLED)
        if status != STATUS_ENABLED:
            #: A deleted v1 image has no file left; migrating it only adds a
            #: dead link to the gallery.
            self.stats["images_deleted"] += 1
            return

        owner_name = str(meta.get("user") or "").strip().lower()
        anonymous = owner_name in ("", "anonymous")
        owner = None if anonymous else self.users.get(owner_name)
        if not anonymous and owner_name not in self.known_users:
            #: Owner was deleted in v1 or failed to migrate: keep the image and
            #: park it in the system album instead of dropping it.
            self.stats["images_orphan_owner"] += 1

        filename = str(meta.get("filename") or "").strip() or "%s.png" % sha[-8:]
        source = self._source_file(meta, filename)
        created_at = _int(meta.get("ctime"), now())
        #: v1 TTL is the seconds left; -1/-2 mean "no expiry"/"gone".
        expire_at = now() + ttl if ttl and ttl > 0 else None
        is_video = _truthy(meta.get("is_video"))

        if self.dry_run:
            self.stats["images_created"] += 1
            if not source.is_file():
                self.stats["images_external"] += 1
                if not str(meta.get("src") or "").strip():
                    self._fail(
                        "image %s: file missing and no src to fall back to" % sha
                    )
            return

        stored = None
        if source.is_file():
            stream = source.read_bytes()
            suffix = splitext(filename)[-1].lower()
            object_name, object_ext = self._object_name(filename, sha)
            stored = save_object(
                self.primary, sha, object_name, stream, upload_path_for(owner)
            )
            if stored.get("code") != 0:
                #: The driver failed but v1 has a public address: register an
                #: external link rather than losing the image entirely.
                self.stats["images_storage_failed"] += 1
                self.failures.append(
                    "image %s: storage driver failed (%s)"
                    % (sha, stored.get("msg") or "unknown error")
                )
                stored = None

        if stored is not None:
            size = stored.get("size") or len(stream)
            mime = guess_type(object_name)[0] or ""
            dimensions = image_size(stream, object_ext or suffix)
            source_url = None
            replica_key = stored.get("path") or ""
            replica_url = stored.get("src")
        else:
            #: Bytes are gone from the v1 directory (or the write failed): keep
            #: the row as an external link so ``/raw/<sha>`` keeps resolving.
            size = 0
            mime = ""
            dimensions = None
            source_url = str(meta.get("src") or "").strip() or None
            replica_key = ""
            replica_url = None
            self.stats["images_external"] += 1
            if source_url is None:
                self._fail("image %s: file missing and no src to fall back to" % sha)
                return

        try:
            with db.atomic():
                album = self._album(owner, str(meta.get("album") or "").strip())
                image = Image.create(
                    sha=sha,
                    owner=owner,
                    album=album,
                    filename=filename[:255],
                    title=str(meta.get("title") or "")[:255],
                    size=size,
                    mime=(mime or "")[:64],
                    is_video=is_video,
                    width=dimensions[0] if dimensions else None,
                    height=dimensions[1] if dimensions else None,
                    status=STATUS_ENABLED,
                    #: Every v1 image was a public hotlink, so public is the
                    #: faithful default; ``--visibility private`` tightens it.
                    visibility=self.visibility,
                    source_url=source_url,
                    created_at=created_at,
                    updated_at=created_at,
                    expire_at=expire_at,
                )
                if source_url is None:
                    ImageBackend.create(
                        image=image,
                        backend=self.primary["id"],
                        object_key=replica_key,
                        url=replica_url,
                        size=size,
                        etag=stored.get("etag") if stored else None,
                        is_primary=True,
                        state=STATE_OK,
                        created_at=now(),
                    )
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the run
            self._fail("image %s: %s" % (sha, exc))
            if stored is not None:
                self._discard_object(sha, stored)
            return
        self.stats["images_created"] += 1

    # -- driver --------------------------------------------------------
    def run(self, users, images) -> Counter:
        if not self.args.skip_users:
            only = self.args.only_user
            for username, account in users:
                if only and (username or "").strip().lower() != only.lower():
                    continue
                self.migrate_user(username, account)

        if self.args.skip_images:
            return self.stats

        backends = list_backends(None)
        if not backends:
            raise SystemExit("no enabled storage backend; start sapic once first")
        self.primary = backends[0]
        print(
            "Primary backend: %s (%s)"
            % (self.primary.get("name"), self.primary.get("hook_name"))
        )

        only = self.args.only_user
        for sha, meta, ttl in images:
            if only and str(meta.get("user") or "").lower() != only.lower():
                continue
            self.migrate_image(sha, meta, ttl)
        return self.stats


# -- redis reading -----------------------------------------------------
def open_v1(redis_url: str):
    return redis.Redis.from_url(redis_url, decode_responses=True)


def count_v1(client) -> tuple[int, int]:
    """``(accounts, indexed images)`` without loading the dataset."""
    return (
        _int(client.scard(KEY_PREFIX + "accounts")),
        _int(client.scard(KEY_PREFIX + "index:global")),
    )


def iter_users(client, batch_size: int = DEFAULT_BATCH_SIZE):
    """Yield ``(username, account hash)`` one by one (``sscan``, no OOM)."""
    for name in client.sscan_iter(
        KEY_PREFIX + "accounts", count=batch_size
    ):
        yield name, client.hgetall("%saccount:%s" % (KEY_PREFIX, name))


def iter_images(client, batch_size: int = DEFAULT_BATCH_SIZE, limit: int = 0):
    """Yield ``(sha, meta hash, ttl)``; ``meta`` is empty for stale index rows."""
    seen = 0
    for sha in client.sscan_iter(
        KEY_PREFIX + "index:global", count=batch_size
    ):
        key = "%simage:%s" % (KEY_PREFIX, sha)
        meta = client.hgetall(key)
        yield sha, meta, client.ttl(key)
        if meta:
            seen += 1
            if limit and seen >= limit:
                return


def read_v1(redis_url: str) -> dict:
    """Load the whole dataset (kept for tests/small instances)."""
    client = open_v1(redis_url)
    try:
        return {
            "users": list(iter_users(client)),
            "images": list(iter_images(client)),
        }
    finally:
        client.close()


# -- verification ------------------------------------------------------
def verify(client, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Compare v1's indexed shas with what v2 holds; 1 when something is missing."""
    missing, checked = [], 0
    batch: list[str] = []

    def flush() -> None:
        nonlocal checked, batch
        if not batch:
            return
        found = {
            row.sha
            for row in Image.select(Image.sha).where(Image.sha.in_(batch))
        }
        missing.extend(sha for sha in batch if sha not in found)
        checked += len(batch)
        batch = []

    for sha in client.sscan_iter(
        KEY_PREFIX + "index:global", count=batch_size
    ):
        key = "%simage:%s" % (KEY_PREFIX, sha)
        status = client.hget(key, "status")
        if status is None and not client.exists(key):
            #: Stale index row: the hash is gone, nothing was migrated on purpose.
            continue
        #: Deleted v1 images are skipped on purpose, so they are not "missing".
        if str(status or STATUS_ENABLED) != STATUS_ENABLED:
            continue
        batch.append(sha)
        if len(batch) >= batch_size:
            flush()
    flush()

    total = _int(Image.select().count())
    print("\nVerification")
    print("  v1 live images        %d" % checked)
    print("  v2 images             %d" % total)
    print("  missing in v2         %d" % len(missing))
    for sha in missing[:20]:
        print("    - %s" % sha)
    if len(missing) > 20:
        print("    ... and %d more" % (len(missing) - 20))
    return 1 if missing else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate sapic v1 (Redis) data into v2 "
            "(MySQL / PostgreSQL / SQLite via Peewee)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("sapic_migrate_redis_url", "redis://127.0.0.1:6379/0"),
        help="v1 Redis DSN",
    )
    parser.add_argument(
        "--v1-upload-dir",
        default=str(Path(__file__).resolve().parents[1] / "V1/src/static/upload"),
        help="v1 local upload directory (up2local static folder)",
    )
    parser.add_argument(
        "--v2-db-url",
        default="",
        help=(
            "v2 target DSN, e.g. "
            "mysql://user:pw@127.0.0.1:3306/sapic?charset=utf8mb4 or "
            "postgresql://user:pw@127.0.0.1:5432/sapic"
        ),
    )
    parser.add_argument("--v2-storage-dir", default="", help="override STORAGE_DIR")
    parser.add_argument(
        "--visibility",
        choices=("public", "private"),
        default="public",
        help="visibility for migrated albums/images (v1 had no concept of it)",
    )
    parser.add_argument("--only-user", default="", help="migrate a single username")
    parser.add_argument(
        "--limit", type=int, default=0, help="cap migrated images (0 = all)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Redis SCAN batch size",
    )
    parser.add_argument("--skip-users", action="store_true", help="images only")
    parser.add_argument("--skip-images", action="store_true", help="users only")
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="allow an SQLite target (rehearsal); MySQL/PostgreSQL are the real targets",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="compare v1 and v2 image shas, write nothing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen without writing any data",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    print("Reading v1 data from %s ..." % mask_dsn(args.redis_url))
    try:
        client = open_v1(args.redis_url)
        accounts, indexed = count_v1(client)
    except redis.exceptions.RedisError as exc:
        print("Cannot read v1 data: %s" % exc)
        print("Check --redis-url (the v1 instance must still hold picbed:* keys).")
        return 2
    print("Found %d account(s) and %d indexed image(s)." % (accounts, indexed))

    overrides = {}
    if args.v2_db_url:
        overrides["DATABASE_URL"] = args.v2_db_url
    if args.v2_storage_dir:
        overrides["STORAGE_DIR"] = args.v2_storage_dir

    try:
        app = create_app(overrides or None)
    except Exception as exc:  # noqa: BLE001 - driver/config errors must read well
        print("Cannot open the v2 database: %s" % exc)
        print("Check --v2-db-url and that the account may create tables.")
        return 2

    target = app.config.get("DATABASE_URL") or ""
    scheme = dsn_scheme(target)
    if scheme.startswith("sqlite") and not args.allow_sqlite:
        print("Refusing to migrate into SQLite (%s)." % mask_dsn(target))
        print(
            "Pass --allow-sqlite for a rehearsal, "
            "or point --v2-db-url at MySQL/PostgreSQL."
        )
        return 2
    print("Target: %s (%s)" % (mask_dsn(target), scheme or "unknown"))

    try:
        with app.app_context():
            if args.verify:
                return verify(client, args.batch_size)

            migrator = Migrator(args)
            stats = migrator.run(
                iter_users(client, args.batch_size),
                iter_images(client, args.batch_size, args.limit),
            )
    finally:
        client.close()
        if not db.is_closed():
            db.close()

    if args.dry_run:
        print("\n[dry-run] nothing was written; the summary shows a real run.")
    print("\nMigration summary")
    for key in (
        "users_created",
        "users_existing",
        "users_invalid",
        "users_incomplete",
        "albums_created",
        "albums_existing",
        "images_created",
        "images_existing",
        "images_external",
        "images_storage_failed",
        "images_deleted",
        "images_missing_meta",
        "images_orphan_owner",
        "failed",
    ):
        print("  %-22s %d" % (key, stats.get(key, 0)))

    if migrator.failures:
        print("\nFailures (first 20):")
        for message in migrator.failures[:20]:
            print("  - %s" % message)
        print("\nFix the cause and re-run: existing rows are skipped.")
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
