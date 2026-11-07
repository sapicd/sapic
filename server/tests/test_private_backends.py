# -*- coding: utf-8 -*-
"""Private (anonymous-read denied) storage backends.

A backend marked ``private`` never hands its URL to the browser: ``image_src``
falls back to ``/raw/<sha>``, and ``/raw`` asks the driver for a temporary read
address (``upimg_url``) which sapic relays itself.
"""

import io
import sys
from email.message import Message
from pathlib import Path

import pytest

from sapic.basis.errors import ApiError
from sapic.libs.settings import get_setting, set_setting
from sapic.models import Image, ImageBackend, StorageBackend, User

READABLE = '''
__version__ = "0.1.0"
__author__ = "tester"
__catalog__ = "upload"


def hook_manifest():
    return {"title": "Private bucket", "catalog": "upload"}


def upimg_save(filename, stream, upload_path="", backend=None, **kwargs):
    data = stream if isinstance(stream, (bytes, bytearray)) else stream.read()
    return {
        "code": 0,
        "path": "%s/%s" % (upload_path, filename),
        "size": len(data),
        "etag": "e1",
    }


def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None, **kwargs):
    return {"code": 0}


def upimg_url(save_result, filename="", backend=None, expires=300, **kwargs):
    key = (save_result or {}).get("path") or ""
    return {
        "code": 0,
        "url": "https://bucket.internal/%s?sign=x" % key,
        "headers": {"Authorization": "Bearer sign"},
    }
'''

WRITE_ONLY = '''
__version__ = "0.1.0"
__author__ = "tester"
__catalog__ = "upload"


def hook_manifest():
    return {"title": "Write only", "catalog": "upload"}


def upimg_save(filename, stream, upload_path="", backend=None, **kwargs):
    return {"code": 0, "path": filename, "size": 1}
'''


class FakeRemote:
    """Minimal stand-in for the ``urllib`` response used when relaying."""

    def __init__(self, payload=b"relayed-bytes"):
        self._buffer = io.BytesIO(payload)
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = "image/png"
        self.headers["Content-Length"] = str(len(payload))
        self.closed = False

    def read(self, size=-1):
        return self._buffer.read(size)

    def close(self):
        self.closed = True


def install(app, name, source):
    target = Path(app.config["HOOK_PKG_STORAGE_DIR"])
    target.mkdir(parents=True, exist_ok=True)
    (target / ("%s.py" % name)).write_text(source, encoding="utf-8")
    if str(target) not in sys.path:
        sys.path.append(str(target))
    with app.app_context():
        imported = list(get_setting("hooks_imported", []) or [])
        if name not in imported:
            imported.append(name)
        set_setting("hooks_imported", imported)
        states = dict(get_setting("hooks_state", {}) or {})
        states[name] = True
        set_setting("hooks_state", states)
        app.extensions["hooks"].reload()


def uninstall(app, name):
    sys.modules.pop(name, None)
    target = str(app.config["HOOK_PKG_STORAGE_DIR"])
    if target in sys.path:
        sys.path.remove(target)


@pytest.fixture()
def driver(app):
    install(app, "private_driver", READABLE)
    yield "private_driver"
    uninstall(app, "private_driver")


def login_admin(app, client, username="alice"):
    client.post(
        "/api/v2/auth/register",
        json={"username": username, "password": "secret123"},
    )
    response = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": "secret123"},
    )
    with app.app_context():
        user = User.get(User.username == username)
        user.is_admin = True
        user.save(only=[User.is_admin])
    return response.get_json()["data"]["csrf"]


def upload(client, csrf):
    response = client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"fake-image-bytes"), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["image"]


def add_backend(client, csrf, hook_name, visibility, priority=1, name="bucket"):
    return client.post(
        "/api/v2/backends",
        json={
            "name": name,
            "hook_name": hook_name,
            "priority": priority,
            "visibility": visibility,
        },
        headers={"X-CSRF-Token": csrf},
    )


def test_new_backends_are_public_by_default(app, client):
    csrf = login_admin(app, client)
    response = add_backend(client, csrf, "up2local", None, name="extra")
    assert response.status_code == 201, response.get_json()

    item = next(
        row
        for row in response.get_json()["data"]["items"]
        if row["name"] == "extra"
    )
    #: 默认沿用「公开直链」，私有桶要显式选择。
    assert item["visibility"] == "public"
    assert item["private_readable"] is True


def test_driver_without_a_read_contract_cannot_be_private(app, client):
    csrf = login_admin(app, client)
    install(app, "write_only", WRITE_ONLY)
    try:
        refused = add_backend(client, csrf, "write_only", "private")
        assert refused.status_code == 400
        assert "upimg_url" in refused.get_json()["message"]

        allowed = add_backend(client, csrf, "write_only", "public", name="wo")
        assert allowed.status_code == 201, allowed.get_json()
    finally:
        uninstall(app, "write_only")


def test_private_backend_relays_a_signed_read(app, client, driver, monkeypatch):
    csrf = login_admin(app, client)
    assert add_backend(client, csrf, driver, "private").status_code == 201

    image = upload(client, csrf)
    sha = image["sha"]
    #: 私有桶的直链匿名访问会 403，公开图也只能走 sapic。
    assert image["src"] == "/raw/%s" % sha

    seen = {}
    remote = FakeRemote()

    def fake_open(target, headers=None, allow_private=False):
        seen["url"] = target
        seen["headers"] = headers or {}
        seen["allow_private"] = allow_private
        return remote

    monkeypatch.setattr("sapic.views.public.open_remote", fake_open)

    response = client.get("/raw/%s" % sha)
    assert response.status_code == 200
    assert response.data == b"relayed-bytes"
    assert seen["url"].startswith("https://bucket.internal/")
    assert seen["headers"]["Authorization"] == "Bearer sign"
    #: 签名地址可能指向内网对象存储，代理时不再做公网校验。
    assert seen["allow_private"] is True
    assert "private" in response.headers["Cache-Control"]
    assert remote.closed is True


def test_failed_private_replica_falls_back(app, client, driver, monkeypatch):
    csrf = login_admin(app, client)
    sha = upload(client, csrf)["sha"]
    with app.app_context():
        image = Image.get(Image.sha == sha)
        private = StorageBackend.create(
            name="private-bucket",
            hook_name=driver,
            config={},
            scope="global",
            visibility="private",
            priority=1,
            enabled=True,
        )
        public = StorageBackend.create(
            name="public-bucket",
            hook_name="up2github",
            config={},
            scope="global",
            visibility="public",
            priority=2,
            enabled=True,
        )
        ImageBackend.delete().where(ImageBackend.image == image).execute()
        ImageBackend.create(
            image=image, backend=private, object_key="a.png", size=5, state="ok"
        )
        ImageBackend.create(
            image=image,
            backend=public,
            object_key="a.png",
            url="https://cdn.example.com/a.png",
            size=5,
            state="ok",
        )

    detail = client.get("/api/v2/images/%s" % sha).get_json()["data"]
    #: 最高优先级副本在私有桶里，不能借用下一个副本的直链。
    assert detail["image"]["src"] == "/raw/%s" % sha

    def failing_open(target, headers=None, allow_private=False):
        raise ApiError("bucket is down")

    monkeypatch.setattr("sapic.views.public.open_remote", failing_open)

    response = client.get("/raw/%s" % sha)
    #: 第一个副本失败后换下一个，而不是直接 404。
    assert response.status_code == 302
    assert response.headers["Location"] == "https://cdn.example.com/a.png"
