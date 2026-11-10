# -*- coding: utf-8 -*-
"""External link import and batch image operations."""

import io

from sapic.models import Image, ImageBackend

LINK = "https://cdn.example.com/pics/photo.png"


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


def upload(client, csrf, name="photo.png"):
    response = client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), name)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    return response.get_json()["data"]["image"]


def import_links(client, csrf, items, album_id=None):
    payload = {"items": items}
    if album_id:
        payload["album_id"] = album_id
    return client.post(
        "/api/v2/images/import",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )


def test_import_link_skips_the_download(app, client):
    csrf = register_and_login(client)

    response = import_links(client, csrf, [LINK])

    assert response.status_code == 200, response.get_json()
    body = response.get_json()["data"]
    assert body["failed"] == []
    image = body["imported"][0]
    assert image["external"] is True
    assert image["filename"] == "photo.png"
    #: 默认相册是公开的，公开图直接指向源站。
    assert image["src"] == LINK
    with app.app_context():
        assert ImageBackend.select().count() == 0

    redirect_to = client.get("/raw/%s" % image["sha"])
    assert redirect_to.status_code == 302
    assert redirect_to.headers["Location"] == LINK


def test_import_reports_bad_and_duplicate_links(app, client):
    csrf = register_and_login(client)

    body = import_links(
        client,
        csrf,
        ["not-a-url", LINK, {"url": LINK, "title": "again"}],
    ).get_json()["data"]

    assert len(body["imported"]) == 1
    assert [item["message"] for item in body["failed"]] == [
        "url must be an absolute http(s) link",
        "link already imported",
    ]
    with app.app_context():
        assert Image.select().count() == 1


def test_import_into_private_album_stays_behind_raw(client):
    csrf = register_and_login(client)
    album = client.post(
        "/api/v2/albums",
        json={"name": "secret", "visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["album"]

    body = import_links(client, csrf, [LINK], album_id=album["id"]).get_json()["data"]

    image = body["imported"][0]
    assert image["src"].endswith("/raw/%s" % image["sha"])


def test_batch_delete_removes_images_and_replicas(app, client):
    csrf = register_and_login(client)
    first = upload(client, csrf, "a.png")
    second = upload(client, csrf, "b.png")

    response = client.post(
        "/api/v2/images/batch/delete",
        json={"shas": [first["sha"], second["sha"]]},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {"deleted": 2}
    with app.app_context():
        assert ImageBackend.select().count() == 0
        assert Image.select().where(Image.status == "enabled").count() == 0


def test_batch_update_moves_album_and_visibility(app, client):
    csrf = register_and_login(client)
    first = upload(client, csrf, "a.png")
    second = upload(client, csrf, "b.png")
    album = client.post(
        "/api/v2/albums",
        json={"name": "moved", "visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["album"]

    response = client.patch(
        "/api/v2/images/batch",
        json={
            "shas": [first["sha"], second["sha"]],
            "album_id": album["id"],
            "visibility": "private",
            "tags": ["bulk"],
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {"updated": 2}
    with app.app_context():
        rows = Image.select().where(Image.status == "enabled")
        assert {row.album_id for row in rows} == {album["id"]}
        assert {row.visibility for row in rows} == {"private"}
        assert {tuple(row.tags) for row in rows} == {("bulk",)}


def test_batch_rejects_other_peoples_images(app, client):
    csrf = register_and_login(client)
    mine = upload(client, csrf, "a.png")

    other = app.test_client()
    other_csrf = register_and_login(other, "bobby")
    theirs = upload(other, other_csrf, "b.png")

    forbidden = client.post(
        "/api/v2/images/batch/delete",
        json={"shas": [theirs["sha"]]},
        headers={"X-CSRF-Token": csrf},
    )
    assert forbidden.status_code == 403

    mixed = client.patch(
        "/api/v2/images/batch",
        json={"shas": [mine["sha"], theirs["sha"]], "visibility": "private"},
        headers={"X-CSRF-Token": csrf},
    )
    assert mixed.status_code == 403


def test_batch_validates_the_request(client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}

    assert (
        client.post("/api/v2/images/batch/delete", json={"shas": []}, headers=headers)
        .status_code
        == 400
    )
    assert (
        client.post(
            "/api/v2/images/batch/delete",
            json={"shas": ["sha1.%d" % index for index in range(101)]},
            headers=headers,
        ).status_code
        == 400
    )
    assert (
        client.patch(
            "/api/v2/images/batch",
            json={"shas": ["sha1.1.abc"], "visibility": "shared"},
            headers=headers,
        ).status_code
        == 400
    )


def test_batch_requires_login(client):
    response = client.post("/api/v2/images/batch/delete", json={"shas": ["sha1.1.1"]})
    assert response.status_code == 401
