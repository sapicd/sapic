# -*- coding: utf-8 -*-
import io

from sapic.libs.settings import set_setting
from sapic.models import Album, AlbumShare, Image, User
from sapic.models.base import now


def register_and_login(client):
    client.post(
        "/api/v2/auth/register",
        json={"username": "alice", "password": "secret123"},
    )
    response = client.post(
        "/api/v2/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    return response.get_json()["data"]["csrf"]


def test_album_flow_controls_visibility(app, client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}

    response = client.post(
        "/api/v2/albums",
        json={"name": "旅行", "visibility": "private"},
        headers=headers,
    )
    assert response.status_code == 201
    album_id = response.get_json()["data"]["album"]["id"]

    albums = client.get("/api/v2/albums").get_json()["data"]["items"]
    assert {album["name"] for album in albums} == {"默认相册", "旅行"}

    response = client.post(
        "/api/v2/uploads",
        data={
            "file": (io.BytesIO(b"album-bytes"), "trip.png"),
            "album_id": str(album_id),
        },
        content_type="multipart/form-data",
        headers=headers,
    )
    assert response.status_code == 201
    sha = response.get_json()["data"]["image"]["sha"]

    anonymous = app.test_client()
    assert anonymous.get("/raw/%s" % sha).status_code == 403

    response = client.patch(
        "/api/v2/albums/%d" % album_id,
        json={"visibility": "public"},
        headers=headers,
    )
    assert response.status_code == 200
    assert anonymous.get("/raw/%s" % sha).status_code == 200

    response = client.delete("/api/v2/albums/%d" % album_id, headers=headers)
    assert response.status_code == 409


def upload(client, csrf=None, filename="photo.png", content=b"album-bytes", album_id=None):
    data = {"file": (io.BytesIO(content), filename)}
    if album_id is not None:
        data["album_id"] = str(album_id)
    return client.post(
        "/api/v2/uploads",
        data=data,
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf} if csrf else {},
    )


def test_upload_without_album_uses_default_album(app, client):
    csrf = register_and_login(client)
    response = upload(client, csrf)
    assert response.status_code == 201, response.get_json()
    image = response.get_json()["data"]["image"]

    with app.app_context():
        row = Album.get_by_id(image["album_id"])
        assert row.name == "默认相册"
        assert row.is_default is True
        #: 兜底相册默认公开，上传即可外链。
        assert row.visibility == "public"
        assert Image.get(Image.sha == image["sha"]).visibility is None

    assert app.test_client().get(image["src"]).status_code == 200


def test_anonymous_upload_lands_in_system_album(app, client):
    with app.app_context():
        set_setting("allow_anonymous_upload", True)

    response = upload(client)
    assert response.status_code == 201, response.get_json()
    image = response.get_json()["data"]["image"]

    with app.app_context():
        row = Image.get(Image.sha == image["sha"])
        assert row.owner_id is None
        assert row.album.owner_id is None
        assert row.album.name == "公共相册"

    assert app.test_client().get(image["src"]).status_code == 200


def test_default_album_cannot_be_deleted(client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}
    albums = client.get("/api/v2/albums").get_json()["data"]["items"]

    default = next(album for album in albums if album["is_default"])
    response = client.delete("/api/v2/albums/%d" % default["id"], headers=headers)
    assert response.status_code == 409


def test_single_image_visibility_overrides_album(app, client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}
    image = upload(client, csrf).get_json()["data"]["image"]
    anonymous = app.test_client()

    assert anonymous.get(image["src"]).status_code == 200

    response = client.patch(
        "/api/v2/images/%s" % image["sha"],
        json={"visibility": "private"},
        headers=headers,
    )
    assert response.status_code == 200
    assert anonymous.get(image["src"]).status_code == 403

    #: 置回 NULL 即重新跟随相册。
    response = client.patch(
        "/api/v2/images/%s" % image["sha"],
        json={"visibility": None},
        headers=headers,
    )
    assert response.status_code == 200
    assert anonymous.get(image["src"]).status_code == 200


def _second_client(app, username):
    client = app.test_client()
    client.post(
        "/api/v2/auth/register",
        json={"username": username, "password": "secret123"},
    )
    csrf = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": "secret123"},
    ).get_json()["data"]["csrf"]
    return client, csrf


def test_album_shares_grant_and_revoke_access(app, client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}

    album = client.post(
        "/api/v2/albums",
        json={"name": "私房", "visibility": "private"},
        headers=headers,
    ).get_json()["data"]["album"]
    image = client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"share-bytes"), "trip.png"), "album_id": str(album["id"])},
        content_type="multipart/form-data",
        headers=headers,
    ).get_json()["data"]["image"]

    bobby, _ = _second_client(app, "bobby")
    assert bobby.get("/api/v2/albums").get_json()["data"]["items"][0]["role"] == "owner"
    assert image["sha"] not in [
        item["sha"] for item in bobby.get("/api/v2/images").get_json()["data"]["items"]
    ]

    response = client.post(
        "/api/v2/albums/%s/shares" % album["id"],
        json={"username": "bobby", "permission": "read"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["share"]["username"] == "bobby"
    #: 私有相册一旦有成员，可见性跟着变成「共享」。
    assert data["album"]["visibility"] == "shared"

    shared = [
        item
        for item in bobby.get("/api/v2/albums").get_json()["data"]["items"]
        if item["id"] == album["id"]
    ]
    assert shared and shared[0]["role"] == "shared"
    assert image["sha"] in [
        item["sha"] for item in bobby.get("/api/v2/images").get_json()["data"]["items"]
    ]

    members = client.get(
        "/api/v2/albums/%s/shares" % album["id"]
    ).get_json()["data"]["items"]
    assert [member["username"] for member in members] == ["bobby"]

    #: 已有成员可以改权限，不必先移除再加。
    response = client.patch(
        "/api/v2/albums/%s/shares/%s" % (album["id"], members[0]["user_id"]),
        json={"permission": "write"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["share"]["permission"] == "write"

    response = client.delete(
        "/api/v2/albums/%s/shares/%s" % (album["id"], members[0]["user_id"]),
        headers=headers,
    )
    assert response.status_code == 200
    assert image["sha"] not in [
        item["sha"] for item in bobby.get("/api/v2/images").get_json()["data"]["items"]
    ]


def test_write_member_can_upload_into_shared_album(app, client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}
    album = client.post(
        "/api/v2/albums",
        json={"name": "协作", "visibility": "private"},
        headers=headers,
    ).get_json()["data"]["album"]
    bobby, bobby_csrf = _second_client(app, "bobby")
    bobby_headers = {"X-CSRF-Token": bobby_csrf}
    base = "/api/v2/albums/%s/shares" % album["id"]

    client.post(
        base, json={"username": "bobby", "permission": "read"}, headers=headers
    )
    denied = bobby.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"read-bytes"), "a.png"), "album_id": str(album["id"])},
        content_type="multipart/form-data",
        headers=bobby_headers,
    )
    #: 只读成员看得到相册，但不能往里传。
    assert denied.status_code == 404

    member = client.get(base).get_json()["data"]["items"][0]
    assert client.patch(
        "%s/%s" % (base, member["user_id"]),
        json={"permission": "write"},
        headers=headers,
    ).status_code == 200

    allowed = bobby.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"write-bytes"), "b.png"), "album_id": str(album["id"])},
        content_type="multipart/form-data",
        headers=bobby_headers,
    )
    assert allowed.status_code == 201
    assert allowed.get_json()["data"]["image"]["album_id"] == album["id"]


def test_share_expiry_and_inactive_grantee(app, client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}
    album = client.post(
        "/api/v2/albums",
        json={"name": "临时", "visibility": "private"},
        headers=headers,
    ).get_json()["data"]["album"]
    bobby, _ = _second_client(app, "bobby")
    base = "/api/v2/albums/%s/shares" % album["id"]

    created = client.post(
        base,
        json={"username": "bobby", "permission": "read", "expires_in": 3600},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.get_json()["data"]["share"]["expires_at"]

    with app.app_context():
        #: 把授权推到过去，成员身份应当立即失效。
        AlbumShare.update(expires_at=now() - 1).execute()
    visible = [
        item["id"]
        for item in bobby.get("/api/v2/albums").get_json()["data"]["items"]
    ]
    assert album["id"] not in visible

    #: 未激活（待审核/已禁用）的账号不能成为共享成员。
    _second_client(app, "carol")
    with app.app_context():
        User.update(status=-1).where(User.username == "carol").execute()
    denied = client.post(
        base, json={"username": "carol"}, headers=headers
    )
    assert denied.status_code == 404


def test_album_share_validation(app, client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}
    album = client.post(
        "/api/v2/albums",
        json={"name": "旅行", "visibility": "public"},
        headers=headers,
    ).get_json()["data"]["album"]
    _second_client(app, "bobby")

    base = "/api/v2/albums/%s/shares" % album["id"]
    assert client.post(
        base, json={"username": "ghost"}, headers=headers
    ).status_code == 404
    assert client.post(
        base, json={"username": "alice"}, headers=headers
    ).status_code == 400
    assert client.post(
        base, json={"username": "bobby", "permission": "owner"}, headers=headers
    ).status_code == 400

    #: 非所有者看不到别人的相册，成员接口统一 404。
    outsider, outsider_csrf = _second_client(app, "carol")
    assert outsider.post(
        base,
        json={"username": "alice"},
        headers={"X-CSRF-Token": outsider_csrf},
    ).status_code == 404
