# -*- coding: utf-8 -*-
import io

from sapic.models import StorageBackend


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


def upload(client, csrf, filename="photo.png"):
    return client.post(
        "/api/v1/uploads",
        data={"file": (io.BytesIO(b"bytes"), filename)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


def make_backend(name, root, priority):
    return StorageBackend.create(
        name=name,
        hook_name="up2local",
        config={"root": str(root)},
        scope="global",
        visibility="private",
        priority=priority,
        enabled=True,
    )


def test_upload_uses_highest_priority_backend(app, client, tmp_path):
    csrf = register_and_login(client)
    with app.app_context():
        make_backend("high", tmp_path / "high", 1)
        make_backend("low", tmp_path / "low", 50)

    response = upload(client, csrf)
    assert response.status_code == 201

    assert list((tmp_path / "high").rglob("photo.png"))
    assert not list((tmp_path / "low").rglob("photo.png"))


def test_disabled_backend_is_skipped(app, client, tmp_path):
    csrf = register_and_login(client)
    with app.app_context():
        high = make_backend("high", tmp_path / "high", 1)
        make_backend("low", tmp_path / "low", 50)

    assert upload(client, csrf, "first.png").status_code == 201
    with app.app_context():
        high.enabled = False
        high.save(only=[StorageBackend.enabled])

    assert upload(client, csrf, "second.png").status_code == 201
    assert list((tmp_path / "high").rglob("first.png"))
    assert list((tmp_path / "low").rglob("second.png"))

    with app.app_context():
        assert StorageBackend.get(StorageBackend.name == "low").priority == 50


def test_hook_config_is_the_default_for_the_driver(app, client, tmp_path):
    from sapic.libs.settings import set_setting

    csrf = register_and_login(client)
    with app.app_context():
        set_setting("hooks_config", {"up2local": {"root": str(tmp_path / "hooked")}})

    assert upload(client, csrf).status_code == 201
    assert list((tmp_path / "hooked").rglob("photo.png"))


def test_backend_config_wins_over_the_hook_default(app, client, tmp_path):
    from sapic.libs.settings import set_setting

    csrf = register_and_login(client)
    with app.app_context():
        set_setting("hooks_config", {"up2local": {"root": str(tmp_path / "hooked")}})
        make_backend("explicit", tmp_path / "explicit", 1)

    assert upload(client, csrf).status_code == 201
    assert list((tmp_path / "explicit").rglob("photo.png"))
    assert not list((tmp_path / "hooked").rglob("photo.png"))
