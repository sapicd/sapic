# -*- coding: utf-8 -*-
"""User management API (admin only).

The admin UI needs to review registrations, enable/disable accounts, grant the
admin flag and remove accounts for good: listing, a single PATCH and DELETE.
Deleting is the one destructive operation here -- ``purge_user`` takes the
account's albums, images, replicas and tokens with it, so it is done in one
transaction rather than as a table-row toggle.
"""

from __future__ import annotations

from flask import Blueprint, g, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.auth import admin_required
from ..libs.users import notify_review, purge_user, serialize_user
from ..models import User
from ..models.base import now
from ..models.user import (
    STATUS_DISABLED,
    STATUS_NORMAL,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from ..utils.web import ok, paginate

bp = Blueprint("users", __name__)

#: Every status a user row may carry.
STATUSES = (STATUS_REJECTED, STATUS_PENDING, STATUS_DISABLED, STATUS_NORMAL)


def _serializer(user: User) -> dict:
    return serialize_user(user, include_private=True)


def _limit() -> int:
    try:
        return int(request.args.get("limit", 20))
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid limit", ErrorCode.PARAM_ERROR) from exc


@bp.get("/users")
@admin_required
def list_users():
    query = User.select()

    keyword = (request.args.get("keyword") or "").strip()
    if keyword:
        query = query.where(
            (User.username.contains(keyword))
            | (User.nickname.contains(keyword))
            | (User.email.contains(keyword))
        )

    raw_status = request.args.get("status")
    if raw_status not in (None, ""):
        try:
            status = int(raw_status)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid status", ErrorCode.PARAM_ERROR) from exc
        if status not in STATUSES:
            raise ApiError("invalid status", ErrorCode.PARAM_ERROR)
        query = query.where(User.status == status)

    data = paginate(
        query,
        User,
        _serializer,
        limit=_limit(),
        cursor=request.args.get("cursor"),
    )
    #: 待审核数量给后台角标用，省掉前端一次额外请求。
    data["counts"] = {
        "total": User.select().count(),
        "pending": User.select().where(User.status == STATUS_PENDING).count(),
    }
    return ok(data)


@bp.patch("/users/<int:user_id>")
@admin_required
def update_user(user_id: int):
    user = User.get_or_none(User.id == user_id)
    if user is None:
        raise ApiError("user not found", ErrorCode.NOT_FOUND, 404)

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ApiError("payload must be a JSON object", ErrorCode.PARAM_ERROR)

    fields = []
    previous_status = user.status
    reason = ""
    reviewed = False
    if "status" in data:
        status = data.get("status")
        #: bool 是 int 的子类（True == 1），必须先排除。
        if isinstance(status, bool) or not isinstance(status, int):
            raise ApiError("invalid status", ErrorCode.PARAM_ERROR)
        if status not in STATUSES:
            raise ApiError("invalid status", ErrorCode.PARAM_ERROR)
        if user.id == g.user.id:
            raise ApiError(
                "cannot change your own status", ErrorCode.FORBIDDEN, 403
            )
        user.status = status
        fields.append(User.status)
        #: 拒绝理由只对「已拒绝」有意义，换成别的状态就清掉，免得页面上留着旧原因。
        if status == STATUS_REJECTED:
            reason = str(data.get("reason") or "").strip()[:200]
            user.status_reason = reason
        else:
            user.status_reason = None
        fields.append(User.status_reason)
        if status != STATUS_NORMAL:
            #: 禁用/拒绝后立刻让该用户已登录的会话失效。
            user.session_version = int(user.session_version or 0) + 1
            fields.append(User.session_version)
        #: 只有「待审核 → 通过/拒绝」才是审核决定，启用/禁用不发审核邮件。
        reviewed = previous_status == STATUS_PENDING and status in (
            STATUS_NORMAL,
            STATUS_REJECTED,
        )

    if "is_admin" in data:
        is_admin = data.get("is_admin")
        if not isinstance(is_admin, bool):
            raise ApiError("invalid is_admin", ErrorCode.PARAM_ERROR)
        if user.id == g.user.id and not is_admin:
            raise ApiError(
                "cannot revoke your own admin permission",
                ErrorCode.FORBIDDEN,
                403,
            )
        user.is_admin = is_admin
        fields.append(User.is_admin)

    if not fields:
        raise ApiError("nothing to update", ErrorCode.PARAM_ERROR)

    user.updated_at = now()
    fields.append(User.updated_at)
    user.save(only=fields)

    if reviewed:
        #: 投递失败由 send_mail 内部吞掉并记日志，审核结果照常返回。
        notify_review(user, user.status, reason)
    return ok({"user": _serializer(user)})


@bp.delete("/users/<int:user_id>")
@admin_required
def delete_user(user_id: int):
    user = User.get_or_none(User.id == user_id)
    if user is None:
        raise ApiError("user not found", ErrorCode.NOT_FOUND, 404)
    #: 删掉自己会立刻失去登录凭据，也容易把站点删成没人管的状态。
    if user.id == g.user.id:
        raise ApiError("cannot delete your own account", ErrorCode.FORBIDDEN, 403)

    purge_user(user)
    return ok({"deleted": True})
