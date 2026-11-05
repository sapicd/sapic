# -*- coding: utf-8 -*-
"""Storage backend management: provisioning, priority and safety guards."""

import io

import pytest

from sapic.models import ImageBackend, StorageBackend, User


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


def promote_admin(app, username="alice"):
    with app.app_context():
        user = User.get(User.username == username)
        user.is_admin = True
        user.save(only=[User.is_admin])


@pytest.fixture()
def admin(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    return csrf


def upload(client, csrf):
    return client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


def backends(client):
    return client.get("/api/v2/backends").get_json()["data"]


def test_enabling_a_storage_hook_provisions_a_backend(client, admin):
    data = backends(client)
    assert [item["hook_name"] for item in data["items"]] == ["up2local"]
    assert data["items"][0]["in_use"] is True
    assert {driver["name"] for driver in data["drivers"]} >= {"up2local"}

    client.patch(
        "/api/v2/hooks/up2upyun",
        json={"enabled": True},
        headers={"X-CSRF-Token": admin},
    )

    names = [item["hook_name"] for item in backends(client)["items"]]
    assert names == ["up2local", "up2upyun"]


def test_priority_decides_where_uploads_go(app, client, admin, tmp_path):
    root = tmp_path / "alt"
    created = client.post(
        "/api/v2/backends",
        json={
            "name": "alt",
            "hook_name": "up2local",
            "config": {"root": str(root)},
            "priority": 10,
        },
        headers={"X-CSRF-Token": admin},
    )
    assert created.status_code == 201, created.get_json()

    response = upload(client, admin)
    assert response.status_code == 201, response.get_json()

    assert any(root.rglob("photo-*.png"))
    with app.app_context():
        replica = ImageBackend.get()
        assert replica.backend.name == "alt"
        alt_id = replica.backend_id

    #: 把 alt 排到后面，上传就该回到 local。
    moved = client.patch(
        "/api/v2/backends/%d" % alt_id,
        json={"priority": 500},
        headers={"X-CSRF-Token": admin},
    )
    assert moved.status_code == 200
    assert moved.get_json()["data"]["items"][0]["hook_name"] == "up2local"

    second = upload(client, admin)
    assert second.status_code == 201
    with app.app_context():
        assert ImageBackend.select().count() == 2
        latest = ImageBackend.select().order_by(ImageBackend.id.desc()).get()
        assert latest.backend.name == "up2local"


def test_backend_holding_replicas_cannot_be_removed(app, client, admin):
    assert upload(client, admin).status_code == 201
    with app.app_context():
        backend_id = ImageBackend.get().backend_id

    disabled = client.patch(
        "/api/v2/backends/%d" % backend_id,
        json={"enabled": False},
        headers={"X-CSRF-Token": admin},
    )
    assert disabled.status_code == 409, disabled.get_json()
    assert disabled.get_json()["code"] == "CONFLICT"

    removed = client.delete(
        "/api/v2/backends/%d" % backend_id, headers={"X-CSRF-Token": admin}
    )
    assert removed.status_code == 409


def test_deleting_the_last_backend_switches_the_hook_off(client, admin):
    backends(client)
    created = client.post(
        "/api/v2/backends",
        json={"name": "alt", "hook_name": "up2local", "priority": 900},
        headers={"X-CSRF-Token": admin},
    )
    assert created.status_code == 201

    for row in list(created.get_json()["data"]["items"]):
        removed = client.delete(
            "/api/v2/backends/%d" % row["id"], headers={"X-CSRF-Token": admin}
        )
        assert removed.status_code == 200, removed.get_json()

    hooks = client.get("/api/v2/hooks").get_json()["data"]["items"]
    local = next(item for item in hooks if item["name"] == "up2local")
    #: 删掉最后一个后端等于停用该驱动，否则下次 sync 又会把它建回来。
    assert local["enabled"] is False
    assert backends(client)["items"] == []


def test_last_enabled_backend_cannot_be_disabled(client, admin):
    backend_id = backends(client)["items"][0]["id"]
    response = client.patch(
        "/api/v2/backends/%d" % backend_id,
        json={"enabled": False},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 409


def test_backend_config_is_validated(client, admin):
    headers = {"X-CSRF-Token": admin}

    unknown = client.post(
        "/api/v2/backends",
        json={"hook_name": "up2local", "config": {"nope": "x"}},
        headers=headers,
    )
    assert unknown.status_code == 400

    disabled = client.post(
        "/api/v2/backends", json={"hook_name": "up2upyun"}, headers=headers
    )
    assert disabled.status_code == 409

    duplicate = client.post(
        "/api/v2/backends",
        json={"name": "up2local", "hook_name": "up2local"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    #: 未命名时自动派生并加序号，不会和自动创建的那行撞名。
    anonymous = client.post(
        "/api/v2/backends", json={"hook_name": "up2local"}, headers=headers
    )
    assert anonymous.status_code == 201
    assert [item["name"] for item in anonymous.get_json()["data"]["items"]][-1:] == [
        "up2local-2"
    ]


def test_required_driver_config_is_enforced(client, admin):
    headers = {"X-CSRF-Token": admin}
    client.patch("/api/v2/hooks/up2upyun", json={"enabled": True}, headers=headers)

    #: 刚启用的驱动还没填必填项，列表里标成「待配置」。
    row = next(
        item for item in backends(client)["items"] if item["hook_name"] == "up2upyun"
    )
    assert row["configured"] is False

    missing = client.post(
        "/api/v2/backends", json={"hook_name": "up2upyun"}, headers=headers
    )
    assert missing.status_code == 400
    assert "missing required config" in missing.get_json()["message"]

    ok_row = client.post(
        "/api/v2/backends",
        json={
            "name": "upy-2",
            "hook_name": "up2upyun",
            "config": {
                "domain": "https://cdn.example.com",
                "bucket": "demo",
                "username": "operator",
                "password": "secret",
            },
        },
        headers=headers,
    )
    assert ok_row.status_code == 201
    created = next(
        item for item in ok_row.get_json()["data"]["items"] if item["name"] == "upy-2"
    )
    assert created["configured"] is True


def test_hook_config_values_are_migrated_into_the_backend_row(app, client, admin):
    from sapic.libs.settings import get_setting, set_setting

    with app.app_context():
        config = dict(get_setting("hooks_config", {}) or {})
        config["up2upyun"] = {
            "domain": "https://cdn.example.com",
            "bucket": "legacy",
            "username": "operator",
            "password": "secret",
            "basedir": "/pics",
        }
        set_setting("hooks_config", config)

    headers = {"X-CSRF-Token": admin}
    client.patch("/api/v2/hooks/up2upyun", json={"enabled": True}, headers=headers)

    row = next(
        item for item in backends(client)["items"] if item["hook_name"] == "up2upyun"
    )
    #: 旧版本把凭据存在钩子配置里，启用后自动搬进后端行，不需要重填。
    assert row["config"]["bucket"] == "legacy"
    assert row["config"]["basedir"] == "/pics"
    assert row["configured"] is True


def test_backend_api_requires_admin(client):
    register_and_login(client)
    assert client.get("/api/v2/backends").status_code == 403
    assert client.post("/api/v2/backends", json={}).status_code == 403
