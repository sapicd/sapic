# -*- coding: utf-8 -*-
"""The v1 → v2 migration tool: users, albums, images and idempotency."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from sapic.libs.storage import list_backends
from sapic.models import Album, Image, ImageBackend, User

TOOL = Path(__file__).resolve().parents[2] / "tools" / "migrate_v1_to_v2.py"
SPEC = importlib.util.spec_from_file_location("migrate_v1_to_v2", TOOL)
MIGRATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATE)

SHA = "sha1.1700000001.abc123def456"


def make_args(tmp_path, **kwargs):
    values = {
        "dry_run": False,
        "visibility": "public",
        "v1_upload_dir": str(tmp_path / "v1"),
        "only_user": "",
        "skip_users": False,
        "skip_images": False,
        "limit": 0,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def write_v1_file(tmp_path, upload_path="2024/01/02", name="photo.png"):
    directory = tmp_path / "v1" / upload_path
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(b"fake-image-bytes")
    return target


def payload(image_overrides=None, ttl=0):
    meta = {
        "sha": SHA,
        "user": "alice",
        "album": "旅行",
        "filename": "photo.png",
        "upload_path": "2024/01/02",
        "ctime": "1700000001",
        "status": "enabled",
        "src": "https://old.example.com/static/upload/2024/01/02/photo.png",
        "title": "海边",
        "is_video": "0",
    }
    meta.update(image_overrides or {})
    return {
        "users": {
            "alice": {
                "password": generate_password_hash("secret123"),
                "ctime": "1700000000",
                "status": "1",
                "is_admin": "1",
                "label": "vip,test",
                "nickname": "Alice",
            }
        },
        "images": [(SHA, meta, ttl)],
    }


def run(app, tmp_path, data=None, **kwargs):
    data = data or payload()
    migrator = MIGRATE.Migrator(make_args(tmp_path, **kwargs))
    with app.app_context():
        #: ``run`` 自己取主后端；这里按脚本内部的 (name, hash) 迭代形式喂数据。
        stats = migrator.run(data["users"].items(), data["images"])
        return stats, migrator


def test_migrates_user_album_and_image(app, tmp_path):
    write_v1_file(tmp_path)
    stats, migrator = run(app, tmp_path)

    assert stats["users_created"] == 1
    assert stats["images_created"] == 1
    assert not migrator.failures

    with app.app_context():
        user = User.get(User.username == "alice")
        assert user.is_admin is True
        assert user.labels == ["vip", "test"]
        assert user.nickname == "Alice"

        album = Album.get(Album.name == "旅行")
        assert album.owner_id == user.id
        assert album.visibility == "public"

        image = Image.get(Image.sha == SHA)
        assert image.owner_id == user.id
        assert image.album_id == album.id
        assert image.title == "海边"
        #: v1 的图都是免登录直链，默认保持公开。
        assert image.visibility == "public"
        assert image.source_url is None

        replica = ImageBackend.get(ImageBackend.image == image)
        assert replica.state == "ok"
        assert replica.is_primary is True
        assert replica.object_key.startswith("alice/")

        stored = Path(app.config["STORAGE_DIR"]) / replica.object_key
        assert stored.read_bytes() == b"fake-image-bytes"


def test_rerun_is_idempotent(app, tmp_path):
    write_v1_file(tmp_path)
    run(app, tmp_path)
    stats, _ = run(app, tmp_path)

    assert stats["users_existing"] == 1
    assert stats["images_existing"] == 1
    assert stats["users_created"] == 0
    assert stats["images_created"] == 0
    with app.app_context():
        assert Image.select().count() == 1


def test_missing_file_falls_back_to_external_link(app, tmp_path):
    stats, migrator = run(app, tmp_path)

    assert stats["images_external"] == 1
    assert not migrator.failures
    with app.app_context():
        image = Image.get(Image.sha == SHA)
        assert image.source_url.endswith("/photo.png")
        assert ImageBackend.select().where(ImageBackend.image == image).count() == 0


def test_dry_run_writes_nothing(app, tmp_path):
    write_v1_file(tmp_path)
    stats, _ = run(app, tmp_path, dry_run=True)

    assert stats["users_created"] == 1
    assert stats["images_created"] == 1
    #: dry-run 也要认得出 owner，不能把已知账号的图算成孤儿。
    assert stats["images_orphan_owner"] == 0
    with app.app_context():
        assert User.select().count() == 0
        assert Image.select().count() == 0


def test_deleted_images_are_skipped(app, tmp_path):
    stats, _ = run(app, tmp_path, data=payload({"status": "deleted"}))
    assert stats["images_deleted"] == 1
    with app.app_context():
        assert Image.select().count() == 0


def test_ttl_becomes_expire_at(app, tmp_path):
    write_v1_file(tmp_path)
    run(app, tmp_path, data=payload(ttl=600))

    with app.app_context():
        image = Image.get(Image.sha == SHA)
        assert image.expire_at is not None


def test_primary_backend_is_required(app, tmp_path):
    with app.app_context():
        assert list_backends(None)
