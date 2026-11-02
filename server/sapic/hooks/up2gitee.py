# -*- coding: utf-8 -*-
"""up2gitee — store objects in a Gitee repository.

Driver contract (v2): ``upimg_save(filename, stream, upload_path, backend=...)``
returns ``{"code": 0, "path": <repo key>, "size": <bytes>, "etag": <blob sha>}``.
The public URL is decided by the service layer, so the driver never returns
``src``; switching backends therefore never changes external links.

The credentials come from ``backend["config"]`` (``token`` / ``repo`` /
``branch`` / ``basedir``). Gitee takes the private token as a request
parameter instead of an ``Authorization`` header.
"""

from __future__ import annotations

from base64 import b64encode
from hashlib import sha256

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None

__version__ = "0.2.0"
__author__ = "staugur"
__description__ = "将图片保存到Gitee"
__catalog__ = "upload"
__state__ = "disabled"

API = "https://gitee.com/api/v5"
TIMEOUT = 30

#: (key, node type, label, hint) shared by the manifest and the settings slot.
FIELDS = (
    ("token", "password", "私人令牌", "Gitee 私人令牌（projects 权限）"),
    ("repo", "input", "仓库名", "公开仓库，格式：用户名/仓库名"),
    ("branch", "input", "分支", "仓库分支，留空则使用仓库默认分支"),
    ("basedir", "input", "存储根目录", "图片存储到仓库的基础目录，默认是根目录"),
)
REQUIRED = ("token", "repo")


def hook_manifest():
    return {
        "title": "Gitee 版本库",
        "catalog": "upload",
        "config_schema": [
            {
                "type": kind,
                "key": key,
                "label": label,
                "placeholder": hint,
                "required": key in REQUIRED,
            }
            for key, kind, label, hint in FIELDS
        ],
        "actions": [
            {
                "name": "ping",
                "label": "检查仓库",
                "scope": "admin",
                "with_form": True,
            }
        ],
        "slots": [{"name": "admin.hook_setting"}],
    }


def slot_admin_hook_setting(context=None, **kwargs):
    backend = (context or {}).get("backend") or {}
    config = backend.get("config") or {}
    children = [
        {
            "type": kind,
            "key": key,
            "label": label,
            "help": hint,
            "default": config.get(key) or "",
            "required": key in REQUIRED,
        }
        for key, kind, label, hint in FIELDS
    ]
    children.append(
        {"type": "button", "text": "检查仓库", "action": "ping", "with_form": True}
    )
    if backend.get("in_use"):
        children.insert(
            0, {"type": "alert", "level": "success", "text": "当前正在使用"}
        )
    return [{"type": "fieldset", "legend": "Gitee 版本库", "children": children}]


def _config(backend=None) -> dict:
    return (backend or {}).get("config") or {}


def _value(values, config, key) -> str:
    value = (values or {}).get(key)
    if value in (None, ""):
        value = (config or {}).get(key)
    return str(value or "").strip()


def _key(basedir, upload_path, filename) -> str:
    parts = []
    for part in (basedir, upload_path, filename):
        text = str(part or "").strip("/")
        if text:
            parts.append(text)
    return "/".join(parts)


def _headers() -> dict:
    return {"User-Agent": "sapic-up2gitee/%s" % __version__}


def _error(response) -> str:
    try:
        message = str((response.json() or {}).get("message") or "")
    except Exception:
        message = ""
    return (message or "HTTP %s" % response.status_code).replace("\n", " ")[:200]


def _check(config: dict) -> str:
    """Return an error message when the driver cannot run."""
    if requests is None:
        return "Please install requests module"
    if not str(config.get("token") or "").strip():
        return "The gitee parameter error"
    if "/" not in str(config.get("repo") or ""):
        return "The gitee parameter error"
    return ""


def upimg_save(filename, stream, upload_path="", backend=None, **kwargs):
    config = _config(backend)
    if not filename or stream is None:
        return {"code": 1, "msg": "Parameter error"}
    error = _check(config)
    if error:
        return {"code": 1, "msg": error}

    data = stream if isinstance(stream, (bytes, bytearray)) else stream.read()
    token = str(config["token"]).strip()
    repo = str(config["repo"]).strip()
    key = _key(config.get("basedir"), upload_path, filename)
    payload = {
        "access_token": token,
        "message": "Create %s by sapic" % key,
        "content": b64encode(data).decode("utf-8"),
    }
    branch = str(config.get("branch") or "").strip()
    if branch:
        payload["branch"] = branch

    try:
        response = requests.post(
            "%s/repos/%s/contents/%s" % (API, repo, key),
            data=payload,
            headers=_headers(),
            timeout=TIMEOUT,
        )
    except Exception as exc:
        return {"code": 1, "msg": str(exc)}

    if response.status_code != 201:
        return {"code": response.status_code or 1, "msg": _error(response)}

    content = (response.json() or {}).get("content") or {}
    return {
        "code": 0,
        "path": key,
        "size": content.get("size") or len(data),
        "etag": content.get("sha") or sha256(data).hexdigest()[:32],
    }


def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None, **kwargs):
    config = _config(backend)
    error = _check(config)
    if error:
        return {"code": 1, "msg": error}

    save_result = save_result or {}
    token = str(config["token"]).strip()
    repo = str(config["repo"]).strip()
    key = save_result.get("path") or _key(
        config.get("basedir") or basedir, upload_path, filename
    )
    url = "%s/repos/%s/contents/%s" % (API, repo, key)
    branch = str(config.get("branch") or "").strip()

    try:
        content_sha = save_result.get("etag")
        if not content_sha:
            current = requests.get(
                url,
                params={"access_token": token},
                headers=_headers(),
                timeout=TIMEOUT,
            )
            if current.status_code != 200:
                return {"code": current.status_code or 1, "msg": _error(current)}
            content_sha = (current.json() or {}).get("sha")
        if not content_sha:
            return {"code": 1, "msg": "The content sha is required"}

        params = {
            "access_token": token,
            "message": "Delete %s by sapic" % key,
            "sha": content_sha,
        }
        if branch:
            params["branch"] = branch
        response = requests.delete(
            url, params=params, headers=_headers(), timeout=TIMEOUT
        )
    except Exception as exc:
        return {"code": 1, "msg": str(exc)}

    if response.status_code not in (200, 204):
        return {"code": response.status_code or 1, "msg": _error(response)}
    return {"code": 0}


def action_ping(values=None, context=None, **kwargs):
    config = ((context or {}).get("backend") or {}).get("config") or {}
    if requests is None:
        return {"code": 1, "message": "Please install requests module"}

    token = _value(values, config, "token")
    repo = _value(values, config, "repo")
    branch = _value(values, config, "branch")
    if not token or "/" not in repo:
        return {"code": 1, "message": "token and repo are required"}

    try:
        response = requests.get(
            "%s/repos/%s" % (API, repo),
            params={"access_token": token},
            headers=_headers(),
            timeout=15,
        )
        if response.status_code != 200:
            return {"code": 1, "message": _error(response)}
        if branch:
            response = requests.get(
                "%s/repos/%s/branches/%s" % (API, repo, branch),
                params={"access_token": token},
                headers=_headers(),
                timeout=15,
            )
            if response.status_code != 200:
                return {"code": 1, "message": _error(response)}
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    return {"code": 0, "toast": {"level": "success", "text": "repository is reachable"}}
