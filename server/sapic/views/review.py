# -*- coding: utf-8 -*-
"""sapic.views.review

Administrator moderation queue: see what a ``moderator`` hook blocked, approve
it, or purge it for good.

``block`` is only a verdict: the bytes and the row stay in place, so a false
positive costs nothing but a click. Purging is the explicit, irreversible
action (replicas first, then the row), which is why it lives here instead of in
the scan.
"""

from __future__ import annotations

from flask import Blueprint, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.auth import admin_required
from ..libs.images import album_serializer, purge_image, serialize_image
from ..models.base import now
from ..models.image import REVIEW_BLOCK, REVIEW_PASS, Image, live_condition
from ..utils.web import ok, page_params, paginate_page

bp = Blueprint("review", __name__)

#: Queue filters; ``pending`` means "not judged yet".
STATES = ("block", "pass", "pending", "all")

#: Admin decisions; ``approve`` writes ``pass`` so the column stays a verdict.
ACTIONS = {"approve": REVIEW_PASS, "block": REVIEW_BLOCK}


@bp.get("/review")
@admin_required
def list_review():
    state = (request.args.get("state") or "block").strip().lower()
    if state not in STATES:
        raise ApiError("invalid state", ErrorCode.PARAM_ERROR)

    query = Image.select(Image).where(live_condition())
    if state == "pending":
        query = query.where(Image.review_state.is_null())
    elif state != "all":
        query = query.where(Image.review_state == ACTIONS[state])

    serialize, prefetch = album_serializer()

    def with_review(image: Image) -> dict:
        data = serialize(image)
        #: 审核字段只在这个管理接口输出，公开列表不暴露判定结果。
        data.update(
            review_state=image.review_state,
            review_note=image.review_note,
            reviewed_at=image.reviewed_at,
        )
        return data

    page, page_size = page_params(default_size=15)
    return ok(
        paginate_page(
            query,
            Image,
            with_review,
            page=page,
            page_size=page_size,
            prefetch=prefetch,
        )
    )


@bp.post("/review/<sha>")
@admin_required
def decide(sha: str):
    image = Image.get_or_none((Image.sha == sha) & live_condition())
    if image is None:
        raise ApiError("image not found", ErrorCode.NOT_FOUND, 404)

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    note = str(payload.get("note") or "").strip()[:255]

    if action == "purge":
        #: 人工确认删除：副本与行一起消失，sha 不再被占用（与过期清理同一路径）。
        purge_image(image)
        return ok({"deleted": True})

    if action not in ACTIONS:
        raise ApiError("invalid action", ErrorCode.PARAM_ERROR)

    image.review_state = ACTIONS[action]
    image.reviewed_at = now()
    image.review_note = note or None
    image.save(only=[Image.review_state, Image.reviewed_at, Image.review_note])
    #: 通过后图片立即回到原有的可见性口径，不需要再扫一次。
    return ok({"image": serialize_image(image, image.album)})
