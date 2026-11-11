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
  link users already published. How the bytes are dealt with depends on where
  v1 kept them:

  - local upload directory -> re-uploaded through the primary storage backend;
  - already in the bucket of an enabled cloud backend (``up2upyun`` /
    ``up2qiniu``, i.e. ``src`` starts with its ``domain``) -> the object is
    **adopted in place**: an ``ok`` replica on that very backend records the
    existing key/url and nothing is copied, so deletes still reach the real
    object (``images_adopted``). The backend is picked by domain, not by upload
    priority: a local backend may outrank the cloud one. Use
    ``--v1-src-prefix`` when v1 was served from a different domain, and
    ``--refresh-external`` to repair rows an older run tagged as external links
    -- or attached to the wrong backend;
  - really gone -> registered as an external link pointing at the old ``src``
    (``images_external``) instead of being dropped.

  Either way the size / mime / pixel dimensions come from v1's own records: v1
  stored the ``upimg_save`` response list in ``senders``, which carries the byte
  size (``file-size``, or plain HTTP ``content-length`` depending on the SDK),
  ``width`` / ``height`` and ``content-md5``. Without that the migrated rows
  would show "0 B / 未知类型 / 未知". ``--refresh-external`` re-reads it, so rows
  created by an older run get repaired too.

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
    python tools/migrate_v1_to_v2.py --verify \
        --redis-url redis://127.0.0.1:6379/0 \
        --v2-db-url '...'

Both DSNs have **no defaults**: ``--redis-url`` is required, and ``--v2-db-url``
falls back to the configured ``DATABASE_URL`` only when omitted on purpose.

Requirements (run the script with the sapic virtualenv):

* the app itself — ``pip install -r server/requirements/base.txt`` — provides
  Peewee, ``Flask``/``Werkzeug`` and the database drivers used here, namely
  ``psycopg`` (v3) for PostgreSQL and ``PyMySQL`` for MySQL;
* **redis-py is not an application dependency** (v2 keeps everything in the
  relational database), this tool is the only thing that reads a Redis server
  -- v1's ``picbed:*`` keys. Install it once before migrating::

      pip install redis

Re-run the same command if it was interrupted; nothing is duplicated.

:copyright: (c) 2026 by staugur.
:license: BSD 3-Clause, see LICENSE for more details.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from importlib.util import find_spec
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

try:  # noqa: SIM105 - a CLI tool must explain the missing extra, not traceback
    import redis  # noqa: E402
except ImportError:  # pragma: no cover - reported by ``main``
    redis = None  # type: ignore[assignment]

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
    LOCAL_DRIVER,
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

#: The tool has no requirement file of its own; it runs on the app virtualenv.
REQUIREMENTS_HINT = (
    "Install the app requirements into this interpreter: "
    "pip install -r server/requirements/base.txt"
)

#: redis-py is not shipped by the app any more: only this migration needs it.
REDIS_HINT = "redis-py is only needed to read v1 data: pip install redis"


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


def missing_driver(url: str) -> str | None:
    """DB-API module the DSN needs, when this interpreter cannot import it.

    Both drivers ship with the app (``server/requirements/base.txt``): PostgreSQL
    through ``psycopg`` v3 (Peewee is pinned to it in ``basis/db.py``), MySQL
    through ``PyMySQL``.
    """
    scheme = dsn_scheme(url)
    if scheme in ("postgres", "postgresql", "pgsql"):
        module = "psycopg"
    elif scheme.startswith("mysql"):
        module = "pymysql"
    else:
        return None
    return None if find_spec(module) is not None else module


def src_object_key(src: str, domain: str) -> str | None:
    """Bucket key of ``src`` when the object is served straight from ``domain``.

    v1 did not have to keep bytes locally: with ``up2upyun`` / ``up2qiniu`` the
    file already sits in the bucket. Re-registering that object as a replica
    beats downloading and re-uploading it -- and beats demoting the image to an
    external link, which would tag it as "外链" and keep the old host alive.
    """
    prefix = str(domain or "").strip().rstrip("/")
    text = str(src or "").strip()
    if not prefix or not text:
        return None

    #: 域名可能写成 ``cdn.example.com``、``//cdn.example.com`` 或带协议；
    #: 只比较 host，所以 http/https、大小写在 v1 与 v2 之间不同也能对上。
    base = urlparse(prefix if "//" in prefix else "//" + prefix)
    parsed = urlparse(text if "//" in text else "//" + text)
    if not base.netloc or parsed.netloc.lower() != base.netloc.lower():
        return None
    path = parsed.path
    if base.path and path.startswith(base.path + "/"):
        path = path[len(base.path) :]
    key = path.strip("/")
    return "/" + key if key else None


def adopt_targets(backends: list[dict], override: str = "") -> list[tuple[dict, str]]:
    """``(backend, public prefix)`` pairs whose bucket may already hold v1 objects.

    Adoption has to record the replica on the backend that really owns the
    object. Attributing it to ``backends[0]`` breaks as soon as a local backend
    outranks the cloud one: the key of a v1 Upyun object would be attached to
    ``up2local``, whose ``upimg_delete`` looks for a file that was never written
    there, so deleting the image silently leaves the bucket object behind.
    """
    def domain_of(backend: dict) -> str:
        config = driver_backend(backend).get("config") or {}
        return str(config.get("domain") or "").strip().rstrip("/")

    targets: list[tuple[dict, str]] = []
    for backend in backends:
        #: ``up2local`` stores on this machine; v1 bytes found there are
        #: re-uploaded through the primary backend instead of being adopted.
        if backend.get("hook_name") == LOCAL_DRIVER:
            continue
        domain = domain_of(backend)
        if domain:
            targets.append((backend, domain))

    override = str(override or "").strip().rstrip("/")
    if override and override not in {prefix for _, prefix in targets} and targets:
        #: v1 may have been served from a retired CDN while the bytes still sit
        #: in the bucket of the current cloud backend.
        targets.append((targets[0][0], override))
    if targets:
        return targets

    #: Only a cloud backend can own a bucket object. Falling back to whatever
    #: backend sorts first would attach the key to ``up2local`` whenever the
    #: cloud backend is disabled, missing or lacks a domain -- deletes then look
    #: in the local storage directory and silently leave the object in the
    #: bucket. Keep ``override`` for that case: the caller reports it as a
    #: configuration problem instead of writing a wrong replica.
    if not backends:
        return []
    primary = backends[0]
    if primary.get("hook_name") == LOCAL_DRIVER:
        return []
    domain = domain_of(primary)
    return [(primary, domain or override)] if (domain or override) else []


def sender_meta(meta: dict) -> dict:
    """First successful ``upimg_save`` response v1 stored in ``image:<sha>``.

    v1 kept the whole result list in the ``senders`` hash field. Those responses
    carry the object's size and pixel dimensions, so for cloud-backed images this
    is the only place the numbers survive -- the v2 row can be filled from it
    without downloading the object. Keys are normalized to lowercase/kebab-case
    because drivers and SDK versions disagree (``File-Size`` vs ``content-length``
    vs ``file_size``).
    """
    raw = meta.get("senders")
    if not raw:
        return {}
    try:
        results = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if isinstance(results, dict):
        results = [results]
    if not isinstance(results, list):
        return {}
    for result in results:
        if isinstance(result, dict) and result.get("code") == 0:
            return {
                str(key).strip().lower().replace("_", "-"): value
                for key, value in result.items()
            }
    return {}


def sender_int(result: dict, *keys) -> int | None:
    """First positive integer among ``keys`` (v1 stored them as strings)."""
    for key in keys:
        try:
            number = int(str(result.get(key)).strip())
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def sender_size(result: dict) -> int | None:
    """Object size in bytes: upyun's ``file-size`` or the raw ``content-length``."""
    return sender_int(result, "file-size", "content-length", "size")


def sender_dims(result: dict) -> tuple[int, int] | None:
    width = sender_int(result, "width")
    height = sender_int(result, "height")
    return (width, height) if width and height else None


def sender_etag(result: dict) -> str | None:
    value = result.get("content-md5") or result.get("etag")
    text = str(value or "").strip()
    return text[:64] if text else None


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
        #: ``(backend, prefix)`` pairs an object may be adopted from; the backend
        #: is the one that owns the bucket, not necessarily the upload primary.
        self.adopt_targets: list[tuple[dict, str]] = []
        #: Prefixes only, kept for the "Not adopted" report.
        self.adopt_prefixes: list[str] = []
        #: Examples of rows ``--refresh-external`` could not match.
        self.unmatched: list[str] = []
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

    def _reuse_object(self, src: str) -> tuple[dict, str, str] | None:
        """``(backend, bucket key, public url)`` when v1's object is in a bucket.

        The backend is the one whose public domain serves ``src`` -- it owns the
        object and its driver must be the one asked to delete it later.
        """
        if not src or not self.adopt_targets:
            return None
        for backend, prefix in self.adopt_targets:
            key = src_object_key(src, prefix)
            if not key:
                continue
            config = driver_backend(backend).get("config") or {}
            domain = str(config.get("domain") or "").strip().rstrip("/")
            #: 直链按该后端的域名重建，旧 CDN 域名退役后也不会坏。
            return backend, key, domain + key if domain else src
        return None

    def _adopt_existing(self, image: Image, meta: dict) -> None:
        """Repair a row an earlier run left behind.

        ``--refresh-external`` does two things: it adopts the bucket object of an
        old external link, and it backfills the size/mime/dimensions v1 recorded
        in ``senders`` (earlier runs could not see them, hence "0 B / 未知").
        """
        result = sender_meta(meta)
        size = sender_size(result)
        dims = sender_dims(result)
        mime = guess_type(str(image.filename or ""))[0] or ""

        updates: dict = {}
        if size and image.size != size:
            updates["size"] = size
        if mime and image.mime != mime:
            updates["mime"] = mime[:64]
        if dims and (image.width is None or image.height is None):
            updates["width"], updates["height"] = dims

        source = str(meta.get("src") or image.source_url or "")
        adopted = self._reuse_object(source) if source else None
        #: ``(replica id, target backend id, url)`` for a replica attached to the
        #: wrong backend by an older run.
        repair = None
        if adopted is None:
            if image.source_url:
                self.stats["images_refresh_skipped"] += 1
                if len(self.unmatched) < 5:
                    self.unmatched.append("%s: %s" % (image.sha, source))
        else:
            backend, key, url = adopted
            if ImageBackend.get_or_none(
                (ImageBackend.image == image)
                & (ImageBackend.backend == backend["id"])
            ) is not None:
                #: 副本已在正确的后端上（早年跑过一次采纳），只补元数据即可。
                adopted = None
            else:
                stray = ImageBackend.get_or_none(
                    (ImageBackend.image == image) & (ImageBackend.object_key == key)
                )
                if stray is not None:
                    #: 早期版本把云上对象挂在了上传主后端（如 up2local）上，删除
                    #: 时那个驱动去本地找文件，bucket 里的对象就一直留着。
                    repair = (stray.id, backend["id"], url)
                elif not image.source_url:
                    #: 本地重传过的图既没有 source_url、也没有错挂副本，不要凭空
                    #: 补一条可能指向已被删对象的副本。
                    adopted = None
                else:
                    updates["source_url"] = None

        if not updates and adopted is None and repair is None:
            return
        if self.dry_run:
            if adopted is not None or repair is not None:
                self.stats["images_adopted"] += 1
            return

        try:
            with db.atomic():
                if repair is not None:
                    replica_id, backend_id, url = repair
                    ImageBackend.update(backend=backend_id, url=url).where(
                        ImageBackend.id == replica_id
                    ).execute()
                    self.stats["images_adopted"] += 1
                elif adopted is not None:
                    target, key, url = adopted
                    ImageBackend.create(
                        image=image,
                        backend=target["id"],
                        object_key=key,
                        url=url,
                        size=updates.get("size", image.size or 0),
                        etag=sender_etag(result),
                        is_primary=target["id"] == self.primary["id"],
                        state=STATE_OK,
                        created_at=now(),
                    )
                    self.stats["images_adopted"] += 1
                if updates:
                    Image.update(**updates).where(Image.id == image.id).execute()
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the run
            self._fail("image %s: %s" % (image.sha, exc))

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

        existing = Image.get_or_none(Image.sha == sha)
        if existing is not None:
            self.stats["images_existing"] += 1
            #: 之前跑过一遍、被记成外链的行，可以在 bucket 认领回来后修好。
            if getattr(self.args, "refresh_external", False):
                self._adopt_existing(existing, meta)
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
        src = str(meta.get("src") or "").strip()
        created_at = _int(meta.get("ctime"), now())
        #: v1 TTL is the seconds left; -1/-2 mean "no expiry"/"gone".
        expire_at = now() + ttl if ttl and ttl > 0 else None
        is_video = _truthy(meta.get("is_video"))

        if self.dry_run:
            self.stats["images_created"] += 1
            if not source.is_file():
                if self._reuse_object(src):
                    self.stats["images_adopted"] += 1
                else:
                    self.stats["images_external"] += 1
                    if not src:
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

        adopted = None
        if stored is None:
            adopted = self._reuse_object(src)

        #: Size/mime/dimensions v1 recorded when it saved to the cloud.
        result = sender_meta(meta)
        mime = guess_type(filename)[0] or ""
        etag = None
        #: Backend that owns the replica; the upload primary unless the object is
        #: adopted from another backend's bucket.
        replica_backend = None

        if stored is not None:
            size = stored.get("size") or len(stream)
            mime = guess_type(object_name)[0] or ""
            dimensions = image_size(stream, object_ext or suffix)
            etag = stored.get("etag")
            source_url = None
            replica_backend = self.primary
            replica_key = stored.get("path") or ""
            replica_url = stored.get("src")
        elif adopted is not None:
            #: v1 的字节还在某个 bucket 里（又拍云/七牛）：登记成副本即可，
            #: 不下载、不重传，删除时也会走该后端的驱动真正删掉对象。
            replica_backend, replica_key, replica_url = adopted
            size = sender_size(result) or 0
            dimensions = sender_dims(result)
            etag = sender_etag(result)
            source_url = None
            self.stats["images_adopted"] += 1
        else:
            #: Bytes are gone from the v1 directory (or the write failed): keep
            #: the row as an external link so ``/raw/<sha>`` keeps resolving.
            #: v1 still recorded size/dimensions in ``senders`` -- use them.
            size = sender_size(result) or 0
            dimensions = sender_dims(result)
            source_url = src or None
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
                    backend = replica_backend or self.primary
                    ImageBackend.create(
                        image=image,
                        backend=backend["id"],
                        object_key=replica_key,
                        url=replica_url,
                        size=size,
                        etag=etag,
                        is_primary=backend["id"] == self.primary["id"],
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
        override = str(getattr(self.args, "v1_src_prefix", "") or "").strip()
        self.adopt_targets = adopt_targets(backends, override)
        self.adopt_prefixes = [prefix for _, prefix in self.adopt_targets]
        print(
            "Adopting objects already in the bucket from: %s"
            % (", ".join(self.adopt_prefixes) or "n/a")
        )
        for backend, _ in self.adopt_targets:
            print(
                "  -> %s (%s)" % (backend.get("name"), backend.get("hook_name"))
            )
        if not self.adopt_targets:
            print(
                "  warning: no cloud backend is available to adopt from. Check "
                "that the cloud hook is enabled, its backend row is enabled and "
                "its public domain is filled. Objects stay external links."
            )
            if override:
                print(
                    "  warning: --v1-src-prefix %s was ignored because no cloud "
                    "backend can own those objects." % override
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
    )
    #: No defaults for the DSNs on purpose: a silent localhost fallback writes
    #: data into the wrong database, so the operator must spell both out.
    parser.add_argument(
        "--redis-url",
        required=True,
        help=(
            "v1 Redis DSN, e.g. redis://127.0.0.1:6379/0 (required; needs "
            "redis-py, which the app itself does not depend on)"
        ),
    )
    parser.add_argument(
        "--v1-upload-dir",
        default=None,
        help=(
            "v1 local upload directory (up2local static folder), e.g. "
            "/srv/sapic-v1/src/static/upload; required unless --skip-images "
            "is given"
        ),
    )
    parser.add_argument(
        "--v2-db-url",
        default=None,
        help=(
            "v2 target DSN (required unless the configured DATABASE_URL is "
            "the intended target). PostgreSQL is driven by psycopg v3: "
            "postgresql://user:pw@127.0.0.1:5432/sapic; MySQL is driven by "
            "PyMySQL: mysql://user:pw@127.0.0.1:3306/sapic?charset=utf8mb4"
        ),
    )
    parser.add_argument(
        "--v1-src-prefix",
        default="",
        help=(
            "public prefix v1 served images from, when it differs from every "
            "backend's domain (e.g. https://old-cdn.example.com); matching "
            "objects are adopted in place instead of re-uploaded"
        ),
    )
    parser.add_argument(
        "--refresh-external",
        action="store_true",
        help=(
            "repair rows migrated before: external links whose object is "
            "already in the primary backend's bucket become ok replicas"
        ),
    )
    parser.add_argument(
        "--v2-storage-dir",
        default=None,
        help="override STORAGE_DIR",
    )
    parser.add_argument(
        "--visibility",
        choices=("public", "private"),
        default="public",
        help=(
            "visibility for migrated albums/images, default: public "
            "(v1 had no concept of it)"
        ),
    )
    parser.add_argument("--only-user", default="", help="migrate a single username")
    parser.add_argument(
        "--limit", type=int, default=0, help="cap migrated images, default: 0 (all)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Redis SCAN batch size, default: %d" % DEFAULT_BATCH_SIZE,
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

    if not args.skip_images and not args.v1_upload_dir:
        print("Missing --v1-upload-dir: point it at your v1 deployment's upload folder")
        print("(the up2local static directory, e.g. /srv/sapic-v1/src/static/upload).")
        print("Pass --skip-images if only users and albums are needed.")
        return 2

    if redis is None:
        print("Cannot read v1 data: redis-py is not installed.")
        print(REDIS_HINT)
        return 2

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
        module = missing_driver(args.v2_db_url)
        if module:
            print(
                "Cannot reach %s: the %s driver is not installed."
                % (dsn_scheme(args.v2_db_url), module)
            )
            print(REQUIREMENTS_HINT)
            return 2
        overrides["DATABASE_URL"] = args.v2_db_url
    if args.v2_storage_dir:
        overrides["STORAGE_DIR"] = args.v2_storage_dir

    try:
        app = create_app(overrides or None)
    except Exception as exc:  # noqa: BLE001 - driver/config errors must read well
        print("Cannot open the v2 database: %s" % exc)
        print("Check --v2-db-url and that the account may create tables.")
        print(REQUIREMENTS_HINT)
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
        "images_adopted",
        "images_external",
        "images_refresh_skipped",
        "images_storage_failed",
        "images_deleted",
        "images_missing_meta",
        "images_orphan_owner",
        "failed",
    ):
        print("  %-22s %d" % (key, stats.get(key, 0)))

    if migrator.unmatched:
        print("\nNot adopted (src is outside %s):" % (migrator.adopt_prefixes or "n/a"))
        for message in migrator.unmatched:
            print("  - %s" % message)

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
