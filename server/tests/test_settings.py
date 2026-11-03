# -*- coding: utf-8 -*-
import io

from sapic.models import User


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


def test_settings_requires_admin(client):
    register_and_login(client)
    assert client.get("/api/v2/settings").status_code == 403


def test_admin_reads_and_writes_settings(app, client):
    csrf = register_and_login(client)
    promote_admin(app)

    data = client.get("/api/v2/settings").get_json()["data"]["items"]
    assert data["site_name"] == "sapic"
    assert data["upload_max_size"] == 20

    response = client.put(
        "/api/v2/settings",
        json={"site_name": "我的图床", "upload_max_size": 5, "allow_video": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    items = response.get_json()["data"]["items"]
    assert items["site_name"] == "我的图床"
    assert items["upload_max_size"] == 5
    assert items["allow_video"] is False

    site = client.get("/api/v2/site").get_json()["data"]
    assert site["name"] == "我的图床"
    assert site["allow_video"] is False


def test_settings_reject_invalid_value(app, client):
    csrf = register_and_login(client)
    promote_admin(app)

    response = client.put(
        "/api/v2/settings",
        json={"upload_max_size": "abc"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    response = client.put(
        "/api/v2/settings",
        json={"not_a_setting": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400


def test_upload_respects_site_limits(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    client.put(
        "/api/v2/settings",
        json={"upload_allowed_ext": "png", "upload_max_size": 1},
        headers={"X-CSRF-Token": csrf},
    )

    rejected = client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"GIF89a"), "photo.gif")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["code"] == "PARAM_ERROR"

    too_big = client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"x" * (1024 * 1024 + 1)), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert too_big.status_code == 413


def test_register_review_and_reserved_username(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    client.put(
        "/api/v2/settings",
        json={"register_review": True, "forbidden_username": "root,system"},
        headers={"X-CSRF-Token": csrf},
    )

    guest = app.test_client()
    reserved = guest.post(
        "/api/v2/auth/register",
        json={"username": "root", "password": "secret123"},
    )
    assert reserved.status_code == 400

    response = guest.post(
        "/api/v2/auth/register",
        json={"username": "bobby", "password": "secret123"},
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["user"]["status"] == -1
