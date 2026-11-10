# -*- coding: utf-8 -*-
import io
from pathlib import Path

from sapic.libs.images import purge_expired
from sapic.libs.settings import set_setting
from sapic.models import Image, ImageBackend
from sapic.models.base import now

DAY = 86400


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


def upload(client, csrf, filename="photo.png", expire=None):
    data = {"file": (io.BytesIO(b"fake-image-bytes"), filename)}
    if expire is not None:
        data["expire"] = str(expire)
    return client.post(
        "/api/v2/upload",
        data=data,
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


def expire_now(app, sha):
    """Move an image's expiry into the past without touching its bytes."""
    with app.app_context():
        Image.update(expire_at=now() - 1).where(Image.sha == sha).execute()


def test_upload_sets_expire_at(app, client):
    csrf = register_and_login(client)
    image = upload(client, csrf, expire=3600).get_json()["data"]["image"]
    assert image["expire_at"] is not None
    assert image["expire_at"] - image["created_at"] in (3599, 3600, 3601)


def test_upload_without_expire_is_permanent(app, client):
    csrf = register_and_login(client)
    image = upload(client, csrf).get_json()["data"]["image"]
    assert image["expire_at"] is None


def test_expired_image_disappears_everywhere(app, client):
    csrf = register_and_login(client)
    image = upload(client, csrf, expire=3600).get_json()["data"]["image"]
    sha = image["sha"]

    expire_now(app, sha)

    #: 过期即消失：直链 404，详情 404，列表里也看不到。
    assert client.get("/raw/%s" % sha).status_code == 404
    assert client.get("/api/v2/images/%s" % sha).status_code == 404
    assert client.get("/api/v2/images").get_json()["data"]["items"] == []


def test_purge_expired_removes_row_and_file(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf, expire=3600).get_json()["data"]["image"]["sha"]

    with app.app_context():
        replica = ImageBackend.get(ImageBackend.image == Image.get(Image.sha == sha))
        stored = Path(app.config["STORAGE_DIR"]) / replica.object_key
        assert stored.is_file()

        expire_now(app, sha)
        assert purge_expired() == 1
        assert Image.get_or_none(Image.sha == sha) is None
        assert ImageBackend.select().count() == 0
        assert not stored.exists()


def test_request_sweeps_expired_images(app, client, monkeypatch):
    """没有 cron 也要落地：请求期节流清理会把过期图片真删掉。"""
    from sapic.libs import images as images_lib

    csrf = register_and_login(client)
    sha = upload(client, csrf, expire=3600).get_json()["data"]["image"]["sha"]
    expire_now(app, sha)
    #: 清掉进程级节流，让这次请求一定触发清理。
    monkeypatch.setattr(images_lib, "_last_sweep", 0.0)

    assert client.get("/api/v2/health").status_code == 200
    with app.app_context():
        assert Image.get_or_none(Image.sha == sha) is None


def test_purge_expired_keeps_live_images(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf, expire=3600).get_json()["data"]["image"]["sha"]
    with app.app_context():
        assert purge_expired() == 0
        assert Image.get_or_none(Image.sha == sha) is not None


def test_expire_beyond_site_limit_is_rejected(app, client):
    csrf = register_and_login(client)
    with app.app_context():
        set_setting("image_expire_max_days", 1)

    response = upload(client, csrf, expire=2 * DAY)
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    #: 上限生效后「永久」不可用：未指定有效期时按上限落库。
    image = upload(client, csrf).get_json()["data"]["image"]
    assert image["expire_at"] - image["created_at"] in (DAY - 1, DAY, DAY + 1)


def test_patch_updates_and_clears_expire_at(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]

    target = now() + 7200
    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"expire_at": target},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["image"]["expire_at"] == target

    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"expire_at": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.get_json()["data"]["image"]["expire_at"] is None

    #: 过去的时间等于「立即删除」，让调用方走 DELETE。
    response = client.patch(
        "/api/v2/images/%s" % sha,
        json={"expire_at": now() - 10},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
