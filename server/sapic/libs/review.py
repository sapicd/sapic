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
from peewee import JOIN

from ..models import Album
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
from .images import public_visibility_condition, purge_image
from .settings import get_setting
from .storage import public_src, replicas_for

logger = logging.getLogger(__name__)

#: Rows one run may claim; the schedule (cron) controls the throughput.
REVIEW_BATCH = 50

#: A ``running`` claim older than this is considered abandoned (worker killed
#: mid-scan) and becomes claimable again.
STALE_CLAIM = 600

#: A failed verdict keeps ``reviewed_at`` as a backoff clock: skip it for a
#: while so a permanently broken hook cannot starve the rest of the queue.
#: Must be longer than the scheduler interval (5 min by default), otherwise
#: the retry is due again on the very next tick and nothing else gets scanned.
RETRY_DELAY = 3600

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
    """Oldest public images without a verdict, plus abandoned claims.

    Private images are never sent to a moderator: the content-safety service
    cannot fetch an authenticated ``/raw`` link, and paying to judge content
    the public cannot see is pointless.
    """
    stale = now() - STALE_CLAIM
    retry_due = now() - RETRY_DELAY
    return (
        Image.select(Image)
        .join(Album, JOIN.LEFT_OUTER, on=(Image.album == Album.id))
        .where(
            public_visibility_condition(),
            (Image.status == STATUS_ENABLED)
            & (
                #: 未审过；或失败退避到期；或 running 被遗弃。
                (
                    Image.review_state.is_null()
                    & (
                        Image.reviewed_at.is_null()
                        | (Image.reviewed_at < retry_due)
                    )
                )
                | ((Image.review_state == REVIEW_RUNNING) & (Image.reviewed_at < stale))
            ),
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
    retry_due = now() - RETRY_DELAY
    updated = (
        Image.update(review_state=REVIEW_RUNNING, reviewed_at=now())
        .where(
            (Image.id == image.id)
            & (
                (
                    Image.review_state.is_null()
                    & (
                        Image.reviewed_at.is_null()
                        | (Image.reviewed_at < retry_due)
                    )
                )
                | ((Image.review_state == REVIEW_RUNNING) & (Image.reviewed_at < stale))
            )
        )
        .execute()
    )
    return bool(updated)


def image_payload(image: Image) -> dict:
    """Metadata handed to a moderator; deliberately not the ORM row.

    ``url`` is an address a third-party reviewer can actually fetch: the
    configured ``EXTERNAL_BASE_URL`` + ``/raw/<sha>`` first, then a registered
    external link or the top public replica's direct URL. Private images never
    reach this function (see :func:`pending_query`), so no authenticated route
    is handed out.
    """
    base = str(current_app.config.get("EXTERNAL_BASE_URL") or "").rstrip("/")
    src = "/raw/%s" % image.sha
    url = base + src if base else ""
    if not url and image.source_url:
        url = image.source_url
    if not url:
        #: 多副本（如 up2local + 公开桶）按优先级排序，第一个可能是本地
        #: ``/raw/<sha>`` 相对路径——不能因此放弃，逐个找带 http 直链的公开副本。
        for replica in replicas_for(image):
            candidate = public_src(replica) or ""
            if candidate.startswith(("http://", "https://")):
                url = candidate
                break
    if url and not url.startswith(("http://", "https://")):
        url = ""
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
        "url": url,
    }


def judge(image: Image) -> tuple[str | None, str]:
    """Ask every enabled moderator; ``None`` means "no verdict, retry later".

    One ``block`` is enough to hide the image, but any failing hook or unknown
    verdict downgrades a clean ``pass`` to "no verdict": guessing ``pass`` would
    silently let content through whenever one reviewer is misconfigured.
    """
    names = moderator_names()
    if not names:
        return None, "no enabled moderator hook"
    payload = image_payload(image)
    blocked: list[str] = []
    passed = False
    failed = False
    notes: list[str] = []
    results = list(
        get_hook_manager().call(
            "review_image", include=names, with_config=True, image=payload
        )
    )
    if not results:
        return None, "no verdict returned by moderator hooks"
    for result in results:
        sender = str(result.get("sender") or "moderator")
        message = str(result.get("message") or "").strip()
        if result.get("code") != 0:
            failed = True
            notes.append(message or "%s: error code %s" % (sender, result.get("code")))
            continue
        verdict = str(result.get("verdict") or "").strip().lower()
        if verdict == REVIEW_BLOCK:
            blocked.append(message)
        elif verdict == REVIEW_PASS:
            passed = True
        else:
            failed = True
            notes.append(
                message
                or "%s: invalid verdict %r" % (sender, result.get("verdict"))
            )
    if blocked:
        return REVIEW_BLOCK, (blocked[0] or "blocked by moderator")
    if failed or not passed:
        return None, " ".join(notes)[:NOTE_MAX]
    return REVIEW_PASS, ""


def review_pending(limit: int = REVIEW_BATCH) -> dict:
    """Judge up to ``limit`` images; returns counters for the CLI output."""
    counts = {
        "scanned": 0,
        "passed": 0,
        "blocked": 0,
        "purged": 0,
        "failed": 0,
        "samples": [],
    }
    auto_purge = bool(get_setting("review_auto_purge"))
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
            #: Give the row back with ``reviewed_at`` as a backoff clock, so a
            #: broken hook cannot keep the scan reading the same 50 rows forever.
            Image.update(
                review_state=None, reviewed_at=now(), review_note=note or None
            ).where(Image.id == candidate.id).execute()
            counts["failed"] += 1
            if len(counts["samples"]) < 3:
                counts["samples"].append({"sha": candidate.sha, "note": note})
            continue
        if verdict == REVIEW_BLOCK and auto_purge:
            #: 后台策略打开时直接物理删除；失败则退回普通 block，保留复核机会。
            try:
                purge_image(candidate)
            except Exception:
                logger.exception("auto-purge failed for image %s", candidate.sha)
                Image.update(
                    review_state=verdict,
                    reviewed_at=now(),
                    review_note=(note + " (auto-purge failed)")[:NOTE_MAX] or None,
                ).where(Image.id == candidate.id).execute()
                counts["blocked"] += 1
            else:
                counts["purged"] += 1
            continue
        Image.update(
            review_state=verdict, reviewed_at=now(), review_note=note or None
        ).where(Image.id == candidate.id).execute()
        counts["passed" if verdict == REVIEW_PASS else "blocked"] += 1
    return counts
