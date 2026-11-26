# -*- coding: utf-8 -*-
"""Moderation scan: verdict persistence, hiding, and the admin queue."""

import io
from types import SimpleNamespace

from peewee import JOIN

from sapic.libs.images import public_condition
from sapic.libs.review import review_pending
from sapic.libs.settings import set_setting
from sapic.libs.storage import replicas_for
from sapic.models import Album
from sapic.models.album import VISIBILITY_PRIVATE
from sapic.models.image import REVIEW_BLOCK, REVIEW_PASS, Image
from sapic.models.storage import ImageBackend
from sapic.models.user import User


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


def promote_admin(app, username="alice"):
    with app.app_context():
        user = User.get(User.username == username)
        user.is_admin = True
        user.save(only=[User.is_admin])


def upload(client, csrf, filename="photo.png"):
    return client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), filename)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


class FakeManager:
    """Stands in for HookManager; only the moderator contract is exercised."""

    def __init__(self, code=0, verdict="pass", message=""):
        self.calls = []
        self.code = code
        self.verdict = verdict
        self.message = message
        module = SimpleNamespace(
            __catalog__="moderator",
            review_image=lambda **kwargs: {},
        )
        self.hooks = {"fake_moderator": SimpleNamespace(enabled=True, module=module)}

    def call(self, funcname, include=None, with_config=False, **kwargs):
        self.calls.append(kwargs.get("image"))
        return [
            {
                "code": self.code,
                "verdict": self.verdict,
                "message": self.message,
                "sender": "fake_moderator",
            }
        ]


def use_manager(monkeypatch, **kwargs) -> FakeManager:
    manager = FakeManager(**kwargs)
    monkeypatch.setattr("sapic.libs.review.get_hook_manager", lambda: manager)
    return manager


def test_scan_blocks_and_hides_from_others(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    use_manager(monkeypatch, verdict="block", message="nsfw")

    with app.app_context():
        counts = review_pending()
    assert counts == {
        "scanned": 1,
        "passed": 0,
        "blocked": 1,
        "purged": 0,
        "failed": 0,
        "samples": [],
    }

    with app.app_context():
        image = Image.get(Image.sha == sha)
        assert image.review_state == REVIEW_BLOCK
        assert image.review_note == "nsfw"

    #: 本人仍能看到（要先能看才知道自己被拦了），匿名访客被挡住。
    assert client.get("/raw/%s" % sha).status_code == 200
    anonymous = app.test_client()
    assert anonymous.get("/raw/%s" % sha).status_code == 403


def test_scan_does_not_repeat_a_judged_image(app, client, monkeypatch):
    csrf = register_and_login(client)
    upload(client, csrf)
    manager = use_manager(monkeypatch, verdict="pass")

    with app.app_context():
        review_pending()
        review_pending()

    #: pass 之后不再入队，省掉一次外部调用（也就省掉一次计费）。
    assert len(manager.calls) == 1
    with app.app_context():
        assert Image.get(Image.review_state == REVIEW_PASS) is not None


def test_failed_verdict_is_retried_after_backoff(app, client, monkeypatch):
    from sapic.libs import review as review_mod

    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    manager = use_manager(monkeypatch, code=1, verdict="", message="timeout")

    with app.app_context():
        counts = review_pending()
    assert counts["failed"] == 1
    assert counts["samples"] == [{"sha": sha, "note": "timeout"}]
    with app.app_context():
        #: 不可判定时退回未审，而不是猜一个 pass 放行。
        image = Image.get(Image.sha == sha)
        assert image.review_state is None
        assert image.reviewed_at is not None
        assert image.review_note == "timeout"

    #: 退避期内立即重扫不会重复调用钩子（避免坏钩子把队列饿死）。
    with app.app_context():
        review_pending()
    assert len(manager.calls) == 1

    #: 退避到期后恢复重试。
    with app.app_context():
        image = Image.get(Image.sha == sha)
        image.reviewed_at -= review_mod.RETRY_DELAY + 1
        image.save(only=[Image.reviewed_at])
        review_pending()
    assert len(manager.calls) == 2


def test_failed_rows_do_not_starve_the_rest_of_the_queue(
    app, client, monkeypatch
):
    from sapic.libs import review as review_mod

    csrf = register_and_login(client)
    shas = [
        upload(client, csrf, filename="f%d.png" % i).get_json()["data"]["image"]["sha"]
        for i in range(review_mod.REVIEW_BATCH + 1)
    ]
    manager = use_manager(monkeypatch, code=1, message="broken")

    with app.app_context():
        first = review_pending()
        assert first["scanned"] == review_mod.REVIEW_BATCH
        assert first["failed"] == review_mod.REVIEW_BATCH

        #: 退避期内再扫：同一批失败图被跳过，最后一张新图终于轮到。
        manager.verdict = "pass"
        manager.code = 0
        second = review_pending()

    assert second["scanned"] == 1
    assert second["passed"] == 1
    assert manager.calls[-1]["sha"] == shas[-1]


def test_invalid_verdict_records_why(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    manager = use_manager(monkeypatch, verdict="approved", message="")

    with app.app_context():
        counts = review_pending()
    assert counts["failed"] == 1
    with app.app_context():
        assert Image.get(Image.sha == sha).review_note == (
            "fake_moderator: invalid verdict 'approved'"
        )


def test_payload_hands_the_hook_a_public_url(app, client, monkeypatch):
    #: 配了对外基址时优先用它拼 /raw，而不是副本直链。
    monkeypatch.setitem(app.config, "EXTERNAL_BASE_URL", "https://img.example.com")
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    manager = use_manager(monkeypatch, verdict="pass")

    with app.app_context():
        review_pending()

    payload = manager.calls[0]
    assert payload["sha"] == sha
    assert payload["src"] == "/raw/%s" % sha
    assert payload["url"] == "https://img.example.com/raw/%s" % sha


def test_payload_falls_back_to_public_replica_url(app, client, monkeypatch):
    monkeypatch.setitem(app.config, "EXTERNAL_BASE_URL", "")
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        image = Image.get(Image.sha == sha)
        replica = replicas_for(image)[0]
        replica.url = "https://cdn.example.test/files/photo.png"
        replica.save(only=[ImageBackend.url])
    manager = use_manager(monkeypatch, verdict="pass")

    with app.app_context():
        review_pending()

    assert manager.calls[0]["url"] == "https://cdn.example.test/files/photo.png"
    assert manager.calls[0]["src"] == "/raw/%s" % sha


def test_payload_skips_local_replica_and_uses_public_one(app, client, monkeypatch):
    #: 双副本（up2local 在前 + 公开桶在后）：第一个副本只有 /raw 相对路径，
    #: 必须跳过它，拿到后面公开桶的 http 直链，否则审核服务商抓不到图。
    monkeypatch.setitem(app.config, "EXTERNAL_BASE_URL", "")
    from sapic.models.storage import StorageBackend

    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        image = Image.get(Image.sha == sha)
        local = replicas_for(image)[0]
        local.url = "/raw/%s" % sha
        local.save(only=[ImageBackend.url])
        cdn_backend = StorageBackend.create(
            name="cdn-review-test", hook_name="up2upyun",
            visibility="public", priority=200,
        )
        ImageBackend.create(
            image=image,
            backend=cdn_backend,
            url="https://cdn.example.test/files/photo.png",
            state="ok",
        )
    manager = use_manager(monkeypatch, verdict="pass")

    with app.app_context():
        review_pending()

    assert manager.calls[0]["url"] == "https://cdn.example.test/files/photo.png"


def test_private_image_is_not_moderated(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        image = Image.get(Image.sha == sha)
        image.visibility = VISIBILITY_PRIVATE
        image.save(only=[Image.visibility])
    manager = use_manager(monkeypatch, verdict="block")

    with app.app_context():
        counts = review_pending()

    assert counts == {
        "scanned": 0,
        "passed": 0,
        "blocked": 0,
        "purged": 0,
        "failed": 0,
        "samples": [],
    }
    assert manager.calls == []
    with app.app_context():
        assert Image.get(Image.sha == sha).review_state is None


def test_private_album_is_not_moderated(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        image = Image.get(Image.sha == sha)
        image.album.visibility = VISIBILITY_PRIVATE
        image.album.save(only=[Album.visibility])
    manager = use_manager(monkeypatch, verdict="block")

    with app.app_context():
        counts = review_pending()

    assert counts["scanned"] == 0
    assert manager.calls == []
    with app.app_context():
        assert Image.get(Image.sha == sha).review_state is None


def test_public_condition_skips_blocked_images(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    use_manager(monkeypatch, verdict="block")

    with app.app_context():
        review_pending()
        from sapic.models import Album
        from peewee import JOIN

        query = (
            Image.select(Image)
            .join(Album, JOIN.LEFT_OUTER, on=(Image.album == Album.id))
            .where(public_condition())
        )
        assert sha not in [row.sha for row in query]


def test_admin_approves_a_blocked_image(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    use_manager(monkeypatch, verdict="block")
    with app.app_context():
        review_pending()

    promote_admin(app)
    response = client.post(
        "/api/v2/review/%s" % sha,
        json={"action": "approve", "note": "false positive"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["image"]["sha"] == sha

    with app.app_context():
        image = Image.get(Image.sha == sha)
        assert image.review_state == REVIEW_PASS
        assert image.review_note == "false positive"
    assert app.test_client().get("/raw/%s" % sha).status_code == 200


def test_admin_queue_and_purge(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    use_manager(monkeypatch, verdict="block", message="nsfw")
    with app.app_context():
        review_pending()
    promote_admin(app)

    listing = client.get("/api/v2/review")
    assert listing.status_code == 200
    data = listing.get_json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["review_state"] == REVIEW_BLOCK
    assert data["items"][0]["review_note"] == "nsfw"

    #: 物理删除：行与副本一起消失。
    removed = client.post(
        "/api/v2/review/%s" % sha,
        json={"action": "purge"},
        headers={"X-CSRF-Token": csrf},
    )
    assert removed.status_code == 200
    with app.app_context():
        assert Image.get_or_none(Image.sha == sha) is None
    assert app.test_client().get("/raw/%s" % sha).status_code == 404


def test_review_queue_requires_admin(client):
    csrf = register_and_login(client)
    response = client.get("/api/v2/review", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 403


def test_admin_queue_filters_by_pass_state(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    use_manager(monkeypatch, verdict="pass")
    with app.app_context():
        review_pending()
    promote_admin(app)

    passed = client.get("/api/v2/review?state=pass")
    assert passed.status_code == 200, passed.get_json()
    data = passed.get_json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["sha"] == sha
    assert data["items"][0]["review_state"] == REVIEW_PASS

    #: 同一张图不该出现在 block 队列。
    blocked = client.get("/api/v2/review?state=block")
    assert blocked.status_code == 200
    assert blocked.get_json()["data"]["total"] == 0


def test_auto_purge_removes_blocked_images(app, client, monkeypatch):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    use_manager(monkeypatch, verdict="block", message="nsfw")
    with app.app_context():
        set_setting("review_auto_purge", True)
        counts = review_pending()

    assert counts["purged"] == 1
    assert counts["blocked"] == 0
    with app.app_context():
        assert Image.get_or_none(Image.sha == sha) is None


def test_batch_decisions(app, client, monkeypatch):
    csrf = register_and_login(client)
    shas = [
        upload(client, csrf, filename="a.png").get_json()["data"]["image"]["sha"],
        upload(client, csrf, filename="b.png").get_json()["data"]["image"]["sha"],
    ]
    promote_admin(app)
    headers = {"X-CSRF-Token": csrf}

    response = client.post(
        "/api/v2/review/batch",
        json={"action": "approve", "shas": shas},
        headers=headers,
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["affected"] == 2

    response = client.post(
        "/api/v2/review/batch",
        json={"action": "purge", "shas": [shas[0], "missing-sha"]},
        headers=headers,
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["affected"] == 1
    with app.app_context():
        assert Image.get_or_none(Image.sha == shas[0]) is None
        assert Image.get(Image.sha == shas[1]).review_state == REVIEW_PASS


def test_cli_reports_when_no_moderator_is_enabled(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["sa", "review-pending"])
    assert result.exit_code == 0
    assert "no enabled moderator hook" in result.output
