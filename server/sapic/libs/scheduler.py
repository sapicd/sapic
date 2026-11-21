# -*- coding: utf-8 -*-
"""sapic.libs.scheduler

In-process background jobs: expired-image purge and moderation scan.

gunicorn starts several workers and every one of them runs ``create_app()``, so
the schedule must live in exactly one of them. Each worker tries a non-blocking
``flock`` on ``data/scheduler.lock``; the winner starts APScheduler, the rest
stay out. No Redis or external queue is involved, and a standalone
``flask sa scheduler`` process takes the same lock when the web workers are told
to stay out of it (``sapic_scheduler=0``).

Jobs never run inside a request: each opens its own app context, and a failure
is logged instead of killing the schedule.
"""

from __future__ import annotations

import atexit
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

from ..basis.vars import DATA_DIR
from ..models.base import now
from .images import purge_expired
from .review import moderator_names, review_pending

try:  # pragma: no cover - POSIX everywhere sapic is deployed
    import fcntl
except ImportError:  # pragma: no cover - Windows development machines
    fcntl = None

logger = logging.getLogger(__name__)

LOCK_NAME = "scheduler.lock"
#: First run fires shortly after boot: migrations and hook loading come first.
FIRST_PURGE_DELAY = 10
FIRST_REVIEW_DELAY = 30

#: Job ids in display order; the admin page labels them by id.
JOB_IDS = ("purge_expired", "review_pending")

_handle = None
_lock_guard = Lock()
_scheduler: BackgroundScheduler | None = None
#: Last result per job, process-local (the leader is the only one scheduling).
_last_runs: dict[str, dict] = {}
_last_guard = Lock()


def lock_path() -> Path:
    """File every candidate scheduler process locks for the leading role."""
    return Path(DATA_DIR) / LOCK_NAME


def acquire_lock(path: str | Path | None = None) -> bool:
    """Claim the scheduler role; ``False`` when another process holds it.

    ``path`` only exists for tests; production always uses :func:`lock_path`.
    """
    global _handle
    with _lock_guard:
        if _handle is not None:
            return True
        path = Path(path) if path is not None else lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+")
        if fcntl is None:
            #: 没有 flock 的平台（Windows 开发机）无法选主，退化为"总是启动"：
            #: 单进程开发环境本来就只有一个，多 worker 的重复执行是幂等的。
            logger.warning("fcntl is unavailable, scheduler leadership is not enforced")
            _handle = handle
            return True
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        _handle = handle
        return True


def release_lock() -> None:
    """Give the role up (shutdown, tests). Safe to call without the lock."""
    global _handle
    with _lock_guard:
        if _handle is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(_handle.fileno(), fcntl.LOCK_UN)
        except OSError:  # pragma: no cover - closing below is enough
            pass
        _handle.close()
        _handle = None


def _record(job_id: str, ok: bool, result) -> None:
    """Keep the latest outcome for the admin page (process-local, best effort)."""
    with _last_guard:
        _last_runs[job_id] = {"at": now(), "ok": ok, "result": result}


def run_purge(app: Flask, limit: int | None = None) -> int:
    """One expiry sweep; failures are logged, never raised into the schedule."""
    with app.app_context():
        try:
            removed = purge_expired() if limit is None else purge_expired(limit)
        except Exception:
            logger.exception("scheduled expiry purge failed")
            _record("purge_expired", False, None)
            return 0
        _record("purge_expired", True, {"removed": removed})
        return removed


def run_review(app: Flask) -> dict:
    """One moderation scan; a site without moderator hooks returns instantly."""
    with app.app_context():
        try:
            counts = (
                {"scanned": 0, "passed": 0, "blocked": 0, "failed": 0}
                if not moderator_names()
                else review_pending()
            )
        except Exception:
            logger.exception("scheduled moderation scan failed")
            _record("review_pending", False, None)
            return {"scanned": 0, "passed": 0, "blocked": 0, "failed": 0}
        _record("review_pending", True, counts)
        return counts


def run_job(app: Flask, job_id: str, limit: int | None = None) -> dict:
    """Run one job synchronously (the admin page's "run now" button).

    Deliberately not routed through the scheduler: a request may land on a
    standby worker, and both jobs are idempotent, so calling them directly is
    simpler than waking the leader. Batching stays small (``limit``) so the
    HTTP response does not outlive the gunicorn timeout.
    """
    if job_id == "purge_expired":
        return {"job": job_id, "removed": run_purge(app, limit)}
    if job_id == "review_pending":
        return {"job": job_id, "review": run_review(app)}
    raise KeyError(job_id)


def status(app: Flask) -> dict:
    """Snapshot for the admin page: role of this worker, schedule and last run."""
    enabled = bool(app.config.get("SCHEDULER"))
    intervals = {
        "purge_expired": int(app.config.get("SCHEDULER_PURGE_INTERVAL") or 600),
        "review_pending": int(app.config.get("SCHEDULER_REVIEW_INTERVAL") or 300),
    }
    jobs = []
    for job_id in JOB_IDS:
        job = _scheduler.get_job(job_id) if _scheduler is not None else None
        jobs.append(
            {
                "id": job_id,
                "interval": (
                    int(job.trigger.interval.total_seconds())
                    if job is not None
                    else intervals[job_id]
                ),
                "next_run_at": (
                    int(job.next_run_time.timestamp())
                    if job is not None and job.next_run_time is not None
                    else None
                ),
                "last_run": _last_runs.get(job_id),
            }
        )
    if _scheduler is not None:
        role = "leader"
    else:
        role = "standby" if enabled else "disabled"
    return {
        "enabled": enabled,
        "role": role,
        "pid": os.getpid(),
        "lock": str(lock_path()),
        "jobs": jobs,
    }


def _build_scheduler(app: Flask) -> BackgroundScheduler:
    purge_interval = int(app.config.get("SCHEDULER_PURGE_INTERVAL") or 600)
    review_interval = int(app.config.get("SCHEDULER_REVIEW_INTERVAL") or 300)
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        run_purge,
        "interval",
        seconds=purge_interval,
        args=[app],
        id="purge_expired",
        max_instances=1,
        #: 进程被挂起/机器休眠后只补跑一次，不把积压的任务全部执行一遍。
        coalesce=True,
        misfire_grace_time=max(purge_interval, 60),
        next_run_time=datetime.now() + timedelta(seconds=FIRST_PURGE_DELAY),
    )
    scheduler.add_job(
        run_review,
        "interval",
        seconds=review_interval,
        args=[app],
        id="review_pending",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=max(review_interval, 60),
        next_run_time=datetime.now() + timedelta(seconds=FIRST_REVIEW_DELAY),
    )
    return scheduler


def init_app(app: Flask) -> BackgroundScheduler | None:
    """Start the schedule in this process when it is allowed to lead."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if not app.config.get("SCHEDULER"):
        logger.info("scheduler disabled by configuration")
        return None
    if app.config.get("TESTING"):
        #: 测试里不跑后台线程：用例需要时直接调 run_purge / run_review。
        return None
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        #: ``flask run --reload`` 的父进程只负责重启子进程，不该占着锁。
        return None
    if not acquire_lock():
        logger.info("scheduler already runs in another process, skipping this one")
        return None
    scheduler = _build_scheduler(app)
    scheduler.start()
    _scheduler = scheduler
    atexit.register(stop)
    logger.info(
        "scheduler started: purge every %ss, review every %ss",
        app.config.get("SCHEDULER_PURGE_INTERVAL"),
        app.config.get("SCHEDULER_REVIEW_INTERVAL"),
    )
    return scheduler


def stop() -> None:
    """Shut the scheduler down and release the role lock."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover - already stopped
            logger.exception("scheduler shutdown failed")
        _scheduler = None
    release_lock()
