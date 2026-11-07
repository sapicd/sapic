# -*- coding: utf-8 -*-
"""Hook UI endpoints: catalogue, manifests, slots, actions and datasets.

These endpoints turn a hook's declarative manifest into the JSON the front-end
renderer consumes. Every response is capped by ``sapic.libs.ui`` on the way out,
so a malformed manifest can never reach the browser as executable content.
"""

from __future__ import annotations

import json
import re

from flask import Blueprint, abort, request

from ..basis.common import as_bool
from ..basis.errors import ApiError, ErrorCode
from ..libs import hook_pkg, ui
from ..libs.auth import admin_required, current_user, login_required
from ..libs.hook import MAX_IMPORTED, get_hook_manager
from ..libs.settings import get_setting, set_setting
from ..utils.common import slice_page
from ..utils.web import ok, page_params

bp = Blueprint("hooks", __name__)


def _manager():
    return get_hook_manager()


def _is_admin():
    user = current_user()
    return bool(user and user.is_admin)


MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _dict_setting(key: str) -> dict:
    data = get_setting(key, {}) or {}
    return dict(data) if isinstance(data, dict) else {}


def _list_setting(key: str) -> list[str]:
    data = get_setting(key, []) or []
    if isinstance(data, str):
        data = [data]
    if not isinstance(data, (list, tuple)):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def _clean_config_value(key: str, field: dict, value):
    """Coerce one config value to the type declared by the manifest."""
    kind = field.get("type")
    if kind == "switch":
        if not isinstance(value, bool):
            raise ApiError("%s must be a boolean" % key, ErrorCode.PARAM_ERROR)
        return value
    if kind == "number":
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ApiError(
                "%s must be an integer" % key, ErrorCode.PARAM_ERROR
            ) from exc
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ApiError("%s must be a string" % key, ErrorCode.PARAM_ERROR)
    return value.strip()


@bp.get("/hooks")
@login_required
def catalogue():
    manifests = _manager().manifests()
    slots = set()
    for manifest in manifests:
        for slot in manifest.get("slots", []):
            slots.add(slot["name"])
    visible = [s for s in sorted(slots) if _is_admin() or not s.startswith("admin.")]
    return ok({"items": manifests, "slots": visible})


@bp.get("/hooks/manifests")
@admin_required
def manifests():
    return ok({"items": _manager().manifests()})


@bp.post("/hooks/reload")
@admin_required
def reload_hooks():
    """Rescan the hook directories so file edits take effect immediately."""
    _manager().reload()
    return ok({"items": _manager().manifests()})


@bp.patch("/hooks/<name>")
@admin_required
def update_hook(name):
    """Enable or disable one hook; the choice is persisted in the settings."""
    if _manager().get(name) is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        raise ApiError("enabled must be a boolean", ErrorCode.PARAM_ERROR)

    states = _dict_setting("hooks_state")
    states[name] = enabled
    set_setting("hooks_state", states)
    _manager().reload()

    hook = _manager().get(name)
    if hook is None:
        abort(404)
    return ok({"name": name, "enabled": hook.enabled})


def _register_imported(module: str) -> dict:
    """Add ``module`` to the loaded set and return its manifest.

    Shared by the import dialog and the market installer; a module that turns
    out not to be a hook is rolled back so it never stays in the list.
    """
    if _manager().get(module) is not None:
        raise ApiError("hook already loaded", ErrorCode.CONFLICT, 409)

    imported = _list_setting("hooks_imported")
    #: 管理器只认前 MAX_IMPORTED 个，多写的会被静默丢弃，这里提前拦住。
    if module not in imported and len(imported) >= MAX_IMPORTED:
        raise ApiError(
            "too many imported hooks (max %d)" % MAX_IMPORTED,
            ErrorCode.PARAM_ERROR,
        )
    imported.append(module)
    set_setting("hooks_imported", imported)
    _manager().reload()

    manifest = _manager().manifest(module)
    if manifest is None:
        set_setting(
            "hooks_imported", [item for item in imported if item != module]
        )
        _manager().reload()
        raise ApiError(
            "module is not a valid hook (needs __version__ and __author__)",
            ErrorCode.PARAM_ERROR,
        )
    return manifest


@bp.post("/hooks/import")
@admin_required
def import_hook():
    """Register an importable module as a third-party hook.

    The module must already be installed in the interpreter that runs sapic;
    this endpoint only adds it to the loaded set (and persists that choice).
    """
    data = request.get_json(silent=True) or {}
    module = str(data.get("module") or "").strip()
    if not MODULE_RE.match(module):
        raise ApiError("invalid module name", ErrorCode.PARAM_ERROR)
    return ok({"item": _register_imported(module)})


@bp.delete("/hooks/import/<module>")
@admin_required
def remove_hook(module: str):
    """Stop loading an imported hook.

    ``?purge=1`` also deletes the package files from ``HOOK_PKG_STORAGE_DIR``;
    without it the installed package stays usable by other deployments.
    """
    purge = as_bool(request.args.get("purge"))
    imported = _list_setting("hooks_imported")
    if module not in imported and not purge:
        abort(404)

    if module in imported:
        set_setting("hooks_imported", [item for item in imported if item != module])
    files = hook_pkg.remove_package(module) if purge else []
    _manager().reload()
    return ok({"module": module, "removed": True, "files": files})


@bp.get("/hooks/packages")
@admin_required
def packages():
    """Packages installed into the hook package directory."""
    directory = hook_pkg.package_dir()
    items = [
        {"name": name, "version": version}
        for name, version in sorted(hook_pkg.installed_versions().items())
    ]
    return ok(
        {
            "items": items,
            "storage_dir": str(directory) if directory else "",
            "configured": directory is not None,
        }
    )


@bp.post("/hooks/install")
@admin_required
def install_package():
    """``pip install`` a third-party hook package into the configured directory.

    A failing pip run is answered with ``ok: false`` and the pip log instead of
    an error envelope: the admin needs that output to fix the requirement.
    """
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ApiError("payload must be a JSON object", ErrorCode.PARAM_ERROR)

    package = str(data.get("package") or "").strip()
    index_url = str(data.get("index_url") or "").strip()
    upgrade = bool(data.get("upgrade"))
    module = str(data.get("module") or "").strip()
    if module and not MODULE_RE.match(module):
        raise ApiError("invalid module name", ErrorCode.PARAM_ERROR)

    result = hook_pkg.install(package, index_url=index_url, upgrade=upgrade)
    if not result["ok"]:
        return ok({"install": result, "manifest": None})

    _manager().reload()
    manifest = _manager().manifest(module) if module else None
    #: 包目录名与模块名相同时，扫描已自动加载；否则补一次按模块名导入。
    if module and manifest is None and _manager().get(module) is None:
        manifest = _register_imported(module)
    return ok({"install": result, "manifest": manifest})


@bp.get("/hooks/market")
@admin_required
def hook_market():
    """Official third-party hook listing, one page at a time.

    The listing is cached whole (six hours), so paging is a slice of that cache;
    the local install/loaded state is merged into the page only, which keeps the
    response small no matter how long the upstream list grows.
    """
    page, page_size = page_params(
        hook_pkg.MARKET_PAGE_SIZE, hook_pkg.MAX_MARKET_PAGE_SIZE
    )
    data = hook_pkg.market_items(refresh=as_bool(request.args.get("refresh")))
    located = slice_page(data["items"], page, page_size)

    loaded = _manager().hooks
    items = []
    for entry in located["items"]:
        hook = loaded.get(entry["module"])
        item = dict(entry)
        item["loaded"] = hook is not None
        item["enabled"] = bool(hook.enabled) if hook is not None else False
        item["installed"] = bool(item["installed_version"]) or hook is not None
        items.append(item)
    located["items"] = items

    directory = hook_pkg.package_dir()
    return ok(
        {
            **located,
            "updated_at": data["updated_at"],
            "market_url": hook_pkg.market_url(),
            "storage_dir": str(directory) if directory else "",
            "configured": directory is not None,
        }
    )


@bp.get("/hooks/config")
@admin_required
def read_config():
    """Config fields of every hook, together with the saved values."""
    saved = _dict_setting("hooks_config")
    items = []
    for manifest in _manager().manifests():
        fields = manifest["config_schema"]
        if not fields:
            continue
        values = saved.get(manifest["name"]) or {}
        if not isinstance(values, dict):
            values = {}
        items.append(
            {
                "name": manifest["name"],
                "title": manifest["title"],
                "description": manifest["description"],
                "catalog": manifest["catalog"],
                "version": manifest["version"],
                "enabled": manifest["enabled"],
                "fields": fields,
                "actions": manifest["actions"],
                "values": {
                    field["key"]: values.get(field["key"], field.get("default"))
                    for field in fields
                },
            }
        )
    return ok({"items": items})


@bp.put("/hooks/config/<name>")
@admin_required
def write_config(name):
    """Save one hook's config; only fields declared by the manifest are taken."""
    manifest = _manager().manifest(name)
    if manifest is None:
        abort(404)
    fields = {field["key"]: field for field in manifest["config_schema"]}
    if not fields:
        raise ApiError("hook has no configurable fields", ErrorCode.PARAM_ERROR)

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ApiError("config must be a JSON object", ErrorCode.PARAM_ERROR)
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise ApiError("unknown config key: %s" % unknown[0], ErrorCode.PARAM_ERROR)

    saved = _dict_setting("hooks_config")
    merged = saved.get(name) or {}
    merged = dict(merged) if isinstance(merged, dict) else {}
    for key, value in data.items():
        merged[key] = _clean_config_value(key, fields[key], value)
    saved[name] = merged
    set_setting("hooks_config", saved)
    return ok({"name": name, "values": merged})


@bp.get("/hooks/slots/<path:slot>")
def get_slot(slot):
    if slot not in ui.SLOTS:
        abort(404)
    context = None
    raw = request.args.get("context")
    if raw:
        try:
            context = json.loads(raw)
        except (ValueError, TypeError):
            abort(400)
    if slot.startswith("admin.") and not _is_admin():
        abort(403)
    blocks = _manager().slot(slot, context=context, values=None)
    return ok(
        {
            "slot": slot,
            "scope": "admin" if slot.startswith("admin.") else "public",
            "blocks": blocks,
        }
    )


@bp.post("/hooks/<name>/actions/<action>")
@login_required
def run_action(name, action):
    manager = _manager()
    hook = manager.get(name)
    if hook is None or not hook.enabled:
        abort(404)
    manifest = manager.manifest(name) or {}
    declared = {item["name"]: item for item in manifest.get("actions", [])}
    meta = declared.get(action)
    if meta is None:
        abort(404)
    #: 动作的 scope 由 manifest 声明；后台动作（探测目录、校验密钥）只给管理员。
    if meta.get("scope") == "admin" and not _is_admin():
        abort(403)
    payload = request.get_json(silent=True) or {}
    result = manager.action(name, action, payload=payload, context=None)
    if result is None:
        abort(404)
    return ok(result)


@bp.get("/hooks/<name>/data/<source>")
@admin_required
def get_data(name, source):
    manager = _manager()
    hook = manager.get(name)
    if hook is None or not hook.enabled:
        abort(404)
    manifest = manager.manifest(name) or {}
    if source not in {item["name"] for item in manifest.get("data_sources", [])}:
        abort(404)
    result = manager.data(name, source, query=request.args.to_dict(), context=None)
    return ok(result)
