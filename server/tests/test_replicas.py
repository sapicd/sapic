# -*- coding: utf-8 -*-
"""Multi-backend uploads: synchronous primary, asynchronous replicas."""

import io

import pytest

from sapic.libs.settings import set_setting
from sapic.libs.storage import flush_replicas
from sapic.models import Image, ImageBackend, StorageBackend, User


def register_and_login(client, username="alice"):
    client.post(
        "/api/v2/auth/register",
        json={
            "username": username,
            "password": "secret123",
            "email": "%s@example.com" % username,
        },
    )
    response = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return response.get_json()["data"]["csrf"]


@pytest.fixture()
def admin(app, client):
    csrf = register_and_login(client)
    with app.app_context():
        user = User.get(User.username == "alice")
        user.is_admin = True
        user.save(only=[User.is_admin])
    return csrf


def upload(client, csrf):
    return client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


def add_backend(client, csrf, name, root, priority, domain=""):
    config = {"root": str(root)}
    if domain:
        config["domain"] = domain
    response = client.post(
        "/api/v2/backends",
        json={"name": name, "hook_name": "up2local", "config": config, "priority": priority},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def test_upload_fans_out_to_all_backends(app, client, admin, tmp_path):
    with app.app_context():
        set_setting("storage_replica", True)
    mirror_root = tmp_path / "mirror"
    add_backend(client, admin, "mirror", mirror_root, 10, "https://cdn.mirror")

    response = upload(client, admin)
    assert response.status_code == 201, response.get_json()
    image = response.get_json()["data"]["image"]
    #: 优先级最高的后端同步写入，直链也用它。
    assert image["src"].startswith("https://cdn.mirror/")

    flush_replicas()
    with app.app_context():
        rows = list(ImageBackend.select().order_by(ImageBackend.id))
        assert [row.state for row in rows] == ["ok", "ok"]
        assert [row.backend.name for row in rows] == ["mirror", "up2local"]
        assert [row.is_primary for row in rows] == [True, False]
    assert any(mirror_root.rglob("photo-*.png"))

    #: 作者能看到每个副本的对象路径，方便核对云端是否真的落盘。
    sha = image["sha"]
    detail = client.get("/api/v2/images/%s" % sha).get_json()["data"]["image"]
    by_name = {item["backend"]: item for item in detail["replicas"]}
    assert by_name["up2local"]["key"].startswith("alice/")
    assert by_name["mirror"]["url"].startswith("https://cdn.mirror/")

    #: 内部路径与失败原因只给作者/管理员，访客只看到状态。
    anon = app.test_client().get("/api/v2/images/%s" % sha)
    assert anon.status_code == 200, anon.get_json()
    assert all("key" not in item for item in anon.get_json()["data"]["image"]["replicas"])


def test_replica_can_be_turned_off(app, client, admin, tmp_path):
    add_backend(client, admin, "mirror", tmp_path / "mirror", 200)
    #: conftest 默认关闭多副本，这里验证「关掉就只有单副本」。
    assert upload(client, admin).status_code == 201
    flush_replicas()

    with app.app_context():
        assert ImageBackend.select().count() == 1


def test_failed_replica_does_not_break_the_upload(app, client, admin, tmp_path):
    with app.app_context():
        set_setting("storage_replica", True)
    #: 用一个普通文件充当「存储根目录」，写入必然失败。
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    add_backend(client, admin, "broken", blocked, 200)

    response = upload(client, admin)
    assert response.status_code == 201, response.get_json()

    flush_replicas()
    with app.app_context():
        broken = ImageBackend.get(ImageBackend.backend == StorageBackend.get(
            StorageBackend.name == "broken"
        ))
        assert broken.state == "failed"
        assert broken.last_error
        #: 主副本仍然可读，图片不受影响。
        assert ImageBackend.get(ImageBackend.is_primary == True).state == "ok"  # noqa: E712
        assert Image.select().count() == 1


def test_failed_replica_does_not_block_backend_removal(app, client, admin, tmp_path):
    with app.app_context():
        set_setting("storage_replica", True)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    add_backend(client, admin, "broken", blocked, 200)
    assert upload(client, admin).status_code == 201
    flush_replicas()

    with app.app_context():
        broken_id = StorageBackend.get(StorageBackend.name == "broken").id
    removed = client.delete(
        "/api/v2/backends/%d" % broken_id, headers={"X-CSRF-Token": admin}
    )
    #: 失败的副本没有数据，不该阻止删除后端。
    assert removed.status_code == 200, removed.get_json()
