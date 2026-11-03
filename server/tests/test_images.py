# -*- coding: utf-8 -*-
import io
import re

from sapic.libs.settings import set_setting
from sapic.models import Image, ImageBackend


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


def upload(client, csrf=None, filename="photo.png", content=b"fake-image-bytes"):
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    return client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
        headers=headers,
    )


def test_upload_and_read(app, client, tmp_path):
    csrf = register_and_login(client)
    response = upload(client, csrf)
    assert response.status_code == 201, response.get_json()

    image = response.get_json()["data"]["image"]
    assert image["sha"].startswith("sha1.")
    assert image["src"].endswith("/i/%s" % image["sha"])

    with app.app_context():
        row = Image.get(Image.sha == image["sha"])
        assert row.size == len(b"fake-image-bytes")
        replica = ImageBackend.get(ImageBackend.image == row)
        assert replica.state == "ok"
        assert replica.is_primary is True

    response = client.get(image["src"])
    assert response.status_code == 200
    assert response.data == b"fake-image-bytes"


def test_image_listing_and_update(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    listing = client.get("/api/v2/images").get_json()["data"]
    assert listing["items"][0]["sha"] == sha
    assert listing["has_more"] is False

    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"title": "new title"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["image"]["title"] == "new title"


def test_image_visibility_rejects_shared(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    #: 共享是按相册授权的，单图覆盖只接受 public / private。
    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"visibility": "shared"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["image"]["visibility"] == "private"


def test_delete_image(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    response = client.delete(
        "/api/v2/images/%s" % sha, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert client.get("/i/%s" % sha).status_code == 404

    with app.app_context():
        assert Image.get(Image.sha == sha).status == "deleted"
        assert ImageBackend.select().where(
            ImageBackend.image == Image.get(Image.sha == sha)
        ).count() == 0


def test_upload_rejects_unknown_suffix(client):
    csrf = register_and_login(client)
    response = upload(client, csrf, filename="shell.php")
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"


def test_same_name_uploads_do_not_overwrite(app, client):
    csrf = register_and_login(client)

    first = upload(client, csrf, content=b"first").get_json()["data"]["image"]
    second = upload(client, csrf, content=b"second").get_json()["data"]["image"]

    assert first["sha"] != second["sha"]
    assert client.get("/i/%s" % first["sha"]).data == b"first"
    assert client.get("/i/%s" % second["sha"]).data == b"second"

    with app.app_context():
        keys = [row.object_key for row in ImageBackend.select()]
        assert len(keys) == 2
        assert len(set(keys)) == 2
        #: 展示用的文件名保持原样，只有存储 key 带唯一后缀。
        assert Image.get(Image.sha == first["sha"]).filename == "photo.png"


def test_upload_generates_a_name_when_it_cannot_be_read(app, client):
    csrf = register_and_login(client)
    #: 纯中文名会被 secure_filename 清空，按时间戳+随机串兜底，后缀必须保住。
    response = upload(client, csrf, filename="截图.png")
    assert response.status_code == 201, response.get_json()

    image = response.get_json()["data"]["image"]
    assert re.match(r"^\d{14}[0-9a-f]{6}\.png$", image["filename"])

    with app.app_context():
        replica = ImageBackend.get(
            ImageBackend.image == Image.get(Image.sha == image["sha"])
        )
        key = replica.object_key.rsplit("/", 1)[-1]
        assert key.startswith(image["filename"].rsplit(".", 1)[0])


def test_upload_from_url(app, client, monkeypatch):
    csrf = register_and_login(client)
    monkeypatch.setattr(
        "sapic.views.uploads.download_image",
        lambda url, max_bytes: (b"remote-bytes", "remote.png", "image/png"),
    )

    response = client.post(
        "/api/v2/uploads",
        data={"url": "https://example.com/remote.png"},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()

    image = response.get_json()["data"]["image"]
    assert image["filename"] == "remote.png"
    assert client.get(image["src"]).data == b"remote-bytes"


def test_upload_from_url_rejects_unsupported_url(client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}

    response = client.post(
        "/api/v2/uploads",
        data={"url": "file:///etc/passwd"},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    #: 内网/环回地址在建立连接前就被拒绝，避免 SSRF。
    response = client.post(
        "/api/v2/uploads",
        data={"url": "http://127.0.0.1/photo.png"},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert response.status_code == 403


def test_anonymous_upload_disabled_by_default(client):
    response = upload(client)
    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_anonymous_upload_when_enabled(app, client):
    with app.app_context():
        set_setting("allow_anonymous_upload", True)

    response = upload(client)
    assert response.status_code == 201, response.get_json()
    image = response.get_json()["data"]["image"]

    with app.app_context():
        row = Image.get(Image.sha == image["sha"])
        assert row.owner_id is None
    assert client.get(image["src"]).status_code == 200


def test_image_listing_filters_by_album(client):
    csrf = register_and_login(client)

    album = client.post(
        "/api/v2/albums",
        json={"name": "旅行", "visibility": "public"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["album"]

    inside = upload(client, csrf).get_json()["data"]["image"]
    outside = upload(client, csrf, "other.png").get_json()["data"]["image"]
    client.patch(
        "/api/v2/images/%s" % inside["sha"],
        json={"album_id": album["id"]},
        headers={"X-CSRF-Token": csrf},
    )

    listing = client.get(
        "/api/v2/images", query_string={"album_id": album["id"]}
    ).get_json()["data"]
    shas = [item["sha"] for item in listing["items"]]
    assert shas == [inside["sha"]]
    assert outside["sha"] not in shas


def test_image_payload_carries_its_album(client):
    csrf = register_and_login(client)
    uploaded = upload(client, csrf).get_json()["data"]["image"]

    detail = client.get("/api/v2/images/%s" % uploaded["sha"]).get_json()["data"]
    assert detail["image"]["album"]["id"] == uploaded["album_id"]
    assert detail["image"]["album"]["name"]

    listing = client.get("/api/v2/images").get_json()["data"]["items"]
    item = next(entry for entry in listing if entry["sha"] == uploaded["sha"])
    assert item["album"]["id"] == uploaded["album_id"]


def test_image_tags_are_normalized_and_filterable(client):
    csrf = register_and_login(client)
    tagged = upload(client, csrf).get_json()["data"]["image"]
    other = upload(client, csrf, "other.png").get_json()["data"]["image"]

    response = client.patch(
        "/api/v2/images/%s" % tagged["sha"],
        json={"tags": ["旅行", " 旅行 ", "", "海边"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["image"]["tags"] == ["旅行", "海边"]

    detail = client.get("/api/v2/images/%s" % tagged["sha"]).get_json()["data"]
    assert detail["image"]["tags"] == ["旅行", "海边"]

    listing = client.get(
        "/api/v2/images", query_string={"tag": "旅行"}
    ).get_json()["data"]
    shas = [item["sha"] for item in listing["items"]]
    assert shas == [tagged["sha"]]
    assert other["sha"] not in shas


def test_image_tags_reject_oversized_input(client):
    csrf = register_and_login(client)
    uploaded = upload(client, csrf).get_json()["data"]["image"]

    too_many = ["t%d" % index for index in range(11)]
    response = client.patch(
        "/api/v2/images/%s" % uploaded["sha"],
        json={"tags": too_many},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    response = client.patch(
        "/api/v2/images/%s" % uploaded["sha"],
        json={"tags": ["x" * 33]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
