# -*- coding: utf-8 -*-
import io

import pytest

from sapic.models import Album, Image, ImageBackend, User


def register(client, username, password="secret123"):
    return client.post(
        "/api/v2/auth/register",
        json={
            "username": username,
            "password": password,
            "email": "%s@example.com" % username,
        },
    )


def register_and_login(client, username="alice"):
    register(client, username)
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


def user_id(app, username):
    with app.app_context():
        return User.get(User.username == username).id


@pytest.fixture()
def admin(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    return csrf


def test_users_requires_admin(client):
    register_and_login(client)
    assert client.get("/api/v2/users").status_code == 403


def test_admin_lists_and_filters_users(app, client, admin):
    register(app.test_client(), "bobby")

    data = client.get("/api/v2/users").get_json()["data"]
    assert data["counts"] == {"total": 2, "pending": 0}
    assert {item["username"] for item in data["items"]} == {"alice", "bobby"}
    assert all("email" in item for item in data["items"])

    filtered = client.get(
        "/api/v2/users", query_string={"keyword": "bob"}
    ).get_json()["data"]
    assert [item["username"] for item in filtered["items"]] == ["bobby"]

    pending = client.get(
        "/api/v2/users", query_string={"status": -1}
    ).get_json()["data"]
    assert pending["items"] == []


def test_admin_reviews_and_disables_user(app, client, admin):
    register(app.test_client(), "bobby")
    bobby = user_id(app, "bobby")

    approved = client.patch(
        "/api/v2/users/%d" % bobby,
        json={"status": 1},
        headers={"X-CSRF-Token": admin},
    )
    assert approved.status_code == 200
    assert approved.get_json()["data"]["user"]["status"] == 1

    disabled = client.patch(
        "/api/v2/users/%d" % bobby,
        json={"status": 0},
        headers={"X-CSRF-Token": admin},
    )
    assert disabled.get_json()["data"]["user"]["status"] == 0
    #: 禁用后已有凭据不再可用。
    login = app.test_client().post(
        "/api/v2/auth/login",
        json={"username": "bobby", "password": "secret123"},
    )
    assert login.status_code == 403


def test_admin_grants_admin_flag(app, client, admin):
    register(app.test_client(), "bobby")
    bobby = user_id(app, "bobby")

    response = client.patch(
        "/api/v2/users/%d" % bobby,
        json={"is_admin": True},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["is_admin"] is True


def test_admin_cannot_lock_itself(app, client, admin):
    alice = user_id(app, "alice")

    status = client.patch(
        "/api/v2/users/%d" % alice,
        json={"status": 0},
        headers={"X-CSRF-Token": admin},
    )
    assert status.status_code == 403

    demote = client.patch(
        "/api/v2/users/%d" % alice,
        json={"is_admin": False},
        headers={"X-CSRF-Token": admin},
    )
    assert demote.status_code == 403


def test_admin_deletes_user_with_owned_data(app, client, admin):
    bobby_client = app.test_client()
    register(bobby_client, "bobby")
    csrf = bobby_client.post(
        "/api/v2/auth/login",
        json={"username": "bobby", "password": "secret123"},
    ).get_json()["data"]["csrf"]
    bobby_client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    bobby = user_id(app, "bobby")

    response = client.delete(
        "/api/v2/users/%d" % bobby, headers={"X-CSRF-Token": admin}
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {"deleted": True}
    with app.app_context():
        assert User.get_or_none(User.id == bobby) is None
        #: 账号名与图片 sha 都要能被重新使用，所以是硬删除而不是软删除。
        assert Album.select().where(Album.owner == bobby).count() == 0
        assert Image.select().where(Image.owner == bobby).count() == 0
        assert ImageBackend.select().count() == 0


def test_admin_cannot_delete_itself_or_missing_user(app, client, admin):
    alice = user_id(app, "alice")
    headers = {"X-CSRF-Token": admin}

    assert client.delete("/api/v2/users/%d" % alice, headers=headers).status_code == 403
    assert client.delete("/api/v2/users/9999", headers=headers).status_code == 404


def test_delete_user_requires_admin(client):
    register_and_login(client)
    assert client.delete("/api/v2/users/1").status_code == 403


def test_admin_rejects_invalid_updates(app, client, admin):
    register(app.test_client(), "bobby")
    bobby = user_id(app, "bobby")
    headers = {"X-CSRF-Token": admin}

    for payload in ({"status": 9}, {"status": True}, {"status": "1"}, {"is_admin": 1}, {}):
        response = client.patch(
            "/api/v2/users/%d" % bobby, json=payload, headers=headers
        )
        assert response.status_code == 400, payload

    missing = client.patch("/api/v2/users/9999", json={"status": 1}, headers=headers)
    assert missing.status_code == 404
