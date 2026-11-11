# -*- coding: utf-8 -*-
"""Storage backend resolution and driver invocation.

Priority is static configuration, never a runtime race: reads walk the
replica list from the highest priority backend downwards and fall back on
failure. This keeps behaviour predictable and avoids probe traffic.

Writes are two-tier: the highest priority backend is written synchronously (the
upload fails if it fails), the remaining enabled backends get their copy from a
small background pool so a slow or broken secondary never blocks the request.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path

from flask import Flask, current_app
from peewee import IntegrityError

from ..basis.errors import ApiError, ErrorCode
from ..models import Image, ImageBackend, StorageBackend, UserBackend
from ..models.base import now
from ..models.image import STATUS_ENABLED, is_expired
from ..models.storage import (
    SCOPE_SYSTEM,
    SCOPE_USER,
    STATE_FAILED,
    STATE_OK,
    STATE_STORING,
    SYSTEM_SCOPES,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
)
from . import ext
from .hook import get_hook_manager
from .settings import get_setting, set_setting

logger = logging.getLogger(__name__)

DEFAULT_BACKEND_NAME = "local"
#: Driver that keeps objects on the local filesystem: ``/raw`` streams the file
#: itself, so it needs no read address of its own.
LOCAL_DRIVER = "up2local"
#: Fallback priority; smaller wins, uploads go to the smallest enabled one.
DEFAULT_PRIORITY = 100
#: Priority step for a backend created automatically from a storage hook.
PRIORITY_STEP = 10
#: Lifetime of a temporary read address handed out by ``upimg_url``.
READ_URL_EXPIRES = 300
#: Two workers is enough: replicas are per-upload sequential and usually rare.
_REPLICA_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sapic-replica")
_PENDING_REPLICAS: set[Future] = set()


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
            scope=SCOPE_SYSTEM,
            visibility=VISIBILITY_PUBLIC,
            priority=DEFAULT_PRIORITY,
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


def private_readable(hook_name: str) -> bool:
    """Whether a backend of ``hook_name`` can serve objects without a public URL.

    Local objects are streamed by ``/raw`` from disk; remote ones need the driver
    to hand out a temporary read address (``upimg_url``). Anything else can only
    be used as a public link, so it is refused as a ``private`` backend up front
    instead of failing on every read.
    """
    if hook_name == LOCAL_DRIVER:
        return True
    hook = get_hook_manager().get(hook_name)
    return bool(hook is not None and ext.supports_private_read(hook.module))


def clean_visibility(value) -> str:
    """Normalise a backend ``visibility``; unknown values are a client error."""
    text = str(value or "").strip().lower()
    if not text:
        return VISIBILITY_PUBLIC
    if text not in (VISIBILITY_PUBLIC, VISIBILITY_PRIVATE):
        raise ApiError("invalid visibility", ErrorCode.PARAM_ERROR)
    return text


def _assert_private_readable(hook_name: str, visibility: str) -> None:
    """Refuse ``private`` for drivers that cannot sign a read request."""
    if visibility == VISIBILITY_PRIVATE and not private_readable(hook_name):
        raise ApiError(
            "driver cannot read private objects: missing %s"
            % ext.DRIVER_READ_FUNC,
            ErrorCode.PARAM_ERROR,
        )


def public_src(replica: ImageBackend) -> str | None:
    """Direct link of one replica, only when its backend is world-readable.

    A ``private`` backend stores the same URL, but the bucket rejects anonymous
    requests, so returning it would hand the browser a 403.
    """
    backend = replica.backend
    if (backend.visibility or VISIBILITY_PRIVATE) != VISIBILITY_PUBLIC:
        return None
    return replica.url or None


def thumb_suffix(backend) -> str:
    """Image-processing suffix the backend declares (``?imageView2/2/w/400``).

    The syntax belongs to the bucket or its CDN, so it is configured per backend
    and is only ever appended to a direct link. Whitespace and quotes are
    rejected: the value ends up inside an ``<img src>`` attribute, and a broken
    suffix would silently turn every thumbnail into a 404.
    """
    config = (
        backend.get("config")
        if isinstance(backend, dict)
        else getattr(backend, "config", None)
    ) or {}
    text = str(config.get("thumb_suffix") or "").strip()
    if not text:
        return ""
    if any(char.isspace() for char in text) or any(
        char in text for char in "<>\"'"
    ):
        logger.warning("ignoring invalid thumb_suffix: %r", text)
        return ""
    #: Qiniu/OSS start with ``?``, Upyun with ``!``; everything else is treated
    #: as a query string so a bare ``x-oss-process=...`` also works.
    if not text.startswith(("?", "!", "/")):
        text = "?" + text
    return text


def object_url(replica: ImageBackend, expires: int = READ_URL_EXPIRES) -> dict | None:
    """Ask the driver for a temporary read address of one replica.

    Used by ``/raw`` for ``private`` backends: the driver signs the request (or
    returns the headers it needs, as Upyun does) and sapic relays the body, so
    the bucket stays closed and the address never reaches the browser. Returns
    ``{"url": ..., "headers": {...}}`` or ``None`` when the driver refuses.
    """
    backend = replica.backend
    image = replica.image
    results = get_hook_manager().call(
        ext.DRIVER_READ_FUNC,
        include=[backend.hook_name],
        sha=image.sha if image is not None else "",
        filename=image.filename if image is not None else "",
        save_result={
            "path": replica.object_key,
            "size": replica.size,
            "etag": replica.etag,
        },
        backend=driver_backend(_as_dict(backend)),
        expires=expires,
    )
    if not results:
        return None
    result = results[0] or {}
    url = str(result.get("url") or "").strip()
    if result.get("code") != 0 or not url:
        logger.warning(
            "upimg_url of %s failed: %s",
            backend.hook_name,
            str(result.get("message") or result.get("msg") or "unknown error")[:200],
        )
        return None
    headers = result.get("headers")
    return {"url": url, "headers": dict(headers) if isinstance(headers, dict) else {}}


def upload_drivers() -> list[dict]:
    """Enabled hooks that can actually store objects, with their config fields."""
    manager = get_hook_manager()
    drivers = []
    for manifest in manager.manifests():
        if not manifest.get("enabled"):
            continue
        hook = manager.get(manifest["name"])
        #: 契约判断收敛在 libs.ext：声明 upload 但没实现 upimg_save 的插件
        #: 不能出现在后端下拉里，否则上传时才发现失败。
        if hook is None or not ext.is_driver(hook.module):
            continue
        drivers.append(manifest)
    return drivers


def _hook_defaults(manifest: dict) -> dict:
    """Hook-wide config values that a fresh backend row should inherit.

    The hook page no longer offers these fields for storage drivers, but the
    values saved there before that change (and by anyone editing settings by
    hand) are copied into the row so nothing has to be retyped.
    """
    saved = get_setting("hooks_config", {}) or {}
    values = saved.get(manifest["name"]) if isinstance(saved, dict) else None
    if not isinstance(values, dict):
        return {}
    keys = {field["key"] for field in manifest.get("config_schema") or []}
    return {
        key: str(value).strip()
        for key, value in values.items()
        if key in keys and str(value).strip()
    }


def _unique_backend_name(base: str) -> str:
    candidate = (base or "backend")[:64]
    index = 1
    while StorageBackend.get_or_none(StorageBackend.name == candidate):
        index += 1
        suffix = "-%d" % index
        candidate = (base or "backend")[: 64 - len(suffix)] + suffix
    return candidate


def sync_backends() -> list[str]:
    """Give every enabled storage hook a backend row.

    Enabling a hook is the one switch an operator expects to be enough, so the
    row is provisioned here instead of asking them to insert it by hand.
    Credentials stay in the hook config (``hooks_config``) and are merged per
    call by :func:`driver_backend`, so a fresh row works immediately.
    """
    #: 只看系统行：用户自定义的后端不算「这个驱动已经有默认后端」。
    rows = {
        row.hook_name: row
        for row in StorageBackend.select().where(
            StorageBackend.scope.in_(SYSTEM_SCOPES)
        )
    }
    priorities = [row.priority for row in StorageBackend.select(StorageBackend.priority)]
    priority = max(priorities or [DEFAULT_PRIORITY - PRIORITY_STEP])
    created = []
    for manifest in upload_drivers():
        name = manifest["name"]
        defaults = _hook_defaults(manifest)
        existing = rows.get(name)
        if existing is not None:
            #: 早期版本把存储凭据存在钩子配置里，这里把值搬进后端行（只搬一次）。
            if defaults and not existing.config:
                existing.config = defaults
                existing.save(only=[StorageBackend.config])
            continue
        priority += PRIORITY_STEP
        try:
            StorageBackend.create(
                name=_unique_backend_name(name),
                hook_name=name,
                config=defaults,
                scope=SCOPE_SYSTEM,
                visibility=VISIBILITY_PUBLIC,
                priority=priority,
                enabled=True,
            )
        except IntegrityError:  # pragma: no cover - concurrent boot
            continue
        created.append(name)
    return created


def list_backend_rows() -> list[StorageBackend]:
    """System backend rows in resolution order (the admin view's data source).

    User defined backends are deliberately excluded: they belong to their owner
    and will be managed by the (still to be built) user facing API.
    """
    sync_backends()
    return list(
        StorageBackend.select()
        .where(StorageBackend.scope.in_(SYSTEM_SCOPES))
        .order_by(StorageBackend.priority, StorageBackend.id)
    )


def _replica_count(row: StorageBackend) -> int:
    """Only healthy replicas hold data, so failed/storing rows do not count."""
    return (
        ImageBackend.select()
        .where(
            (ImageBackend.backend == row)
            & (ImageBackend.state == STATE_OK)  # noqa: E712
        )
        .count()
    )


def _required_missing(manifest: dict, config: dict) -> list[str]:
    """Labels of the required fields that ``config`` does not fill."""
    return [
        field.get("label") or field["key"]
        for field in manifest.get("config_schema") or []
        if field.get("required") and not config.get(field["key"])
    ]


def _assert_configured(manifest: dict, config: dict) -> None:
    missing = _required_missing(manifest, config)
    if missing:
        raise ApiError(
            "missing required config: %s" % ", ".join(missing),
            ErrorCode.PARAM_ERROR,
        )


def backend_payload(row: StorageBackend, primary_id: int | None = None) -> dict:
    """Serialize a backend row for the admin UI."""
    manifest = get_hook_manager().manifest(row.hook_name) or {}
    config = dict(hook_config(row.hook_name) or {})
    config.update(dict(row.config or {}))
    return {
        "id": row.id,
        "name": row.name,
        "hook_name": row.hook_name,
        "title": manifest.get("title") or row.hook_name,
        "priority": row.priority,
        "enabled": bool(row.enabled),
        "scope": row.scope,
        "config": dict(row.config or {}),
        #: ``public`` 直接给直链，``private`` 一律经 ``/raw`` 签名转发。
        "visibility": row.visibility or VISIBILITY_PUBLIC,
        #: 驱动能否私有读：不能时前端禁用「私有」选项，后端也会拒绝保存。
        "private_readable": private_readable(row.hook_name),
        "replicas": _replica_count(row),
        "in_use": row.id == primary_id,
        #: 驱动声明的必填项还没填时，前端标「待配置」，上传会失败。
        "configured": not _required_missing(manifest, config),
    }


def _upload_manifest(hook_name: str) -> dict:
    """Validate that ``hook_name`` may back a storage row."""
    manager = get_hook_manager()
    manifest = manager.manifest(hook_name)
    if manifest is None:
        raise ApiError("hook not found: %s" % hook_name, ErrorCode.NOT_FOUND, 404)
    hook = manager.get(hook_name)
    if hook is None or not ext.is_driver(hook.module):
        missing = ext.missing_callables(hook.module, ext.DRIVER_FUNCS) if hook else []
        raise ApiError(
            "hook is not a storage driver%s"
            % (": missing %s" % missing[0] if missing else ""),
            ErrorCode.PARAM_ERROR,
        )
    if not manifest.get("enabled"):
        raise ApiError("hook is disabled", ErrorCode.CONFLICT, 409)
    return manifest


def clean_backend_config(manifest: dict, config) -> dict:
    """Keep only the fields the driver declares, as trimmed strings."""
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ApiError("config must be a JSON object", ErrorCode.PARAM_ERROR)
    fields = {field["key"] for field in manifest.get("config_schema") or []}
    unknown = sorted(set(config) - fields)
    if unknown:
        raise ApiError(
            "unknown config key: %s" % unknown[0], ErrorCode.PARAM_ERROR
        )
    cleaned = {}
    for key, value in config.items():
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ApiError("%s must be a string" % key, ErrorCode.PARAM_ERROR)
        text = str(value).strip()
        if text:
            cleaned[key] = text
    return cleaned


def _clean_name(name) -> str:
    value = str(name or "").strip()[:64]
    if not value:
        raise ApiError("name is required", ErrorCode.PARAM_ERROR)
    return value


def _assert_name_free(name: str, row: StorageBackend | None = None) -> None:
    other = StorageBackend.get_or_none(StorageBackend.name == name)
    if other is not None and (row is None or other.id != row.id):
        raise ApiError("backend name already exists", ErrorCode.CONFLICT, 409)


def _other_enabled(row: StorageBackend) -> list[StorageBackend]:
    return [
        item
        for item in StorageBackend.select().where(
            StorageBackend.enabled == True  # noqa: E712
        )
        if item.id != row.id
    ]


def _guard_replicas(row: StorageBackend) -> None:
    """Refuse to drop the read path of existing replicas.

    Deleting (or disabling) a backend removes it from ``replicas_for``, so its
    images would lose their data until the backend comes back.
    """
    replicas = _replica_count(row)
    if replicas:
        raise ApiError(
            "backend still holds %d replicas" % replicas, ErrorCode.CONFLICT, 409
        )


def _guard_last_enabled(row: StorageBackend) -> None:
    """Keep one writable target; removing it entirely means deleting the row."""
    if row.enabled and not _other_enabled(row):
        raise ApiError(
            "at least one backend must stay enabled", ErrorCode.CONFLICT, 409
        )


def create_backend(
    name: str = "",
    hook_name: str = "",
    config=None,
    priority: int | None = None,
    enabled: bool = True,
    visibility: str = VISIBILITY_PUBLIC,
) -> StorageBackend:
    """Add one configured instance of a storage driver."""
    manifest = _upload_manifest((hook_name or "").strip())
    visibility = clean_visibility(visibility)
    _assert_private_readable(manifest["name"], visibility)
    cleaned = clean_backend_config(manifest, config)
    merged = _hook_defaults(manifest)
    merged.update(cleaned)
    _assert_configured(manifest, merged)
    if name:
        row_name = _clean_name(name)
        _assert_name_free(row_name)
    else:
        #: 未命名时按驱动名派生，同名自动加序号，避免与自动创建的那行撞名。
        row_name = _unique_backend_name(manifest["name"])
    if priority is None:
        priorities = [
            row.priority for row in StorageBackend.select(StorageBackend.priority)
        ]
        priority = max(priorities or [DEFAULT_PRIORITY - PRIORITY_STEP]) + PRIORITY_STEP
    try:
        return StorageBackend.create(
            name=row_name,
            hook_name=manifest["name"],
            config=cleaned,
            scope=SCOPE_SYSTEM,
            visibility=visibility,
            priority=int(priority),
            enabled=bool(enabled),
        )
    except IntegrityError as exc:
        raise ApiError(
            "backend name already exists", ErrorCode.CONFLICT, 409
        ) from exc


def update_backend(
    row: StorageBackend, data: dict, guard_last_enabled: bool = True
) -> StorageBackend:
    """Rename, reorder, enable/disable or reconfigure one backend.

    ``guard_last_enabled`` is turned off for user rows: a user may own a single
    backend and the system backends still guarantee a writable target.
    """
    fields = []
    if "name" in data:
        name = _clean_name(data.get("name"))
        _assert_name_free(name, row)
        row.name = name
        fields.append(StorageBackend.name)
    if "priority" in data:
        try:
            row.priority = int(data.get("priority"))
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid priority", ErrorCode.PARAM_ERROR) from exc
        fields.append(StorageBackend.priority)
    if "enabled" in data:
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            raise ApiError("enabled must be a boolean", ErrorCode.PARAM_ERROR)
        if not enabled:
            _guard_replicas(row)
            if guard_last_enabled:
                _guard_last_enabled(row)
        row.enabled = enabled
        fields.append(StorageBackend.enabled)
    if "visibility" in data:
        visibility = clean_visibility(data.get("visibility"))
        _assert_private_readable(row.hook_name, visibility)
        row.visibility = visibility
        fields.append(StorageBackend.visibility)
    if "config" in data:
        manifest = _upload_manifest(row.hook_name)
        cleaned = clean_backend_config(manifest, data.get("config"))
        merged = _hook_defaults(manifest)
        merged.update(dict(row.config or {}))
        merged.update(cleaned)
        _assert_configured(manifest, merged)
        row.config = cleaned
        fields.append(StorageBackend.config)
    if not fields:
        raise ApiError("nothing to update", ErrorCode.PARAM_ERROR)

    row.save(only=fields)
    return row


def delete_backend(row: StorageBackend) -> None:
    """Remove a backend row, refusing when it still holds replicas.

    Removing the last *system* row of a driver also switches the hook off,
    otherwise the next :func:`sync_backends` would provision it right back.
    A user row never changes the hook state: other users may rely on it.
    """
    _guard_replicas(row)
    hook_name = row.hook_name
    is_system = row.scope in SYSTEM_SCOPES
    UserBackend.delete().where(UserBackend.backend == row).execute()
    row.delete_instance()

    if not is_system:
        return

    remaining = StorageBackend.get_or_none(
        (StorageBackend.hook_name == hook_name)
        & StorageBackend.scope.in_(SYSTEM_SCOPES)
    )
    if remaining is None:
        states = dict(get_setting("hooks_state", {}) or {})
        states[hook_name] = False
        set_setting("hooks_state", states)
        get_hook_manager().reload()


def primary_backend_id() -> int | None:
    """The system backend an upload would land on right now (admin view)."""
    drivers = {manifest["name"] for manifest in upload_drivers()}
    for row in (
        StorageBackend.select()
        .where(
            (StorageBackend.enabled == True)  # noqa: E712
            & StorageBackend.scope.in_(SYSTEM_SCOPES)
        )
        .order_by(StorageBackend.priority, StorageBackend.id)
    ):
        if row.hook_name in drivers:
            return row.id
    return None


def list_backends(user=None) -> list[dict]:
    """Backends available to ``user`` ordered by effective priority."""
    sync_backends()
    #: 钩子被禁用后驱动不再被调用，这类后端行不能作为写入目标。
    drivers = {manifest["name"] for manifest in upload_drivers()}
    rows = [
        row
        for row in StorageBackend.select()
        .where(StorageBackend.enabled == True)  # noqa: E712
        .order_by(StorageBackend.priority, StorageBackend.id)
        if row.hook_name in drivers
    ]

    grants = {}
    if user is not None:
        grants = {
            grant.backend_id: grant
            for grant in UserBackend.select().where(UserBackend.user == user)
        }
    #: 用户自定义后端是预留能力：站点开关没打开时，即使库里有行也不参与上传。
    allow_user = bool(get_setting("allow_user_backends"))

    items = []
    for row in rows:
        if row.scope == SCOPE_USER:
            if not allow_user or user is None or row.owner_id != user.id:
                continue
        elif row.scope not in SYSTEM_SCOPES:
            continue
        elif user is not None and grants:
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


#: 用户端回显时替换密码字段的占位串；提交时原样带回表示「不修改」。
SECRET_MASK = "******"
#: 用户新建后端的默认优先级：排在系统默认（100）之前，建好即生效。
USER_BACKEND_PRIORITY = 50


def user_backends_allowed() -> bool:
    return bool(get_setting("allow_user_backends"))


def user_backend_limit() -> int:
    """Per-user backend cap, ``0`` meaning unlimited."""
    try:
        return max(0, int(get_setting("user_backend_limit") or 0))
    except (TypeError, ValueError):
        return 0


def list_user_backend_rows(user) -> list[StorageBackend]:
    """Backends owned by ``user`` in their own priority order."""
    return list(
        StorageBackend.select()
        .where((StorageBackend.scope == SCOPE_USER) & (StorageBackend.owner == user))
        .order_by(StorageBackend.priority, StorageBackend.id)
    )


def mask_backend_config(manifest: dict, config: dict) -> dict:
    masked = dict(config or {})
    for field in manifest.get("config_schema") or []:
        key = field["key"]
        if field.get("type") == "password" and masked.get(key):
            masked[key] = SECRET_MASK
    return masked


def _restore_masked_fields(manifest: dict, incoming: dict, current: dict) -> dict:
    """Treat the mask sentinel as "keep the stored secret"."""
    for field in manifest.get("config_schema") or []:
        key = field["key"]
        if field.get("type") != "password" or incoming.get(key) != SECRET_MASK:
            continue
        if current.get(key):
            incoming[key] = current[key]
        else:
            incoming.pop(key, None)
    return incoming


def user_backend_payload(row: StorageBackend, primary_id: int | None = None) -> dict:
    """Serialize an own backend for its owner; secrets never leave the server."""
    manifest = get_hook_manager().manifest(row.hook_name) or {}
    payload = backend_payload(row, primary_id)
    payload["config"] = mask_backend_config(manifest, row.config)
    return payload


def create_user_backend(
    user,
    name: str = "",
    hook_name: str = "",
    config=None,
    priority: int | None = None,
    enabled: bool = True,
    visibility: str = VISIBILITY_PUBLIC,
) -> StorageBackend:
    """Add a backend owned by ``user`` so their uploads can use their storage."""
    if not user_backends_allowed():
        raise ApiError("user backends are disabled", ErrorCode.FORBIDDEN, 403)

    manifest = _upload_manifest((hook_name or "").strip())
    visibility = clean_visibility(visibility)
    _assert_private_readable(manifest["name"], visibility)
    cleaned = clean_backend_config(manifest, config)
    #: 用户必须自己填齐必填项，不会回落到管理员在钩子页留下的默认凭据。
    _assert_configured(manifest, cleaned)
    if name:
        row_name = _clean_name(name)
        _assert_name_free(row_name)
    else:
        row_name = _unique_backend_name("%s-%s" % (user.username, manifest["name"]))

    limit = user_backend_limit()
    owned = StorageBackend.select().where(
        (StorageBackend.scope == SCOPE_USER) & (StorageBackend.owner == user)
    )
    if limit and owned.count() >= limit:
        raise ApiError(
            "at most %d storage backends are allowed" % limit,
            ErrorCode.CONFLICT,
            409,
        )

    if priority is None:
        priority = USER_BACKEND_PRIORITY
    try:
        return StorageBackend.create(
            name=row_name,
            hook_name=manifest["name"],
            config=cleaned,
            scope=SCOPE_USER,
            owner=user,
            visibility=visibility,
            priority=int(priority),
            enabled=bool(enabled),
        )
    except IntegrityError as exc:
        raise ApiError(
            "backend name already exists", ErrorCode.CONFLICT, 409
        ) from exc


def update_user_backend(row: StorageBackend, data: dict) -> StorageBackend:
    """Owner-side update: same validation, but no global guards and masked secrets."""
    manifest = _upload_manifest(row.hook_name)
    payload = dict(data)
    if "config" in payload:
        cleaned = clean_backend_config(manifest, payload.get("config"))
        cleaned = _restore_masked_fields(manifest, cleaned, dict(row.config or {}))
        merged = dict(row.config or {})
        merged.update(cleaned)
        _assert_configured(manifest, merged)
        payload["config"] = cleaned
    return update_backend(row, payload, guard_last_enabled=False)


def hook_config(hook_name: str) -> dict:
    """Hook-wide defaults managed on the hooks page (site settings)."""
    saved = get_setting("hooks_config", {}) or {}
    if not isinstance(saved, dict):
        return {}
    data = saved.get(hook_name) or {}
    return dict(data) if isinstance(data, dict) else {}


def driver_backend(backend: dict) -> dict:
    """Merge hook defaults, per-backend config and runtime-only options."""
    data = dict(backend)
    hook_name = data.get("hook_name") or ""
    config = hook_config(hook_name)
    #: A configured backend row always wins over the hook-wide defaults.
    config.update(dict(data.get("config") or {}))
    if hook_name == LOCAL_DRIVER and not config.get("root"):
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
        return {"code": 1, "message": "no storage driver available"}
    return results[0]


def delete_object(image, replica: ImageBackend) -> bool:
    backend = replica.backend
    runtime = driver_backend(_as_dict(backend))
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
        basedir=(runtime.get("config") or {}).get("root", ""),
        save_result=result,
        backend=runtime,
    )
    deleted = bool(results and results[0].get("code") == 0)
    if not deleted:
        #: 驱动失败时调用方只丢掉返回值，于是「删除成功」的界面配上残留对象；
        #: 至少留一条日志，能看出是 key 不对、凭证过期还是钩子没启用。
        detail = results[0].get("message") if results else "no storage driver"
        logger.warning(
            "delete %s on backend %s failed: %s",
            replica.object_key,
            backend.name,
            detail,
        )
    return deleted


def queue_replicas(
    app: Flask,
    image_id: int,
    backends: list[dict],
    sha: str,
    object_name: str,
    stream: bytes,
    upload_path: str,
) -> None:
    """Copy the object to the remaining backends without blocking the upload."""
    if not backends:
        return
    payload = {
        "image_id": image_id,
        "backends": backends,
        "sha": sha,
        "object_name": object_name,
        "stream": stream,
        "upload_path": upload_path,
    }
    future = _REPLICA_POOL.submit(_write_replicas, app, payload)
    _PENDING_REPLICAS.add(future)
    future.add_done_callback(_PENDING_REPLICAS.discard)


def flush_replicas(timeout: float = 30.0) -> None:
    """Block until queued replica jobs finish (tests and graceful shutdown)."""
    pending = list(_PENDING_REPLICAS)
    if pending:
        wait(pending, timeout=timeout)


def _write_replicas(app: Flask, payload: dict) -> None:
    with app.app_context():
        image = Image.get_or_none(Image.id == payload["image_id"])
        #: 图片可能已经被删除或已过期，那就没有必要再往别的后端写。
        if image is None or image.status != STATUS_ENABLED or is_expired(image):
            return
        for backend in payload["backends"]:
            try:
                _write_replica(image, backend, payload)
            except Exception:  # pragma: no cover - keep the loop alive
                logger.exception("Replica to backend %s failed", backend.get("name"))


def _write_replica(image: Image, backend: dict, payload: dict) -> None:
    row = ImageBackend.get_or_none(
        (ImageBackend.image == image) & (ImageBackend.backend == backend["id"])
    )
    if row is None:
        try:
            row = ImageBackend.create(
                image=image,
                backend=backend["id"],
                state=STATE_STORING,
                created_at=now(),
            )
        except IntegrityError:  # pragma: no cover - concurrent enqueue
            row = ImageBackend.get_or_none(
                (ImageBackend.image == image)
                & (ImageBackend.backend == backend["id"])
            )
            if row is None:
                return
    if row.state == STATE_OK:
        return

    try:
        result = save_object(
            backend,
            payload["sha"],
            payload["object_name"],
            payload["stream"],
            payload["upload_path"],
        )
    except Exception as exc:  # pragma: no cover - driver specific
        logger.exception("Replica save raised on backend %s", backend.get("name"))
        result = {"code": 1, "message": str(exc)}

    if result.get("code") == 0:
        row.object_key = result.get("path") or ""
        row.url = result.get("src")
        row.size = result.get("size") or 0
        row.etag = result.get("etag")
        row.state = STATE_OK
        row.last_error = None
    else:
        row.state = STATE_FAILED
        row.last_error = str(
            result.get("message") or result.get("msg") or "unknown error"
        )[:255]
    row.checked_at = now()
    row.save()


def local_path(replica: ImageBackend) -> Path | None:
    if replica.backend.hook_name != LOCAL_DRIVER:
        return None
    config = driver_backend(_as_dict(replica.backend)).get("config") or {}
    path = Path(config["root"]) / replica.object_key
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
