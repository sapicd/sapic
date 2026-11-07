# -*- coding: utf-8 -*-
"""up2github — store objects in a GitHub repository.

Driver contract (v2): ``upimg_save(filename, stream, upload_path, backend=...)``
returns ``{"code": 0, "path": <repo key>, "size": <bytes>, "etag": <blob sha>}``
plus ``src``, the ``download_url`` GitHub reports for the new blob (public
repositories only; the service layer falls back to ``/raw/<sha>`` without it).

``etag`` is the blob sha GitHub assigns, which lets :func:`upimg_delete` remove
the object without a round trip; the credentials come from ``backend["config"]``
(``token`` / ``repo`` / ``branch`` / ``basedir``).

``upimg_url`` serves private repositories: ``raw.githubusercontent.com`` ignores
tokens, so the service layer reads the object through the contents API with the
raw media type and relays the body itself.
"""

from __future__ import annotations

from base64 import b64encode
from hashlib import sha256

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None

__version__ = "0.4.0"
__author__ = "staugur"
__description__ = "将图片保存到GitHub"
__catalog__ = "upload"
__state__ = "disabled"

API = "https://api.github.com"
TIMEOUT = 30

#: (key, node type, label, hint) shared by the manifest and the settings slot.
FIELDS = (
    ("domain", "input", "加速域名", "如 JsDelivr 或自建加速地址，留空则使用仓库源站地址"),
    ("token", "password", "Token", "GitHub personal access token（repo 权限）"),
    ("repo", "input", "仓库名", "公开仓库，格式：用户名/仓库名"),
    ("branch", "input", "分支", "仓库分支，留空则使用仓库默认分支"),
    ("basedir", "input", "存储根目录", "图片存储到仓库的基础目录，默认是根目录"),
)
REQUIRED = ("token", "repo")


def hook_manifest():
    return {
        "title": "GitHub 版本库",
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
    return [{"type": "fieldset", "legend": "GitHub 版本库", "children": children}]


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


def _headers(token: str) -> dict:
    return {
        "User-Agent": "sapic-up2github/%s" % __version__,
        "Authorization": "token %s" % token,
        "Accept": "application/vnd.github+json",
    }


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
        return "The github parameter error"
    if "/" not in str(config.get("repo") or ""):
        return "The github parameter error"
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
        "message": "Create %s by sapic" % key,
        "content": b64encode(data).decode("utf-8"),
    }
    branch = str(config.get("branch") or "").strip()
    if branch:
        payload["branch"] = branch

    try:
        response = requests.put(
            "%s/repos/%s/contents/%s" % (API, repo, key),
            json=payload,
            headers=_headers(token),
            timeout=TIMEOUT,
        )
    except Exception as exc:
        return {"code": 1, "msg": str(exc)}

    if response.status_code != 201:
        return {"code": response.status_code or 1, "msg": _error(response)}

    content = (response.json() or {}).get("content") or {}
    result = {
        "code": 0,
        "path": key,
        "size": content.get("size") or len(data),
        "etag": content.get("sha") or sha256(data).hexdigest()[:32],
    }
    #: 加速域名优先；其次是 GitHub 给出的 raw 地址；私有仓库两者都需 token，
    #: 服务层只对公开图使用。
    src = str(config.get("domain") or "").strip().rstrip("/")
    if src:
        src = "%s/%s" % (src, key)
    else:
        src = content.get("download_url") or ""
        if not src and "/" in repo:
            src = "https://cdn.jsdelivr.net/gh/%s%s/%s" % (
                repo,
                "@" + branch if branch else "",
                key,
            )
    if src:
        result["src"] = src
    return result


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
    headers = _headers(token)
    branch = str(config.get("branch") or "").strip()

    try:
        content_sha = save_result.get("etag")
        if not content_sha:
            current = requests.get(url, headers=headers, timeout=TIMEOUT)
            if current.status_code != 200:
                return {"code": current.status_code or 1, "msg": _error(current)}
            content_sha = (current.json() or {}).get("sha")
        if not content_sha:
            return {"code": 1, "msg": "The content sha is required"}

        payload = {"message": "Delete %s by sapic" % key, "sha": content_sha}
        if branch:
            payload["branch"] = branch
        response = requests.delete(
            url, json=payload, headers=headers, timeout=TIMEOUT
        )
    except Exception as exc:
        return {"code": 1, "msg": str(exc)}

    if response.status_code not in (200, 204):
        return {"code": response.status_code or 1, "msg": _error(response)}
    return {"code": 0}


def upimg_url(save_result, filename="", backend=None, expires=300, **kwargs):
    """Authenticated read address for a private repository.

    ``raw.githubusercontent.com`` ignores tokens, so a private object is read
    through the contents API with the raw media type; sapic relays the body and
    the token never reaches the browser. ``expires`` does not apply — the token
    authorises each request.
    """
    config = _config(backend)
    error = _check(config)
    if error:
        return {"code": 1, "msg": error}

    key = str((save_result or {}).get("path") or "").strip()
    if not key:
        return {"code": 1, "msg": "The object key is required"}
    repo = str(config["repo"]).strip()
    url = "%s/repos/%s/contents/%s" % (API, repo, key)
    branch = str(config.get("branch") or "").strip()
    if branch:
        url = "%s?ref=%s" % (url, branch)

    headers = _headers(str(config["token"]).strip())
    headers["Accept"] = "application/vnd.github.raw"
    return {"code": 0, "url": url, "headers": headers}


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
            "%s/repos/%s" % (API, repo), headers=_headers(token), timeout=15
        )
        if response.status_code != 200:
            return {"code": 1, "message": _error(response)}
        if branch:
            response = requests.get(
                "%s/repos/%s/branches/%s" % (API, repo, branch),
                headers=_headers(token),
                timeout=15,
            )
            if response.status_code != 200:
                return {"code": 1, "message": _error(response)}
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    return {"code": 0, "toast": {"level": "success", "text": "repository is reachable"}}
