# -*- coding: utf-8 -*-
"""Plaza listing: publishing is explicit, permission still comes from visibility."""

import io

from sapic.libs.settings import set_setting


def register_and_login(client):
    client.post(
        "/api/v2/auth/register",
        json={
            "username": "alice",
            "password": "secret123",
            "email": "alice@example.com",
        },
    )
    response = client.post(
        "/api/v2/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    return response.get_json()["data"]["csrf"]


def upload(client, csrf, filename="photo.png"):
    return client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"fake-image-bytes"), filename)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


def plaza_items(client):
    return client.get("/api/v2/plaza").get_json()["data"]["items"]


def test_plaza_lists_only_pushed_images(app, client):
    csrf = register_and_login(client)
    image = upload(client, csrf).get_json()["data"]["image"]
    anonymous = app.test_client()

    #: 默认不上广场，即使图片落在公开相册里。
    assert plaza_items(anonymous) == []

    pushed = client.patch(
        "/api/v2/albums/%s" % image["album_id"],
        json={"plaza": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert pushed.status_code == 200
    assert [item["sha"] for item in plaza_items(anonymous)] == [image["sha"]]

    #: 单图可以把自己排除掉。
    client.patch(
        "/api/v2/images/%s" % image["sha"],
        json={"plaza": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert plaza_items(anonymous) == []

    #: 空值表示重新跟随相册。
    client.patch(
        "/api/v2/images/%s" % image["sha"],
        json={"plaza": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert len(plaza_items(anonymous)) == 1


def test_plaza_requires_public_visibility(app, client):
    csrf = register_and_login(client)
    image = upload(client, csrf).get_json()["data"]["image"]
    anonymous = app.test_client()

    client.patch(
        "/api/v2/albums/%s" % image["album_id"],
        json={"plaza": True, "visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    )
    #: 发布只是曝光开关，私有图片不会因为被标记就出现在广场。
    assert plaza_items(anonymous) == []

    client.patch(
        "/api/v2/images/%s" % image["sha"],
        json={"visibility": "public"},
        headers={"X-CSRF-Token": csrf},
    )
    assert len(plaza_items(anonymous)) == 1


def test_plaza_can_be_disabled(app, client):
    csrf = register_and_login(client)
    upload(client, csrf)

    with app.app_context():
        set_setting("plaza_enabled", False)
    assert app.test_client().get("/api/v2/plaza").status_code == 404

    with app.app_context():
        set_setting("plaza_enabled", True)
    assert app.test_client().get("/api/v2/plaza").status_code == 200
