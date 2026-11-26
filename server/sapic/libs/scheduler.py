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
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, current_app

from ..basis.vars import DATA_DIR
from ..models.base import now
from .images import purge_expired
from .review import moderator_names, review_pending
from .settings import get_setting
from .users import rotate_demo_password

try:  # pragma: no cover - POSIX everywhere sapic is deployed
    import fcntl
except ImportError:  # pragma: no cover - Windows development machines
    fcntl = None

logger = logging.getLogger(__name__)

LOCK_NAME = "scheduler.lock"
#: Cross-process snapshot of the last job results. Only the PID that holds the
#: lock is trusted by readers, so a dead scheduler's stale file is ignored.
STATUS_FILE = Path(DATA_DIR) / "scheduler-status.json"
#: First run fires shortly after boot: migrations and hook loading come first.
FIRST_PURGE_DELAY = 10
FIRST_REVIEW_DELAY = 30
FIRST_DEMO_ROTATE_DELAY = 60

#: 演示账号改密只在这个周期上"看一眼"：真正的时间间隔从站点设置读，
#: 这样后台改完不用重启调度器（多 worker 只有 leader 在跑）。
DEMO_ROTATE_TICK = 60

#: Job ids in display order; the admin page labels them by id.
JOB_IDS = ("purge_expired", "review_pending", "demo_rotate")

_handle = None
_lock_guard = Lock()
_scheduler: BackgroundScheduler | None = None
#: Last result per job, process-local (the leader is the only one scheduling).
_last_runs: dict[str, dict] = {}
_last_guard = Lock()
#: When the demo password was last checked on this process; 0 means "on boot".
_demo_last_run = 0


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


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def external_leader() -> int | None:
    """PID of a scheduler process running outside this one, when it is alive.

    The container image runs ``flask sa scheduler`` under supervisor and tells
    the web workers ``sapic_scheduler=0``, so there is no local scheduler to
    report. ``acquire_lock`` writes the leader pid into the lock file; trusting
    it lets the admin page say "external" instead of "disabled".
    """
    try:
        pid = int(lock_path().read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return None
    if pid == os.getpid() or not _pid_alive(pid):
        return None
    return pid


def _write_shared_status() -> None:
    """Publish the last-run snapshot atomically so other workers can read it.

    A temp file in the same directory plus ``os.replace`` means readers never
    see a partial JSON document; no read lock is needed.
    """
    payload = {"pid": os.getpid(), "at": now(), "runs": dict(_last_runs)}
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix="scheduler-status-", suffix=".json", dir=STATUS_FILE.parent
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp)
        os.replace(tmp, STATUS_FILE)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _read_shared_status() -> dict | None:
    """Return the published snapshot, or ``None`` when absent/corrupt."""
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _record(job_id: str, ok: bool, result) -> None:
    """Keep the latest outcome for the admin page, process-local and shared."""
    with _last_guard:
        _last_runs[job_id] = {"at": now(), "ok": ok, "result": result}
    try:
        testing = current_app.config.get("TESTING")
    except RuntimeError:
        testing = True
    if not testing:
        try:
            _write_shared_status()
        except Exception:
            logger.exception("cannot publish scheduler status snapshot")


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
                {"scanned": 0, "passed": 0, "blocked": 0, "failed": 0, "samples": []}
                if not moderator_names()
                else review_pending()
            )
        except Exception:
            logger.exception("scheduled moderation scan failed")
            _record("review_pending", False, None)
            return {
                "scanned": 0,
                "passed": 0,
                "blocked": 0,
                "failed": 0,
                "samples": [],
            }
        _record("review_pending", True, counts)
        return counts


def run_demo_rotate(app: Flask, force: bool = False) -> dict:
    """Reset the demo account's password, at most once per configured interval.

    The trigger ticks every :data:`DEMO_ROTATE_TICK` seconds and this function
    decides whether the interval elapsed, so editing the settings in the admin
    UI takes effect without restarting the scheduler. ``force`` skips that
    throttle for the "run now" button.
    """
    global _demo_last_run
    with app.app_context():
        try:
            if not get_setting("demo_rotate_enabled"):
                return {"rotated": False, "reason": "disabled"}
            interval = max(
                int(get_setting("demo_rotate_interval") or 3600), DEMO_ROTATE_TICK
            )
            if not force and now() - _demo_last_run < interval:
                return {"rotated": False, "reason": "not due"}
            _demo_last_run = now()
            result = rotate_demo_password(
                get_setting("demo_rotate_username"),
                get_setting("demo_rotate_password"),
            )
        except Exception:
            logger.exception("scheduled demo password rotation failed")
            _record("demo_rotate", False, None)
            return {"rotated": False, "reason": "error"}
        _record("demo_rotate", True, result)
        return result


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
    if job_id == "demo_rotate":
        #: 手动执行不看间隔，管理员点一次就应该真的检查一遍。
        return {"job": job_id, "demo": run_demo_rotate(app, force=True)}
    raise KeyError(job_id)


def status(app: Flask) -> dict:
    """Snapshot for the admin page: role of this worker, schedule and last run."""
    enabled = bool(app.config.get("SCHEDULER"))
    intervals = {job_id: interval for job_id, _f, interval, _d in job_specs(app)}
    #: demo 任务按分钟 tick，展示给管理员的是真正的轮换间隔（来自站点设置）。
    intervals["demo_rotate"] = max(
        int(get_setting("demo_rotate_interval") or intervals["demo_rotate"]),
        intervals["demo_rotate"],
    )
    leader_pid = None
    if _scheduler is not None:
        role = "leader"
    elif enabled:
        role = "standby"
    else:
        #: 容器里由 supervisor 起独立的 `flask sa scheduler`，web 端看不到它；
        #: 锁文件里的 pid 还活着就说明调度在跑，别让页面误报"已关闭"。
        leader_pid = external_leader()
        role = "external" if leader_pid else "disabled"
    #: 独立进程的结果从共享快照读；pid 不匹配说明文件是上一个调度进程留下的。
    shared = _read_shared_status() if role == "external" else None

    jobs = []
    for job_id in JOB_IDS:
        job = _scheduler.get_job(job_id) if _scheduler is not None else None
        #: demo 的 trigger 只是检查周期，展示的间隔由设置决定。
        use_trigger = job is not None and job_id != "demo_rotate"
        last_run = _last_runs.get(job_id)
        if last_run is None and shared is not None and shared.get("pid") == leader_pid:
            last_run = (shared.get("runs") or {}).get(job_id)
        jobs.append(
            {
                "id": job_id,
                "interval": (
                    int(job.trigger.interval.total_seconds())
                    if use_trigger
                    else intervals[job_id]
                ),
                "next_run_at": (
                    int(job.next_run_time.timestamp())
                    if job is not None and job.next_run_time is not None
                    else None
                ),
                "last_run": last_run,
            }
        )
    return {
        "enabled": enabled,
        "role": role,
        "pid": os.getpid(),
        "leader_pid": leader_pid,
        "lock": str(lock_path()),
        "jobs": jobs,
    }


def job_specs(app: Flask) -> tuple[tuple[str, object, int, int], ...]:
    """Job table shared by the in-process scheduler and ``flask sa scheduler``.

    Each entry is ``(id, callable, interval_seconds, first_delay_seconds)``.
    """
    return (
        (
            "purge_expired",
            run_purge,
            int(app.config.get("SCHEDULER_PURGE_INTERVAL") or 600),
            FIRST_PURGE_DELAY,
        ),
        (
            "review_pending",
            run_review,
            int(app.config.get("SCHEDULER_REVIEW_INTERVAL") or 300),
            FIRST_REVIEW_DELAY,
        ),
        (
            "demo_rotate",
            run_demo_rotate,
            DEMO_ROTATE_TICK,
            FIRST_DEMO_ROTATE_DELAY,
        ),
    )


def _build_scheduler(app: Flask) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(daemon=True)
    for job_id, func, interval, delay in job_specs(app):
        scheduler.add_job(
            func,
            "interval",
            seconds=interval,
            args=[app],
            id=job_id,
            max_instances=1,
            #: 进程被挂起/机器休眠后只补跑一次，不把积压的任务全部执行一遍。
            coalesce=True,
            misfire_grace_time=max(interval, 60),
            next_run_time=datetime.now() + timedelta(seconds=delay),
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
        "scheduler started: purge every %ss, review every %ss, demo rotate every %ss",
        app.config.get("SCHEDULER_PURGE_INTERVAL"),
        app.config.get("SCHEDULER_REVIEW_INTERVAL"),
        DEMO_ROTATE_TICK,
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
