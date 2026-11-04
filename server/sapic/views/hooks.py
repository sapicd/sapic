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

from ..basis.errors import ApiError, ErrorCode
from ..libs import ui
from ..libs.auth import admin_required, current_user, login_required
from ..libs.hook import get_hook_manager
from ..libs.settings import get_setting, set_setting
from ..utils.web import ok

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
    if _manager().get(module) is not None:
        raise ApiError("hook already loaded", ErrorCode.CONFLICT, 409)

    imported = _list_setting("hooks_imported")
    imported.append(module)
    set_setting("hooks_imported", imported)
    _manager().reload()

    manifest = _manager().manifest(module)
    if manifest is None:
        #: Roll back so an unloadable module does not stay in the list.
        set_setting(
            "hooks_imported", [item for item in imported if item != module]
        )
        _manager().reload()
        raise ApiError(
            "module is not a valid hook (needs __version__ and __author__)",
            ErrorCode.PARAM_ERROR,
        )
    return ok({"item": manifest})


@bp.delete("/hooks/import/<module>")
@admin_required
def remove_hook(module: str):
    """Stop loading an imported hook; the package itself is untouched."""
    imported = _list_setting("hooks_imported")
    if module not in imported:
        abort(404)
    set_setting("hooks_imported", [item for item in imported if item != module])
    _manager().reload()
    return ok({"module": module, "removed": True})


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
