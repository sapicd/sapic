# -*- coding: utf-8 -*-
"""Declarative UI vocabulary for hook front-ends.

Hooks describe their UI as JSON node trees; the frontend implements one
renderer. Every node type, key and value is whitelisted here so a hook can
never inject HTML or script: unknown types are dropped, unknown keys are
stripped, ``href`` values are scheme-checked, and ``action`` names must be
declared by the hook manifest. See :mod:`sapic.libs.hook` for how the tree is
produced and consumed.
"""

from __future__ import annotations

import re

UI_VERSION = 1

MAX_TEXT = 2000
MAX_CHILDREN = 64
MAX_ROWS = 500
MAX_DEPTH = 8

#: Named slots a hook may declare. Anything else is rejected by the server.
SLOTS = {
    "nav",
    "login.after_form",
    "profile",
    "user.setting",
    "admin.site_setting",
    "admin.hook_setting",
    "image.detail",
    "upload.after",
}

#: Only declarative rendering is supported. HTML/ESM modes are rejected and
#: downgraded to ``declarative`` so plugins cannot execute arbitrary front-end
#: code in the host application.
SLOT_MODES = {"declarative"}

#: Allowed icon prefixes. Hooks reference nominal icons; the frontend maps them
#: onto its own component library.
ICON_RE = re.compile(r"^(?:builtin|brand):[a-z0-9_\-]+$", re.IGNORECASE)

#: Allowed node types and the keys each may carry.
_TYPE_KEYS = {
    # structural
    "fieldset": {"type", "legend", "status", "children", "when", "icon"},
    "group": {"type", "title", "children", "when", "icon"},
    "row": {"type", "gap", "children", "when"},
    "col": {"type", "span", "children", "when"},
    "tabs": {"type", "children", "when"},
    "collapse": {"type", "children", "when"},
    "list": {"type", "empty", "children", "when"},
    "list_item": {"type", "title", "description", "row_actions", "when"},
    # display
    "text": {"type", "text", "muted", "when", "icon"},
    "alert": {"type", "level", "text", "when"},
    "badge": {"type", "level", "text", "when"},
    "image": {"type", "src", "alt", "fit", "width", "height", "when"},
    "code": {"type", "text", "when"},
    "divider": {"type", "label", "when"},
    # input
    "input": {"type", "key", "label", "default", "required", "help", "readonly",
              "disabled", "placeholder", "maxlength", "prefix", "suffix", "when"},
    "number": {"type", "key", "label", "default", "required", "help", "disabled",
               "min", "max", "step", "when"},
    "password": {"type", "key", "label", "default", "required", "help",
                 "disabled", "placeholder", "when"},
    "textarea": {"type", "key", "label", "default", "required", "help",
                  "disabled", "placeholder", "maxlength", "rows", "mono", "when"},
    "switch": {"type", "key", "label", "default", "required", "disabled",
               "help", "active_text", "inactive_text", "when"},
    "select": {"type", "key", "label", "default", "required", "help",
               "disabled", "placeholder", "multiple", "options", "source", "when"},
    "radio": {"type", "key", "label", "default", "required", "disabled",
              "options", "when"},
    # interactive
    "button": {"type", "text", "action", "with_form", "confirm", "refresh",
               "icon", "variant", "size", "disabled", "disabled_reason", "when"},
    "link": {"type", "text", "href", "target", "icon", "when"},
    "dropdown": {"type", "text", "icon", "children", "when"},
    "dropdown_item": {"type", "text", "action", "with_form", "confirm",
                      "danger", "disabled", "when"},
}

_CONTAINER_TYPES = {
    "fieldset", "group", "row", "col", "tabs", "collapse", "list", "dropdown",
}
_LEVELS = {"info", "notice", "success", "warn", "error"}
_VARIANTS = {"default", "primary", "success", "warn", "danger"}
_SIZES = {"small", "normal", "large"}
_LINK_SCHEMES = {"http", "https"}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

_STRING_KEYS = {
    "text", "label", "legend", "status", "title", "description", "help",
    "placeholder", "alt", "fit", "width", "height", "active_text",
    "inactive_text", "empty", "disabled_reason", "prefix", "suffix",
}
_NUM_KEYS = {"maxlength", "min", "max", "step", "rows", "gap", "span"}
_BOOL_KEYS = {
    "required", "readonly", "disabled", "multiple", "mono", "confirm",
    "with_form", "refresh", "danger", "muted", "target",
}


def _text(value, limit=MAX_TEXT):
    if value is None:
        return None
    text = str(value)
    if limit and len(text) > limit:
        text = text[:limit]
    return text


def _expand(text, context):
    if not context:
        return text

    def _sub(match):
        key = match.group(1)
        return str(context[key]) if key in context else match.group(0)

    return _PLACEHOLDER.sub(_sub, text)


def _clean_href(href, context):
    if not isinstance(href, str):
        return None
    if href.startswith("//"):
        #: protocol-relative URLs are treated as unsafe
        return None
    if not href.startswith("/"):
        scheme = href.split(":", 1)[0].lower()
        if scheme not in _LINK_SCHEMES:
            return None
    return _expand(href, context)


def _eval_when(when, values):
    if not isinstance(when, dict):
        return True
    field = when.get("field")
    op = when.get("op")
    expected = when.get("value")
    actual = values.get(field) if isinstance(values, dict) else None
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not actual
    return True


def _clean_options(options):
    if not isinstance(options, list):
        return []
    result = []
    seen = set()
    for option in options[:MAX_CHILDREN]:
        if not isinstance(option, dict):
            continue
        value = option.get("value")
        label = option.get("label", option.get("value"))
        if value is None or label is None:
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append({"value": value, "label": _text(label)})
    return result


def _clean_row_actions(actions, declared):
    if not isinstance(actions, list):
        return []
    result = []
    for action in actions[:MAX_CHILDREN]:
        if not isinstance(action, dict):
            continue
        name = action.get("action")
        if not name or (declared is not None and name not in declared):
            continue
        item = {"action": _text(name, 64), "text": _text(action.get("text") or name)}
        if action.get("confirm"):
            item["confirm"] = True
        if action.get("danger"):
            item["danger"] = True
        result.append(item)
    return result


def clean_node(node, actions=None, values=None, context=None, depth=0):
    if not isinstance(node, dict):
        return None
    node = dict(node)
    ntype = node.get("type")
    if ntype not in _TYPE_KEYS:
        return None

    if node.get("when") is not None and not _eval_when(node["when"], values or {}):
        return None

    allowed = _TYPE_KEYS[ntype]
    out = {"type": ntype}

    for key in allowed:
        if key not in node:
            continue
        value = node[key]
        if key in _STRING_KEYS:
            value = _text(value)
            if value is None:
                continue
        elif key in _NUM_KEYS:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        elif key in _BOOL_KEYS:
            value = bool(value)
            if not value:
                continue
        else:
            #: handled explicitly below
            continue
        out[key] = value

    if "level" in node and "level" in allowed:
        out["level"] = node["level"] if node["level"] in _LEVELS else "info"
    if "variant" in node and "variant" in allowed:
        out["variant"] = node["variant"] if node["variant"] in _VARIANTS else "default"
    if "size" in node and "size" in allowed:
        out["size"] = node["size"] if node["size"] in _SIZES else "normal"
    if "icon" in node and "icon" in allowed and ICON_RE.match(str(node["icon"])):
        out["icon"] = str(node["icon"])
    if "key" in node and "key" in allowed and node["key"]:
        out["key"] = _text(node["key"], 64)
    if "default" in node and "default" in allowed:
        value = node["default"]
        if isinstance(value, str):
            value = _text(value)
        out["default"] = value
    if "options" in node and "options" in allowed:
        out["options"] = _clean_options(node["options"])
    if "row_actions" in node and "row_actions" in allowed:
        out["row_actions"] = _clean_row_actions(node["row_actions"], actions)

    if ntype == "link":
        href = _clean_href(node.get("href"), context)
        if href is None:
            return None
        out["href"] = href
        if out.get("target") not in ("blank", "self"):
            out["target"] = "self"

    if ntype == "button":
        action = node.get("action")
        refresh = bool(node.get("refresh"))
        if action:
            if actions is not None and action not in actions:
                return None
            out["action"] = _text(action, 64)
        elif not refresh:
            return None
        if refresh:
            out["refresh"] = True

    if ntype == "dropdown_item":
        action = node.get("action")
        if not action or (actions is not None and action not in actions):
            return None
        out["action"] = _text(action, 64)

    if ntype in _CONTAINER_TYPES and "children" in node:
        children = node["children"]
        if not isinstance(children, list):
            children = []
        cleaned = []
        for child in children[:MAX_CHILDREN]:
            if depth + 1 <= MAX_DEPTH:
                sub = clean_node(child, actions, values, context, depth + 1)
                if sub is not None:
                    cleaned.append(sub)
        out["children"] = cleaned

    return out


def clean_tree(nodes, actions=None, values=None, context=None):
    if nodes is None:
        return []
    if isinstance(nodes, dict):
        nodes = [nodes]
    if not isinstance(nodes, list):
        return []
    result = []
    for node in nodes[:MAX_CHILDREN]:
        cleaned = clean_node(node, actions, values, context, depth=0)
        if cleaned is not None:
            result.append(cleaned)
    return result


def clean_fields(fields):
    if not isinstance(fields, list):
        return []
    result = []
    seen = set()
    for field in fields[:MAX_CHILDREN]:
        if not isinstance(field, dict):
            continue
        ftype = field.get("type")
        if ftype not in ("input", "number", "password", "textarea",
                         "switch", "select", "radio"):
            continue
        key = field.get("key")
        if not key or key in seen:
            continue
        seen.add(key)
        item = {"type": ftype, "key": _text(key, 64),
                "label": _text(field.get("label") or key)}
        if field.get("default") is not None:
            default = field["default"]
            #: 数字控件需要真数字，字符串会让前端的 el-input-number 失配。
            if ftype == "number" and isinstance(default, (int, float)):
                item["default"] = int(default)
            else:
                item["default"] = _text(default, MAX_TEXT)
        if field.get("required"):
            item["required"] = True
        if field.get("help"):
            item["help"] = _text(field["help"])
        if field.get("placeholder"):
            item["placeholder"] = _text(field["placeholder"])
        if field.get("format"):
            item["format"] = _text(field["format"], 32)
        if ftype in ("select", "radio") and field.get("options"):
            item["options"] = _clean_options(field["options"])
        if ftype == "select" and field.get("multiple"):
            item["multiple"] = True
        if field.get("source"):
            item["source"] = _text(field["source"], 64)
        if ftype == "number":
            for bound in ("min", "max", "step"):
                try:
                    item[bound] = int(field[bound])
                except (KeyError, TypeError, ValueError):
                    continue
        result.append(item)
    return result


def clean_actions(actions):
    if not isinstance(actions, list):
        return []
    result = []
    seen = set()
    for action in actions[:MAX_CHILDREN]:
        if not isinstance(action, dict):
            continue
        name = action.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        item = {"name": _text(name, 64),
                "label": _text(action.get("label") or name)}
        if action.get("scope"):
            item["scope"] = _text(action["scope"], 32)
        if action.get("with_form"):
            item["with_form"] = True
        if action.get("confirm"):
            item["confirm"] = True
        result.append(item)
    return result


def clean_sources(sources):
    if not isinstance(sources, list):
        return []
    result = []
    seen = set()
    for source in sources[:MAX_CHILDREN]:
        if not isinstance(source, dict):
            continue
        name = source.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        result.append({"name": _text(name, 64),
                      "label": _text(source.get("label") or name)})
    return result


def clean_slots(slots):
    if not isinstance(slots, list):
        return []
    result = []
    seen = set()
    for slot in slots[:MAX_CHILDREN]:
        if not isinstance(slot, dict):
            continue
        name = slot.get("name")
        if not name or name not in SLOTS or name in seen:
            continue
        seen.add(name)
        result.append({"name": name, "mode": "declarative"})
    return result


def clean_result(result):
    if not isinstance(result, dict):
        result = {}
    try:
        code = int(result.get("code", 0))
    except (TypeError, ValueError):
        code = 0
    out = {"code": code}
    message = result.get("message") or result.get("msg")
    if message:
        out["message"] = _text(message, MAX_TEXT)
    toast = result.get("toast")
    if isinstance(toast, dict) and toast.get("text"):
        level = toast.get("level")
        if level in _LEVELS:
            out["toast"] = {"level": level, "text": _text(toast["text"], MAX_TEXT)}
    if result.get("refresh"):
        out["refresh"] = True
    return out


def clean_dataset(raw):
    if not isinstance(raw, dict):
        return {"items": [], "total": 0}
    rows = raw.get("items")
    if not isinstance(rows, (list, tuple)):
        rows = []
    items = []
    for row in list(rows)[:MAX_ROWS]:
        if not isinstance(row, dict):
            continue
        item = {}
        for key, value in row.items():
            name = _text(key, 64)
            if not name:
                continue
            if isinstance(value, str):
                item[name] = _text(value)
            elif isinstance(value, (int, float, bool)) or value is None:
                item[name] = value
        items.append(item)
    total = raw.get("total")
    return {"items": items, "total": total if isinstance(total, int) else len(items)}
