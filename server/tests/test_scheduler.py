# -*- coding: utf-8 -*-
"""Background jobs: what the scheduler runs and how the leader is elected."""

import io
import subprocess
import sys
from pathlib import Path

from sapic.libs import scheduler
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


def test_build_registers_the_two_jobs(app):
    built = scheduler._build_scheduler(app)
    assert {job.id for job in built.get_jobs()} == {"purge_expired", "review_pending"}
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
    assert counts == {"scanned": 0, "passed": 0, "blocked": 0, "failed": 0}


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
    assert [job["id"] for job in data["jobs"]] == ["purge_expired", "review_pending"]
    assert [job["interval"] for job in data["jobs"]] == [600, 300]
    assert all(job["next_run_at"] is None for job in data["jobs"])


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
