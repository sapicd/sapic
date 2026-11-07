# -*- coding: utf-8 -*-
"""Storage backend APIs.

Two surfaces share this blueprint:

* ``/backends`` (admin): the ``scope="system"`` defaults maintained by the
  operator.
* ``/me/backends`` (any signed-in user): their own ``scope="user"`` backends,
  available only when the site setting ``allow_user_backends`` is on. Secrets
  are never echoed back — password fields come back masked.

A backend is one configured instance of a storage driver (a hook with
``catalog=upload``). Uploads go to the enabled backend with the smallest
``priority``; existing images keep reading from the backend that holds their
replica, so disabling or deleting a backend is refused while it still owns
objects.
"""

from __future__ import annotations

from flask import Blueprint, g, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.auth import admin_required, login_required
from ..libs.storage import (
    backend_payload,
    create_backend,
    create_user_backend,
    delete_backend,
    list_backend_rows,
    list_backends,
    list_user_backend_rows,
    primary_backend_id,
    private_readable,
    update_backend,
    update_user_backend,
    upload_drivers,
    user_backend_limit,
    user_backend_payload,
    user_backends_allowed,
)
from ..models import StorageBackend
from ..models.storage import SCOPE_USER, VISIBILITY_PUBLIC
from ..utils.web import ok

bp = Blueprint("backends", __name__)


def _json_body() -> dict:
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ApiError("payload must be a JSON object", ErrorCode.PARAM_ERROR)
    return data


def _drivers() -> list[dict]:
    return [
        {
            "name": manifest["name"],
            "title": manifest["title"],
            "description": manifest["description"],
            "fields": manifest["config_schema"],
            #: 能否作为「私有」后端：驱动要能签发临时读地址（本地驱动除外）。
            "private_readable": private_readable(manifest["name"]),
        }
        for manifest in upload_drivers()
    ]


def _payload() -> dict:
    #: Order matters: the rows are synced first, otherwise ``primary_backend_id``
    #: may answer before the freshly enabled driver has a row at all.
    rows = list_backend_rows()
    primary = primary_backend_id()
    return {
        "items": [backend_payload(row, primary) for row in rows],
        "drivers": _drivers(),
    }


def _my_payload() -> dict:
    enabled = user_backends_allowed()
    primary = None
    if enabled:
        primary = next((item["id"] for item in list_backends(g.user)), None)
    return {
        "enabled": enabled,
        "limit": user_backend_limit(),
        "items": [
            user_backend_payload(row, primary)
            for row in list_user_backend_rows(g.user)
        ],
        "drivers": _drivers(),
    }


def _own_backend(backend_id: int) -> StorageBackend:
    """Only the owner may touch a user backend; others get a plain 404."""
    row = StorageBackend.get_or_none(StorageBackend.id == backend_id)
    if row is None or row.scope != SCOPE_USER or row.owner_id != g.user.id:
        raise ApiError("backend not found", ErrorCode.NOT_FOUND, 404)
    return row


@bp.get("/me/backends")
@login_required
def read_my_backends():
    return ok(_my_payload())


@bp.post("/me/backends")
@login_required
def add_my_backend():
    data = _json_body()
    hook_name = str(data.get("hook_name") or "").strip()
    if not hook_name:
        raise ApiError("hook_name is required", ErrorCode.PARAM_ERROR)
    create_user_backend(
        g.user,
        name=data.get("name") or "",
        hook_name=hook_name,
        config=data.get("config"),
        priority=data.get("priority"),
        enabled=data.get("enabled", True),
        visibility=data.get("visibility") or VISIBILITY_PUBLIC,
    )
    return ok(_my_payload(), status=201)


@bp.patch("/me/backends/<int:backend_id>")
@login_required
def modify_my_backend(backend_id: int):
    update_user_backend(_own_backend(backend_id), _json_body())
    return ok(_my_payload())


@bp.delete("/me/backends/<int:backend_id>")
@login_required
def remove_my_backend(backend_id: int):
    delete_backend(_own_backend(backend_id))
    return ok(_my_payload())


@bp.get("/backends")
@admin_required
def read_backends():
    return ok(_payload())


@bp.post("/backends")
@admin_required
def add_backend():
    data = _json_body()
    hook_name = str(data.get("hook_name") or "").strip()
    if not hook_name:
        raise ApiError("hook_name is required", ErrorCode.PARAM_ERROR)
    create_backend(
        name=data.get("name") or "",
        hook_name=hook_name,
        config=data.get("config"),
        priority=data.get("priority"),
        enabled=data.get("enabled", True),
        visibility=data.get("visibility") or VISIBILITY_PUBLIC,
    )
    return ok(_payload(), status=201)


@bp.patch("/backends/<int:backend_id>")
@admin_required
def modify_backend(backend_id: int):
    row = StorageBackend.get_or_none(StorageBackend.id == backend_id)
    if row is None:
        raise ApiError("backend not found", ErrorCode.NOT_FOUND, 404)
    update_backend(row, _json_body())
    return ok(_payload())


@bp.delete("/backends/<int:backend_id>")
@admin_required
def remove_backend(backend_id: int):
    row = StorageBackend.get_or_none(StorageBackend.id == backend_id)
    if row is None:
        raise ApiError("backend not found", ErrorCode.NOT_FOUND, 404)
    delete_backend(row)
    return ok(_payload())
