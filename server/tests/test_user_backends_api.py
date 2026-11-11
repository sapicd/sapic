# -*- coding: utf-8 -*-
"""User facing storage backends (/api/v2/me/backends)."""

import io

import pytest

from sapic.libs.hook import get_hook_manager
from sapic.libs.settings import get_setting, set_setting
from sapic.libs.storage import create_user_backend, flush_replicas
from sapic.models import ImageBackend, StorageBackend, User
from sapic.models.storage import SCOPE_USER


def register_and_login(client, username):
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
def user_client(app, client):
    csrf = register_and_login(client, "bobby")
    with app.app_context():
        set_setting("allow_user_backends", True)
    return client, csrf


def create(client, csrf, tmp_path, name="my-disk", priority=None):
    payload = {
        "name": name,
        "hook_name": "up2local",
        "config": {"root": str(tmp_path / name)},
    }
    if priority is not None:
        payload["priority"] = priority
    return client.post(
        "/api/v2/me/backends", json=payload, headers={"X-CSRF-Token": csrf}
    )


def test_feature_flag_gates_the_api(app, client):
    csrf = register_and_login(client, "bobby")
    body = client.get("/api/v2/me/backends").get_json()["data"]
    assert body["enabled"] is False
    assert body["items"] == []

    blocked = client.post(
        "/api/v2/me/backends",
        json={"hook_name": "up2local", "config": {}},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 403


def test_owner_can_create_and_use_a_backend(app, user_client, tmp_path):
    client, csrf = user_client
    created = create(client, csrf, tmp_path)
    assert created.status_code == 201, created.get_json()
    item = created.get_json()["data"]["items"][0]
    assert item["scope"] == SCOPE_USER
    assert item["configured"] is True
    assert item["in_use"] is True  #: 用户后端默认优先级 50，排在系统后端之前

    response = client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    flush_replicas()
    with app.app_context():
        replica = ImageBackend.get(ImageBackend.is_primary == True)  # noqa: E712
        assert replica.backend.scope == SCOPE_USER
        assert replica.backend.name == "my-disk"


def test_secrets_are_masked_and_kept_on_edit(app, user_client):
    client, csrf = user_client
    with app.app_context():
        states = dict(get_setting("hooks_state", {}) or {})
        states["up2upyun"] = True
        set_setting("hooks_state", states)
        get_hook_manager().reload()

    config = {
        "domain": "https://cdn.example.com",
        "bucket": "demo",
        "username": "operator",
        "password": "secret",
    }
    with app.app_context():
        user = User.get(User.username == "bobby")
        row = create_user_backend(user, "upy", "up2upyun", config)

    items = client.get("/api/v2/me/backends").get_json()["data"]["items"]
    masked = next(item for item in items if item["id"] == row.id)
    assert masked["config"]["password"] == "******"
    assert masked["config"]["bucket"] == "demo"

    #: 原样回传掩码表示「不修改密码」，其它字段照常更新。
    masked["config"]["bucket"] = "demo2"
    updated = client.patch(
        "/api/v2/me/backends/%d" % row.id,
        json={"config": masked["config"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.status_code == 200, updated.get_json()
    with app.app_context():
        stored = StorageBackend.get_by_id(row.id)
        assert stored.config["password"] == "secret"
        assert stored.config["bucket"] == "demo2"


def test_limit_and_ownership(app, user_client, tmp_path):
    client, csrf = user_client
    with app.app_context():
        set_setting("user_backend_limit", 1)

    assert create(client, csrf, tmp_path, "one").status_code == 201
    over = create(client, csrf, tmp_path, "two")
    assert over.status_code == 409

    #: 另一个用户看不到、也改不了别人的后端。
    other = app.test_client()
    other_csrf = register_and_login(other, "alice2")
    assert other.get("/api/v2/me/backends").get_json()["data"]["items"] == []

    with app.app_context():
        mine = StorageBackend.get(StorageBackend.scope == SCOPE_USER)
    assert (
        other.patch(
            "/api/v2/me/backends/%d" % mine.id,
            json={"name": "hijack"},
            headers={"X-CSRF-Token": other_csrf},
        ).status_code
        == 404
    )


def test_delete_with_replicas_is_refused(app, user_client, tmp_path):
    client, csrf = user_client
    created = create(client, csrf, tmp_path)
    backend_id = created.get_json()["data"]["items"][0]["id"]

    client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    flush_replicas()

    removed = client.delete(
        "/api/v2/me/backends/%d" % backend_id, headers={"X-CSRF-Token": csrf}
    )
    assert removed.status_code == 409
