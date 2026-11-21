# -*- coding: utf-8 -*-
"""sapic.libs.review

Content moderation scan: claim unreviewed images, ask the ``moderator`` hooks,
persist the verdict.

Uploads stay untouched (``先发后审``): the scan runs from a maintenance command
or cron, so a slow moderation API never delays an upload. A ``block`` verdict
only hides the image through ``review_state`` -- nothing is deleted here, an
administrator decides whether to approve or purge it.
"""

from __future__ import annotations

import logging

from flask import current_app

from ..models.base import now
from ..models.image import (
    REVIEW_BLOCK,
    REVIEW_PASS,
    REVIEW_RUNNING,
    STATUS_ENABLED,
    Image,
)
from . import ext
from .hook import get_hook_manager

logger = logging.getLogger(__name__)

#: Rows one run may claim; the schedule (cron) controls the throughput.
REVIEW_BATCH = 50

#: A ``running`` claim older than this is considered abandoned (worker killed
#: mid-scan) and becomes claimable again.
STALE_CLAIM = 600

#: ``review_note`` is a short column; the hook message is only a hint anyway.
NOTE_MAX = 255


def moderator_names() -> list[str]:
    """Enabled hooks implementing the moderator contract."""
    manager = get_hook_manager()
    return [
        name
        for name, hook in sorted(manager.hooks.items())
        if hook.enabled and ext.is_moderator(hook.module)
    ]


def pending_query(limit: int = REVIEW_BATCH):
    """Oldest images without a verdict, plus abandoned claims."""
    stale = now() - STALE_CLAIM
    return (
        Image.select(Image)
        .where(
            (Image.status == STATUS_ENABLED)
            & (
                Image.review_state.is_null()
                | ((Image.review_state == REVIEW_RUNNING) & (Image.reviewed_at < stale))
            )
        )
        .order_by(Image.created_at, Image.id)
        .limit(limit)
    )


def _claim(image: Image) -> bool:
    """Atomically take one row; ``False`` when a concurrent worker won it.

    One ``UPDATE`` per row instead of one batch update: a batch tells us how
    many rows changed but not *which* ones, and working on rows another worker
    claimed would judge (and bill) the same image twice.
    """
    stale = now() - STALE_CLAIM
    updated = (
        Image.update(review_state=REVIEW_RUNNING, reviewed_at=now())
        .where(
            (Image.id == image.id)
            & (
                Image.review_state.is_null()
                | ((Image.review_state == REVIEW_RUNNING) & (Image.reviewed_at < stale))
            )
        )
        .execute()
    )
    return bool(updated)


def image_payload(image: Image) -> dict:
    """Metadata handed to a moderator; deliberately not the ORM row.

    ``url`` is only filled when ``EXTERNAL_BASE_URL`` (``sapic_external_base_url``)
    is configured, since that is the address the site is reachable at from the
    outside. A hook that needs the bytes can GET ``url`` (most content-safety
    APIs accept an image URL) or return "no verdict" and let an operator
    configure the address first.
    """
    base = str(current_app.config.get("EXTERNAL_BASE_URL") or "").rstrip("/")
    src = "/raw/%s" % image.sha
    return {
        "id": image.id,
        "sha": image.sha,
        "filename": image.filename,
        "title": image.title,
        "mime": image.mime,
        "size": image.size,
        "width": image.width,
        "height": image.height,
        "is_video": bool(image.is_video),
        "owner_id": image.owner_id,
        "album_id": image.album_id,
        "created_at": image.created_at,
        "src": src,
        "url": base + src if base else "",
    }


def judge(image: Image) -> tuple[str | None, str]:
    """Ask every enabled moderator; ``None`` means "no verdict, retry later".

    One ``block`` is enough to hide the image, but any failing hook or unknown
    verdict downgrades a clean ``pass`` to "no verdict": guessing ``pass`` would
    silently let content through whenever one reviewer is misconfigured.
    """
    names = moderator_names()
    if not names:
        return None, ""
    payload = image_payload(image)
    blocked: list[str] = []
    passed = False
    failed = False
    notes: list[str] = []
    for result in get_hook_manager().call(
        "review_image", include=names, with_config=True, image=payload
    ):
        message = str(result.get("message") or "").strip()
        if result.get("code") != 0:
            failed = True
            if message:
                notes.append(message)
            continue
        verdict = str(result.get("verdict") or "").strip().lower()
        if verdict == REVIEW_BLOCK:
            blocked.append(message)
        elif verdict == REVIEW_PASS:
            passed = True
        else:
            failed = True
            if message:
                notes.append(message)
    if blocked:
        return REVIEW_BLOCK, (blocked[0] or "blocked by moderator")
    if failed or not passed:
        return None, " ".join(notes)[:NOTE_MAX]
    return REVIEW_PASS, ""


def review_pending(limit: int = REVIEW_BATCH) -> dict:
    """Judge up to ``limit`` images; returns counters for the CLI output."""
    counts = {"scanned": 0, "passed": 0, "blocked": 0, "failed": 0}
    for candidate in list(pending_query(limit)):
        if not _claim(candidate):
            continue
        counts["scanned"] += 1
        try:
            verdict, note = judge(candidate)
        except Exception:  # pragma: no cover - defensive, judge() already guards
            logger.exception("moderation of image %s failed", candidate.sha)
            verdict, note = None, ""
        if verdict is None:
            #: Give the row back so the next run retries instead of leaving it
            #: stuck in ``running`` until the stale window expires.
            Image.update(
                review_state=None, reviewed_at=None, review_note=note or None
            ).where(Image.id == candidate.id).execute()
            counts["failed"] += 1
            continue
        Image.update(
            review_state=verdict, reviewed_at=now(), review_note=note or None
        ).where(Image.id == candidate.id).execute()
        counts["passed" if verdict == REVIEW_PASS else "blocked"] += 1
    return counts
