# -*- coding: utf-8 -*-
"""v1 compatibility endpoint: ``POST /api/upload``."""

import base64
import io

from sapic.models import Album

USER = {
    "username": "dave",
    "password": "secret123",
    "email": "dave@example.com",
}


def register(client):
    client.post("/api/v2/auth/register", json=USER)
    response = client.post(
        "/api/v2/auth/login",
        json={"username": USER["username"], "password": USER["password"]},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["csrf"]


def make_token(client, csrf, scopes=("upload",)):
    response = client.post(
        "/api/v2/auth/tokens",
        json={"name": "legacy", "scopes": list(scopes)},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["token"]


def logout(client, csrf):
    client.post("/api/v2/auth/logout", headers={"X-CSRF-Token": csrf})


def legacy_upload(
    client, data=None, content=b"fake-image-bytes", filename="photo.png", csrf=None
):
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    return client.post(
        "/api/upload",
        data={"picbed": (io.BytesIO(content), filename), **(data or {})},
        content_type="multipart/form-data",
        headers=headers,
    )


def test_anonymous_upload_is_refused_by_default(client):
    response = legacy_upload(client)
    assert response.status_code == 403
    body = response.get_json()
    assert body["code"] == 1
    assert "anonymous" in body["msg"]


def test_pat_in_form_field_uploads(app, client):
    csrf = register(client)
    token = make_token(client, csrf)
    logout(client, csrf)

    response = legacy_upload(client, {"token": token})
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["code"] == 0
    assert body["sha"].startswith("sha1.")
    assert body["src"]
    assert body["is_video"] is False


def test_pat_scope_is_enforced(app, client):
    csrf = register(client)
    token = make_token(client, csrf, scopes=("read",))
    logout(client, csrf)

    response = legacy_upload(client, {"token": token})
    assert response.status_code == 403
    assert response.get_json()["code"] == 1


def test_session_upload_needs_csrf(client):
    register(client)
    response = legacy_upload(client)
    assert response.status_code == 403
    assert "access token" in response.get_json()["msg"]


def test_session_upload_with_csrf(client):
    csrf = register(client)
    response = client.post(
        "/api/upload",
        data={"picbed": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["code"] == 0


def test_base64_payload(app, client):
    csrf = register(client)
    payload = base64.b64encode(b"fake-image-bytes").decode()
    response = client.post(
        "/api/upload",
        data={"picbed": "data:image/png;base64,%s" % payload},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["code"] == 0
    assert body["filename"].endswith(".png")


def test_album_name_is_created_on_demand(app, client):
    csrf = register(client)
    response = legacy_upload(client, {"album": "旅行", "title": "海边"}, csrf=csrf)
    assert response.status_code == 200, response.get_json()

    with app.app_context():
        album = Album.get_or_none(Album.name == "旅行")
        assert album is not None
        assert album.is_default is False


def test_format_parameter_places_the_url(client):
    csrf = register(client)
    response = client.post(
        "/api/upload",
        data={
            "picbed": (io.BytesIO(b"fake-image-bytes"), "photo.png"),
            "format": "data.src",
        },
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    body = response.get_json()
    assert body["code"] == 0
    assert body["data"]["src"] == body["src"]
