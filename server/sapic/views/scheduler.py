# -*- coding: utf-8 -*-
"""sapic.views.scheduler

Admin view of the background jobs: which worker leads, what runs next, and a
manual trigger for one job.

The admin page shows the schedule of the **worker that served the request**, so
a follower answers with ``role: standby`` and no ``next_run_at``; the leader's
snapshot is the authoritative one. Running a job works from any worker because
both jobs are idempotent and self-contained.
"""

from __future__ import annotations

from flask import Blueprint, current_app

from ..basis.errors import ApiError, ErrorCode
from ..libs import scheduler
from ..libs.auth import admin_required
from ..utils.web import ok

bp = Blueprint("scheduler", __name__)


@bp.get("/scheduler")
@admin_required
def get_status():
    return ok(scheduler.status(current_app._get_current_object()))


@bp.post("/scheduler/run/<job_id>")
@admin_required
def run_job(job_id: str):
    try:
        return ok(scheduler.run_job(current_app._get_current_object(), job_id))
    except KeyError:
        raise ApiError("unknown job", ErrorCode.NOT_FOUND, 404)
