# -*- coding: utf-8 -*-
"""``migrate_backend``: copy replicas to a target, optionally deleting the source."""

from sapic.libs import storage as storage_mod
from sapic.models import Image, ImageBackend, StorageBackend


def _backend(name: str) -> StorageBackend:
    return StorageBackend.create(name=name, hook_name="up2local", enabled=True)


def _image(sha: str) -> Image:
    return Image.create(sha=sha, filename="a.png")


def test_migrate_rewrites_sole_replicas_and_drops_redundant(app, monkeypatch):
    with app.app_context():
        source = _backend("src")
        target = _backend("dst")

        sole = _image("sha-sole")
        ImageBackend.create(
            image=sole,
            backend=source,
            object_key="alice/2026/sole.png",
            state="ok",
            is_primary=True,
        )

        dup = _image("sha-dup")
        ImageBackend.create(
            image=dup,
            backend=source,
            object_key="alice/2026/dup.png",
            state="ok",
            is_primary=True,
        )
        ImageBackend.create(image=dup, backend=target, object_key="dup.png", state="ok")

        monkeypatch.setattr(
            storage_mod, "read_object", lambda image, replica: b"payload"
        )
        monkeypatch.setattr(
            storage_mod,
            "save_object",
            lambda backend, sha, filename, stream, upload_path: {
                "code": 0,
                "path": "moved/%s" % filename,
                "size": len(stream),
                "etag": "e2",
            },
        )
        monkeypatch.setattr(storage_mod, "delete_object", lambda image, replica: True)

        result = storage_mod.migrate_backend(source, target, delete_source=True)

    assert result["moved"] == 1
    assert result["deleted"] == 1
    assert result["failed"] == 0

    with app.app_context():
        #: 唯一副本：迁移到目标后端，object_key 采用驱动返回的新 key。
        sole_row = ImageBackend.get(
            (ImageBackend.image == sole) & (ImageBackend.state == "ok")
        )
        assert sole_row.backend_id == target.id
        assert sole_row.object_key == "moved/sole.png"

        #: 冗余副本：源后端上的行已删除，只剩目标后端那条。
        dup_rows = list(ImageBackend.select().where(ImageBackend.image == dup))
        assert len(dup_rows) == 1
        assert dup_rows[0].backend_id == target.id


def test_migrate_keeps_the_source_when_the_target_write_fails(app, monkeypatch):
    with app.app_context():
        source = _backend("src")
        target = _backend("dst")
        sole = _image("sha-sole")
        ImageBackend.create(
            image=sole,
            backend=source,
            object_key="alice/2026/sole.png",
            state="ok",
            is_primary=True,
        )

        monkeypatch.setattr(
            storage_mod, "read_object", lambda image, replica: b"payload"
        )
        monkeypatch.setattr(
            storage_mod,
            "save_object",
            lambda backend, sha, filename, stream, upload_path: {
                "code": 1,
                "message": "save failed",
            },
        )

        result = storage_mod.migrate_backend(source, target)

    assert result["moved"] == 0
    assert result["failed"] == 1

    with app.app_context():
        #: 目标写失败时源副本必须原样保留，不能丢数据。
        row = ImageBackend.get(
            (ImageBackend.image == sole) & (ImageBackend.state == "ok")
        )
        assert row.backend_id == source.id


def test_migrate_copies_by_default_and_keeps_the_source(app, monkeypatch):
    with app.app_context():
        source = _backend("src")
        target = _backend("dst")
        image = _image("sha-copy")
        ImageBackend.create(
            image=image,
            backend=source,
            object_key="alice/2026/copy.png",
            state="ok",
            is_primary=True,
        )

        monkeypatch.setattr(
            storage_mod, "read_object", lambda image, replica: b"payload"
        )
        monkeypatch.setattr(
            storage_mod,
            "save_object",
            lambda backend, sha, filename, stream, upload_path: {
                "code": 0,
                "path": "copied/%s" % filename,
                "size": len(stream),
                "etag": "e3",
            },
        )
        #: 复制模式绝不能删源站对象。
        monkeypatch.setattr(
            storage_mod,
            "delete_object",
            lambda image, replica: (_ for _ in ()).throw(
                AssertionError("delete_object must not be called")
            ),
        )

        result = storage_mod.migrate_backend(source, target)

    assert result == {
        "moved": 0,
        "copied": 1,
        "deleted": 0,
        "failed": 0,
        "errors": [],
    }

    with app.app_context():
        rows = {
            row.backend_id: row
            for row in ImageBackend.select().where(ImageBackend.image == image)
        }
        assert source.id in rows
        assert rows[source.id].object_key == "alice/2026/copy.png"
        assert rows[source.id].is_primary is True
        assert target.id in rows
        assert rows[target.id].object_key == "copied/copy.png"
        assert rows[target.id].state == "ok"
