# -*- coding: utf-8 -*-
"""System vs user owned storage backends (the user backend seam)."""

import io

import pytest

from sapic.libs.settings import set_setting
from sapic.libs.storage import flush_replicas, list_backends
from sapic.migrations import _v007_storage_scope_system
from sapic.models import ImageBackend, StorageBackend, User
from sapic.models.storage import SCOPE_SYSTEM, SCOPE_USER


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
def bob(app, client):
    """bob 带一个自己定义的存储后端（scope=user）。"""
    csrf = register_and_login(client, "bobby")
    with app.app_context():
        user = User.get(User.username == "bobby")
        StorageBackend.create(
            name="bob-disk",
            hook_name="up2local",
            config={"root": str(app.config["STORAGE_DIR"]) + "/bob"},
            scope=SCOPE_USER,
            owner=user,
            visibility="private",
            priority=10,
        )
    return csrf


def upload(client, csrf):
    response = client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["image"]


def test_user_backend_is_ignored_until_the_switch_is_on(app, client, bob):
    upload(client, bob)
    flush_replicas()
    with app.app_context():
        row = ImageBackend.get()
        assert row.backend.scope == SCOPE_SYSTEM

    with app.app_context():
        set_setting("allow_user_backends", True)

    upload(client, bob)
    flush_replicas()
    with app.app_context():
        latest = ImageBackend.select().order_by(ImageBackend.id.desc()).get()
        assert latest.backend.scope == SCOPE_USER
        assert latest.backend.name == "bob-disk"


def test_other_users_never_see_a_personal_backend(app, client, bob):
    with app.app_context():
        set_setting("allow_user_backends", True)
        alice = User.create(
            username="alice2",
            password_hash="x",
            email="alice2@example.com",
            status=1,
        )
        #: 系统后端 + 别人的用户后端，alice2 只能拿到系统那份。
        names = [item["name"] for item in list_backends(alice)]
        assert "bob-disk" not in names
        assert names

        bob_user = User.get(User.username == "bobby")
        assert "bob-disk" in [item["name"] for item in list_backends(bob_user)]


def test_admin_api_only_lists_system_backends(app, client, bob):
    with app.app_context():
        bob_user = User.get(User.username == "bobby")
        bob_user.is_admin = True
        bob_user.save(only=[User.is_admin])

    items = client.get("/api/v2/backends").get_json()["data"]["items"]
    assert {item["scope"] for item in items} == {SCOPE_SYSTEM}
    assert "bob-disk" not in [item["name"] for item in items]


def test_legacy_global_scope_is_renamed(app):
    with app.app_context():
        row = StorageBackend.create(
            name="legacy", hook_name="up2local", scope="global", priority=900
        )
        _v007_storage_scope_system()
        row = StorageBackend.get_by_id(row.id)
        assert row.scope == SCOPE_SYSTEM
