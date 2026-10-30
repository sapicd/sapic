# -*- coding: utf-8 -*-
import io


def register_and_login(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "secret123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    return response.get_json()["data"]["csrf"]


def test_album_flow_controls_visibility(app, client):
    csrf = register_and_login(client)
    headers = {"X-CSRF-Token": csrf}

    response = client.post(
        "/api/v1/albums",
        json={"name": "旅行", "visibility": "private"},
        headers=headers,
    )
    assert response.status_code == 201
    album_id = response.get_json()["data"]["album"]["id"]

    albums = client.get("/api/v1/albums").get_json()["data"]["items"]
    assert {album["name"] for album in albums} == {"默认相册", "旅行"}

    response = client.post(
        "/api/v1/uploads",
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
    assert anonymous.get("/i/%s" % sha).status_code == 403

    response = client.patch(
        "/api/v1/albums/%d" % album_id,
        json={"visibility": "public"},
        headers=headers,
    )
    assert response.status_code == 200
    assert anonymous.get("/i/%s" % sha).status_code == 200

    response = client.delete("/api/v1/albums/%d" % album_id, headers=headers)
    assert response.status_code == 409
