# -*- coding: utf-8 -*-
"""The v1 → v2 migration tool: users, albums, images and idempotency."""

import importlib.util
import json
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
        "v1_src_prefix": "",
        "refresh_external": False,
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


def test_src_object_key_only_matches_the_backend_domain():
    cdn = "https://cdn.example.com"
    assert MIGRATE.src_object_key(
        "https://cdn.example.com/sapic/2024/01/02/a.png", cdn
    ) == "/sapic/2024/01/02/a.png"
    #: 别的域名、空域名都不是「同一个 bucket」。
    assert MIGRATE.src_object_key("https://other.example.com/a.png", cdn) is None
    assert MIGRATE.src_object_key("https://cdn.example.com/a.png", "") is None
    #: CDN 加的参数不能混进对象路径。
    assert MIGRATE.src_object_key(
        "https://cdn.example.com/a.png?v=1", cdn
    ) == "/a.png"
    #: 协议不同不算换了存储：v1 是 http、现在配了 https 也要认。
    assert MIGRATE.src_object_key(
        "http://cdn.example.com/a.png", cdn
    ) == "/a.png"
    #: 域名没写协议头也要能对上（后台里填 cdn.example.com 很常见）。
    assert MIGRATE.src_object_key(
        "https://cdn.example.com/a.png", "cdn.example.com"
    ) == "/a.png"


def senders_json(size="20480", width="1920", height="1080", md5="5Q0Zt9eGjKk="):
    """v1 存在 ``image:<sha>`` 里的钩子返回（又拍云返回值含大小与像素）。"""
    return json.dumps(
        [
            {
                "code": 0,
                "sender": "up2upyun",
                "basedir": "/sapic",
                "file-type": "file",
                "file-size": size,
                "width": width,
                "height": height,
                "frames": "1",
                "content-md5": md5,
            }
        ]
    )


def test_sender_meta_normalizes_keys_and_reads_content_length():
    """v1 里大小有时只记在 ``content-length``，键名大小写/下划线也不统一。"""
    meta = {
        "senders": json.dumps(
            [
                {
                    "code": 0,
                    "sender": "up2upyun",
                    "Content-Length": "2048",
                    "Width": "800",
                    "Height": "600",
                }
            ]
        )
    }
    result = MIGRATE.sender_meta(meta)
    assert MIGRATE.sender_size(result) == 2048
    assert MIGRATE.sender_dims(result) == (800, 600)

    #: upyun 的 ``file-size`` 仍然优先，两者都在时用它。
    preferred = MIGRATE.sender_meta(
        {"senders": senders_json(size="4096")}
    )
    assert MIGRATE.sender_size(preferred) == 4096

    #: 失败的结果（code != 0）不该被当成元数据来源。
    assert MIGRATE.sender_meta(
        {"senders": json.dumps([{"code": 1, "file-size": "1"}])}
    ) == {}


def test_bucket_objects_are_adopted_instead_of_external(app, tmp_path, monkeypatch):
    """v1 用又拍云/七牛时字节还在 bucket 里：登记副本，不能降级成外链。"""
    src = "https://cdn.example.com/sapic/2024/01/02/photo.png"
    #: 主后端是云存储：配置里有公开域名，对象已经在同一个 bucket 里。
    monkeypatch.setattr(
        MIGRATE,
        "driver_backend",
        lambda backend: {"config": {"domain": "https://cdn.example.com"}},
    )
    migrator = MIGRATE.Migrator(make_args(tmp_path))
    data = payload({"src": src, "senders": senders_json()})
    with app.app_context():
        stats = migrator.run(data["users"].items(), data["images"])

        assert stats["images_adopted"] == 1
        assert stats["images_external"] == 0
        assert not migrator.failures

        image = Image.get(Image.sha == SHA)
        #: 不再是外链：字节归副本管，删除会真正删掉对象。
        assert image.source_url is None
        #: v1 的 ``senders`` 里记了大小/尺寸，不能再显示 0 B / 未知。
        assert image.size == 20480
        assert image.mime == "image/png"
        assert (image.width, image.height) == (1920, 1080)

        replica = ImageBackend.get(ImageBackend.image == image)
        assert replica.object_key == "/sapic/2024/01/02/photo.png"
        assert replica.url == src
        assert replica.state == "ok"
        assert replica.is_primary is True
        assert replica.size == 20480
        assert replica.etag == "5Q0Zt9eGjKk="


def test_refresh_external_backfills_metadata_of_adopted_rows(app, tmp_path, monkeypatch):
    """早年采纳过、但缺大小/尺寸的行，重跑 ``--refresh-external`` 能补齐。"""
    src = "https://cdn.example.com/sapic/2024/01/02/photo.png"
    monkeypatch.setattr(
        MIGRATE,
        "driver_backend",
        lambda backend: {"config": {"domain": "https://cdn.example.com"}},
    )

    first, _ = run(app, tmp_path, data=payload({"src": src}))
    assert first["images_adopted"] == 1
    with app.app_context():
        image = Image.get(Image.sha == SHA)
        assert image.source_url is None
        assert image.size == 0
        assert image.width is None

    second, _ = run(
        app,
        tmp_path,
        data=payload({"src": src, "senders": senders_json()}),
        refresh_external=True,
    )
    assert second["images_adopted"] == 0
    with app.app_context():
        image = Image.get(Image.sha == SHA)
        assert (image.size, image.mime) == (20480, "image/png")
        assert (image.width, image.height) == (1920, 1080)
        #: 副本没有重复创建。
        assert (
            ImageBackend.select().where(ImageBackend.image == image).count() == 1
        )


def test_refresh_external_repairs_previous_runs(app, tmp_path, monkeypatch):
    """之前记成外链的行，配上域名 + ``--refresh-external`` 后能补成副本。"""
    src = "https://cdn.example.com/sapic/2024/01/02/photo.png"
    data = payload({"src": src})

    #: 第一遍：主后端没有公开域名，只能登记外链。
    monkeypatch.setattr(MIGRATE, "driver_backend", lambda backend: {"config": {}})
    with app.app_context():
        stats = MIGRATE.Migrator(make_args(tmp_path)).run(
            data["users"].items(), data["images"]
        )
        assert stats["images_external"] == 1
        assert Image.get(Image.sha == SHA).source_url == src

    #: 只加 --refresh-external 但没配域名：什么都不改，但要说清楚为什么。
    with app.app_context():
        skipped = MIGRATE.Migrator(make_args(tmp_path, refresh_external=True))
        stats = skipped.run(data["users"].items(), data["images"])
        assert stats["images_refresh_skipped"] == 1
        assert skipped.unmatched and SHA in skipped.unmatched[0]
        assert Image.get(Image.sha == SHA).source_url == src

    #: 第二遍补上域名：外链升级成 ok 副本，``source_url`` 清掉。
    monkeypatch.setattr(
        MIGRATE,
        "driver_backend",
        lambda backend: {"config": {"domain": "https://cdn.example.com"}},
    )
    with app.app_context():
        stats = MIGRATE.Migrator(
            make_args(tmp_path, refresh_external=True)
        ).run(data["users"].items(), data["images"])
        assert stats["images_existing"] == 1
        assert stats["images_adopted"] == 1
        image = Image.get(Image.sha == SHA)
        assert image.source_url is None
        replica = ImageBackend.get(ImageBackend.image == image)
        assert replica.object_key == "/sapic/2024/01/02/photo.png"
        assert replica.state == "ok"


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
