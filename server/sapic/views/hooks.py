# -*- coding: utf-8 -*-
"""Hook UI endpoints: catalogue, manifests, slots, actions and datasets.

These endpoints turn a hook's declarative manifest into the JSON the front-end
renderer consumes. Every response is capped by ``sapic.libs.ui`` on the way out,
so a malformed manifest can never reach the browser as executable content.
"""

from __future__ import annotations

import json

from flask import Blueprint, abort, request

from ..libs import ui
from ..libs.auth import admin_required, current_user, login_required
from ..libs.hook import get_hook_manager
from ..utils.web import ok

bp = Blueprint("hooks", __name__)


def _manager():
    return get_hook_manager()


def _is_admin():
    user = current_user()
    return bool(user and user.is_admin)


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
    payload = request.get_json(silent=True) or {}
    result = manager.action(name, action, payload=payload, context=None)
    if result is None:
        abort(404)
    return ok(result)


@bp.get("/hooks/<name>/data/<source>")
@login_required
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
