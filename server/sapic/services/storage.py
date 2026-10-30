# -*- coding: utf-8 -*-
"""Storage backend resolution and driver invocation.

Priority is static configuration, never a runtime race: reads walk the
replica list from the highest priority backend downwards and fall back on
failure. This keeps behaviour predictable and avoids probe traffic.
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app
from peewee import IntegrityError

from ..libs.hook import get_hook_manager
from ..models import ImageBackend, StorageBackend, UserBackend
from ..models.storage import SCOPE_GLOBAL, SCOPE_USER

DEFAULT_BACKEND_NAME = "local"


def ensure_default_backend() -> StorageBackend:
    """Make sure a local backend exists so every replica has a backend row."""
    row = StorageBackend.get_or_none(StorageBackend.name == DEFAULT_BACKEND_NAME)
    if row is not None:
        return row
    try:
        return StorageBackend.create(
            name=DEFAULT_BACKEND_NAME,
            hook_name="up2local",
            config={},
            scope=SCOPE_GLOBAL,
            visibility="private",
            priority=100,
            enabled=True,
        )
    except IntegrityError:
        #: Another worker created it concurrently.
        return StorageBackend.get(StorageBackend.name == DEFAULT_BACKEND_NAME)


def _as_dict(row: StorageBackend) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "hook_name": row.hook_name,
        "config": dict(row.config or {}),
        "visibility": row.visibility,
        "priority": row.priority,
    }


def list_backends(user=None) -> list[dict]:
    """Backends available to ``user`` ordered by effective priority."""
    rows = list(
        StorageBackend.select()
        .where(StorageBackend.enabled == True)  # noqa: E712
        .order_by(StorageBackend.priority, StorageBackend.id)
    )

    grants = {}
    if user is not None:
        grants = {
            grant.backend_id: grant
            for grant in UserBackend.select().where(UserBackend.user == user)
        }

    items = []
    for row in rows:
        if row.scope == SCOPE_USER:
            if user is None or row.owner_id != user.id:
                continue
        elif row.scope == SCOPE_GLOBAL and user is not None and grants:
            grant = grants.get(row.id)
            if grant is None or not grant.enabled:
                continue
        item = _as_dict(row)
        grant = grants.get(row.id)
        if grant is not None:
            item["priority"] = grant.priority
        items.append(item)

    if not items:
        items = [_as_dict(ensure_default_backend())]

    items.sort(key=lambda item: (item["priority"], item["id"] or 0))
    return items


def driver_backend(backend: dict) -> dict:
    """Add runtime-only driver options (never persisted)."""
    data = dict(backend)
    config = dict(data.get("config") or {})
    if data.get("hook_name") == "up2local" and not config.get("root"):
        config["root"] = current_app.config["STORAGE_DIR"]
    data["config"] = config
    return data


def save_object(
    backend: dict,
    sha: str,
    filename: str,
    stream: bytes,
    upload_path: str,
) -> dict:
    results = get_hook_manager().call(
        "upimg_save",
        include=[backend["hook_name"]],
        filename=filename,
        stream=stream,
        upload_path=upload_path,
        backend=driver_backend(backend),
    )
    if not results:
        return {"code": 1, "msg": "no storage driver available"}
    return results[0]


def delete_object(image, replica: ImageBackend) -> bool:
    backend = replica.backend
    root = (backend.config or {}).get("root") or current_app.config["STORAGE_DIR"]
    result = {
        "path": replica.object_key,
        "size": replica.size,
        "etag": replica.etag,
    }
    results = get_hook_manager().call(
        "upimg_delete",
        include=[backend.hook_name],
        sha=image.sha,
        upload_path="",
        filename=image.filename,
        basedir=root,
        save_result=result,
    )
    return bool(results and results[0].get("code") == 0)


def local_path(replica: ImageBackend) -> Path | None:
    if replica.backend.hook_name != "up2local":
        return None
    root = (replica.backend.config or {}).get("root") or current_app.config[
        "STORAGE_DIR"
    ]
    path = Path(root) / replica.object_key
    return path if path.is_file() else None


def replicas_for(image) -> list[ImageBackend]:
    """Replicas in read order (backend priority, then id)."""
    return list(
        ImageBackend.select(ImageBackend, StorageBackend)
        .join(StorageBackend)
        .where(
            (ImageBackend.image == image)
            & (ImageBackend.state == "ok")
            & (StorageBackend.enabled == True)  # noqa: E712
        )
        .order_by(StorageBackend.priority, ImageBackend.id)
    )
