# -*- coding: utf-8 -*-
import io
from email.message import Message

from sapic.models import Image, ImageBackend, StorageBackend


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


def upload(client, csrf, filename="photo.png"):
    return client.post(
        "/api/v2/uploads",
        data={"file": (io.BytesIO(b"bytes"), filename)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


def use_remote_replica(app, sha, url, private=False):
    """Swap the local replica for a remote one, optionally making it private."""
    with app.app_context():
        image = Image.get(Image.sha == sha)
        if private:
            image.visibility = "private"
            image.save(only=[Image.visibility])
        backend = StorageBackend.create(
            name="remote-%d" % image.id,
            hook_name="up2github",
            config={},
            scope="global",
            visibility="public",
            priority=1,
            enabled=True,
        )
        ImageBackend.delete().where(ImageBackend.image == image).execute()
        ImageBackend.create(
            image=image,
            backend=backend,
            object_key="photo.png",
            url=url,
            size=5,
            is_primary=True,
            state="ok",
        )


class FakeRemote:
    """Minimal stand-in for the ``urllib`` response used when relaying."""

    def __init__(self, payload=b"remote-bytes"):
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


def test_public_image_links_to_the_backend_domain(app, client, tmp_path):
    csrf = register_and_login(client)
    with app.app_context():
        StorageBackend.create(
            name="cdn",
            hook_name="up2local",
            config={
                "root": str(tmp_path / "cdn"),
                "domain": "https://cdn.example.com",
            },
            scope="global",
            visibility="public",
            priority=1,
            enabled=True,
        )

    image = upload(client, csrf).get_json()["data"]["image"]
    assert image["src"].startswith("https://cdn.example.com/")
    #: 存储 key 带唯一后缀，展示用的 filename 仍是原名。
    assert "/photo-" in image["src"]
    assert image["src"].endswith(".png")
    assert image["filename"] == "photo.png"

    detail = client.get("/api/v2/images/%s" % image["sha"]).get_json()["data"]
    assert detail["image"]["src"] == image["src"]

    listing = client.get("/api/v2/images").get_json()["data"]["items"]
    assert listing[0]["src"] == image["src"]


def test_public_image_with_remote_replica_redirects(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    url = "https://raw.githubusercontent.com/u/r/main/photo.png"
    use_remote_replica(app, sha, url)

    detail = client.get("/api/v2/images/%s" % sha).get_json()["data"]
    assert detail["image"]["src"] == url

    response = client.get("/raw/%s" % sha)
    assert response.status_code == 302
    assert response.headers["Location"] == url


def test_highest_priority_replica_decides_the_link(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        image = Image.get(Image.sha == sha)
        secondary = StorageBackend.create(
            name="remote-secondary",
            hook_name="up2github",
            config={},
            scope="global",
            visibility="public",
            priority=200,
            enabled=True,
        )
        ImageBackend.create(
            image=image,
            backend=secondary,
            object_key="photo.png",
            url="https://raw.githubusercontent.com/u/r/main/photo.png",
            size=5,
            is_primary=False,
            state="ok",
        )

    detail = client.get("/api/v2/images/%s" % sha).get_json()["data"]
    #: 主副本是本地（无直链），不能跳到次优先级副本的直链。
    assert detail["image"]["src"] == "/raw/%s" % sha
    assert client.get("/raw/%s" % sha).status_code == 200


def test_private_image_stays_behind_the_sapic_endpoint(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        image = Image.get(Image.sha == sha)
        image.visibility = "private"
        image.save(only=[Image.visibility])

    detail = client.get("/api/v2/images/%s" % sha).get_json()["data"]
    assert detail["image"]["src"] == "/raw/%s" % sha

    assert app.test_client().get("/raw/%s" % sha).status_code == 403

    response = client.get("/raw/%s" % sha)
    assert response.status_code == 200
    cache = response.headers["Cache-Control"]
    assert "private" in cache
    assert "immutable" in cache


def test_private_remote_replica_is_relayed_not_redirected(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    url = "https://raw.githubusercontent.com/u/r/main/photo.png"
    use_remote_replica(app, sha, url, private=True)

    remote = FakeRemote()
    seen = {}

    def fake_open(target, headers=None, allow_private=False):
        seen["url"] = target
        seen["headers"] = headers or {}
        seen["allow_private"] = allow_private
        return remote

    monkeypatch.setattr("sapic.views.public.open_remote", fake_open)

    response = client.get("/raw/%s" % sha, headers={"Range": "bytes=0-4"})
    assert response.status_code == 200
    assert response.data == b"remote-bytes"
    assert seen["url"] == url
    assert seen["headers"].get("Range") == "bytes=0-4"
    #: 后端地址由服务端产生，允许指向内网（自建 MinIO），不是用户输入。
    assert seen["allow_private"] is True
    assert response.headers["Accept-Ranges"] == "bytes"
    assert "private" in response.headers["Cache-Control"]
    assert remote.closed is True


def test_local_replica_is_served_with_public_cache(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    response = client.get("/raw/%s" % sha)
    assert response.status_code == 200
    assert response.data == b"bytes"
    cache = response.headers["Cache-Control"]
    assert "public" in cache
    assert "immutable" in cache
