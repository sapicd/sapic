# -*- coding: utf-8 -*-
import io


def setup_user_and_token(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "secret123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    csrf = response.get_json()["data"]["csrf"]
    token = client.post(
        "/api/v1/auth/tokens",
        json={"name": "picgo"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["token"]
    return csrf, token


def test_legacy_upload_and_sha(client):
    _, token = setup_user_and_token(client)

    response = client.post(
        "/api/upload",
        data={
            "token": token,
            "album": "legacy-album",
            "picbed": (io.BytesIO(b"legacy-bytes"), "legacy.jpg"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == 0
    assert body["sha"].startswith("sha1.")
    assert body["src"].endswith("/i/%s" % body["sha"])

    detail = client.get("/api/sha/%s?token=%s" % (body["sha"], token))
    assert detail.status_code == 200
    assert detail.get_json()["code"] == 0
    assert detail.get_json()["data"]["sha"] == body["sha"]

    removed = client.delete("/api/sha/%s?token=%s" % (body["sha"], token))
    assert removed.get_json()["code"] == 0
    assert client.get("/api/sha/%s?token=%s" % (body["sha"], token)).get_json()[
        "code"
    ] == 3


def test_legacy_upload_requires_token(client):
    response = client.post("/api/upload", data={})
    assert response.status_code == 200
    assert response.get_json()["code"] == 1


def test_legacy_format_option(client):
    _, token = setup_user_and_token(client)
    response = client.post(
        "/api/upload",
        data={
            "token": token,
            "format": "data.src",
            "picbed": (io.BytesIO(b"bytes"), "a.png"),
        },
        content_type="multipart/form-data",
    )
    body = response.get_json()
    assert body["code"] == 0
    assert body["data"]["src"] == body["src"]
