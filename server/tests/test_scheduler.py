# -*- coding: utf-8 -*-
"""Background jobs: what the scheduler runs and how the leader is elected."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from werkzeug.security import check_password_hash

from sapic.libs import scheduler
from sapic.libs.settings import set_setting
from sapic.libs.users import create_user
from sapic.models import ApiToken, User
from sapic.models.image import Image


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


def upload(client, csrf, filename="photo.png"):
    return client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"fake-image-bytes"), filename)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )


def test_scheduler_does_not_start_inside_tests(app):
    app.config["SCHEDULER"] = True
    assert scheduler.init_app(app) is None
    assert scheduler._scheduler is None


def test_build_registers_all_jobs(app):
    built = scheduler._build_scheduler(app)
    assert {job.id for job in built.get_jobs()} == {
        "purge_expired",
        "review_pending",
        "demo_rotate",
    }
    assert built.running is False


def test_purge_job_removes_an_expired_image(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        Image.update(expire_at=1).where(Image.sha == sha).execute()

    assert scheduler.run_purge(app) == 1
    with app.app_context():
        assert Image.get_or_none(Image.sha == sha) is None


def test_review_job_is_a_noop_without_moderator(app):
    counts = scheduler.run_review(app)
    assert counts == {
        "scanned": 0,
        "passed": 0,
        "blocked": 0,
        "failed": 0,
        "samples": [],
    }


def test_jobs_log_instead_of_raising(app, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("storage is down")

    monkeypatch.setattr(scheduler, "purge_expired", boom)
    monkeypatch.setattr(scheduler, "review_pending", boom)
    #: 后台任务出错不能把调度器打死，只能返回一个"这轮没做事"的结果。
    assert scheduler.run_purge(app) == 0
    assert scheduler.run_review(app)["scanned"] == 0


def test_only_one_process_can_lead(tmp_path):
    lock = tmp_path / "scheduler.lock"
    assert scheduler.acquire_lock(lock) is True
    code = (
        "import sys;"
        "from sapic.libs.scheduler import acquire_lock;"
        "sys.exit(0 if acquire_lock(%r) else 3)" % str(lock)
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 3, result.stderr.decode()

    scheduler.release_lock()
    assert scheduler.acquire_lock(lock) is True
    scheduler.release_lock()


def promote_admin(app, username="alice"):
    from sapic.models.user import User

    with app.app_context():
        user = User.get(User.username == username)
        user.is_admin = True
        user.save(only=[User.is_admin])


def test_status_api_requires_admin(client):
    register_and_login(client)
    assert client.get("/api/v2/scheduler").status_code == 403


def test_status_api_lists_the_jobs(app, client):
    register_and_login(client)
    promote_admin(app)
    response = client.get("/api/v2/scheduler")
    assert response.status_code == 200
    data = response.get_json()["data"]
    #: conftest 关掉了调度器，所以这个 worker 是 disabled 而不是 standby。
    assert data["role"] == "disabled"
    assert [job["id"] for job in data["jobs"]] == [
        "purge_expired",
        "review_pending",
        "demo_rotate",
    ]
    assert [job["interval"] for job in data["jobs"]] == [600, 300, 3600]
    assert all(job["next_run_at"] is None for job in data["jobs"])


def test_external_status_reads_the_shared_last_run(app, monkeypatch, tmp_path):
    status_file = tmp_path / "scheduler-status.json"
    monkeypatch.setattr(scheduler, "STATUS_FILE", status_file)
    monkeypatch.setattr(scheduler, "_last_runs", {})
    status_file.write_text(
        json.dumps(
            {
                "pid": 424242,
                "at": 1,
                "runs": {
                    "purge_expired": {"at": 1, "ok": True, "result": {"removed": 7}}
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scheduler, "external_leader", lambda: 424242)
    monkeypatch.setitem(app.config, "SCHEDULER", False)

    with app.app_context():
        data = scheduler.status(app)
    purge = next(job for job in data["jobs"] if job["id"] == "purge_expired")
    assert data["role"] == "external"
    assert purge["last_run"]["result"] == {"removed": 7}
    assert purge["next_run_at"] is None

    #: 锁文件换了进程但状态文件没更新时，旧结果不能冒充当前调度进程的。
    monkeypatch.setattr(scheduler, "external_leader", lambda: 999999)
    with app.app_context():
        data = scheduler.status(app)
    purge = next(job for job in data["jobs"] if job["id"] == "purge_expired")
    assert purge["last_run"] is None


def test_record_publishes_an_atomic_snapshot(app, monkeypatch, tmp_path):
    status_file = tmp_path / "scheduler-status.json"
    monkeypatch.setattr(scheduler, "STATUS_FILE", status_file)
    monkeypatch.setattr(scheduler, "_last_runs", {})
    monkeypatch.setitem(app.config, "TESTING", False)

    with app.app_context():
        scheduler._record("purge_expired", True, {"removed": 3})

    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    assert payload["runs"]["purge_expired"]["result"] == {"removed": 3}
    assert list(tmp_path.glob("scheduler-status-*.json")) == []


def test_run_now_purges_and_records_the_result(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        Image.update(expire_at=1).where(Image.sha == sha).execute()
    promote_admin(app)

    response = client.post(
        "/api/v2/scheduler/run/purge_expired",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["removed"] == 1
    with app.app_context():
        assert Image.get_or_none(Image.sha == sha) is None

    status = client.get("/api/v2/scheduler").get_json()["data"]
    purge = next(job for job in status["jobs"] if job["id"] == "purge_expired")
    assert purge["last_run"]["ok"] is True
    assert purge["last_run"]["result"] == {"removed": 1}


def test_run_now_reports_a_failed_job(app, client, monkeypatch):
    csrf = register_and_login(client)
    promote_admin(app)

    def boom(*args, **kwargs):
        raise RuntimeError("storage is down")

    monkeypatch.setattr(scheduler, "purge_expired", boom)
    response = client.post(
        "/api/v2/scheduler/run/purge_expired",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["removed"] == 0
    status = client.get("/api/v2/scheduler").get_json()["data"]
    purge = next(job for job in status["jobs"] if job["id"] == "purge_expired")
    assert purge["last_run"]["ok"] is False


def test_run_now_rejects_an_unknown_job(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    response = client.post(
        "/api/v2/scheduler/run/not_a_job",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 404


def configure_demo(app, username="demo01", password="newsecret", interval=3600):
    with app.app_context():
        set_setting("demo_rotate_enabled", True)
        set_setting("demo_rotate_username", username)
        set_setting("demo_rotate_password", password)
        set_setting("demo_rotate_interval", interval)


def test_demo_rotation_is_off_by_default(app):
    assert scheduler.run_demo_rotate(app, force=True) == {
        "rotated": False,
        "reason": "disabled",
    }


def test_demo_rotation_resets_the_password(app, client, monkeypatch):
    """到点改密：新密码生效、会话版本 +1、旧 PAT 一并吊销。"""
    monkeypatch.setattr(scheduler, "_demo_last_run", 0)
    register_and_login(client)
    with app.app_context():
        user = create_user("demo01", "oldsecret")
        ApiToken.create(
            owner=user, name="cli", token_hash="hash-demo", prefix="sapic_abc"
        )
        before = user.session_version

    configure_demo(app)
    assert scheduler.run_demo_rotate(app, force=True) == {
        "rotated": True,
        "reason": "rotated",
    }
    with app.app_context():
        user = User.get(User.username == "demo01")
        assert check_password_hash(user.password_hash, "newsecret")
        assert user.session_version == before + 1
        assert ApiToken.select().where(ApiToken.owner == user).count() == 0

    #: 已经是目标密码时不重复写库、也不重复吊销会话。
    assert scheduler.run_demo_rotate(app, force=True) == {
        "rotated": False,
        "reason": "already current",
    }
    with app.app_context():
        assert User.get(User.username == "demo01").session_version == before + 1


def test_demo_rotation_skips_admins_and_missing_users(app, monkeypatch):
    monkeypatch.setattr(scheduler, "_demo_last_run", 0)
    with app.app_context():
        create_user("alice", "secret123")
    promote_admin(app)

    configure_demo(app, username="alice")
    assert scheduler.run_demo_rotate(app, force=True)["reason"] == "admin account"

    configure_demo(app, username="ghost")
    assert scheduler.run_demo_rotate(app, force=True)["reason"] == "user not found"

    configure_demo(app, username="", password="")
    assert scheduler.run_demo_rotate(app, force=True)["reason"] == "not configured"


def test_demo_rotation_waits_for_the_interval(app, monkeypatch):
    monkeypatch.setattr(scheduler, "_demo_last_run", 0)
    with app.app_context():
        create_user("demo01", "oldsecret")
    configure_demo(app, interval=3600)
    assert scheduler.run_demo_rotate(app, force=True)["reason"] == "rotated"
    #: 刚跑过，非强制调用要等下一个间隔。
    assert scheduler.run_demo_rotate(app)["reason"] == "not due"


def test_cli_runs_both_jobs_once(app, client):
    csrf = register_and_login(client)
    sha = upload(client, csrf).get_json()["data"]["image"]["sha"]
    with app.app_context():
        Image.update(expire_at=1).where(Image.sha == sha).execute()

    result = app.test_cli_runner().invoke(args=["sa", "scheduler", "--once"])
    assert result.exit_code == 0, result.output
    assert "purged 1 expired" in result.output
    with app.app_context():
        assert Image.get_or_none(Image.sha == sha) is None
