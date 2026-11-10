# -*- coding: utf-8 -*-
"""Self-service account deletion: password check, empty gallery, admin guard."""

import io

from sapic.models import ApiToken, Image, User

USER = {
    "username": "erin",
    "password": "secret123",
    "email": "erin@example.com",
}


def register(client):
    client.post("/api/v2/auth/register", json=USER)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": USER["username"], "password": USER["password"]},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["csrf"]


def delete_account(client, csrf, password):
    return client.delete(
        "/api/v2/auth/account",
        json={"password": password},
        headers={"X-CSRF-Token": csrf},
    )


def test_requires_login(client):
    assert client.delete("/api/v2/auth/account", json={"password": "x"}).status_code == 401


def test_wrong_password_is_refused(app, client):
    csrf = register(client)
    response = delete_account(client, csrf, "not-my-password")
    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"
    with app.app_context():
        assert User.get_or_none(User.username == USER["username"]) is not None


def test_images_block_deletion(app, client):
    csrf = register(client)
    upload = client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert upload.status_code in (200, 201), upload.get_json()

    response = delete_account(client, csrf, USER["password"])
    assert response.status_code == 409
    assert "image" in response.get_json()["message"]
    with app.app_context():
        assert Image.select().count() == 1


def test_deletes_account_and_revokes_session(app, client):
    csrf = register(client)
    created = client.post(
        "/api/v2/auth/tokens",
        json={"name": "cli", "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201

    response = delete_account(client, csrf, USER["password"])
    assert response.status_code == 200
    assert response.get_json()["data"]["deleted"] is True

    with app.app_context():
        assert User.get_or_none(User.username == USER["username"]) is None
        assert ApiToken.select().count() == 0
    #: 会话已清，后续请求按未登录处理。
    assert client.get("/api/v2/auth/session").get_json()["data"]["user"] is None


def test_admins_cannot_delete_themselves(app, client):
    csrf = register(client)
    with app.app_context():
        User.update(is_admin=True).where(User.username == USER["username"]).execute()

    response = delete_account(client, csrf, USER["password"])
    assert response.status_code == 403
    assert "admin" in response.get_json()["message"]
    with app.app_context():
        assert User.get_or_none(User.username == USER["username"]) is not None
