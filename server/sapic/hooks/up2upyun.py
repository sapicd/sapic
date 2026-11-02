# -*- coding: utf-8 -*-
"""up2upyun — store objects in Upyun.

Driver contract (v2): ``upimg_save(filename, stream, upload_path, backend=...)``
returns ``{"code": 0, "path": <bucket key>, "size": <bytes>, "etag": <hash>}``.
The public URL is decided by the service layer, so the driver never returns
``src``; switching backends therefore never changes external links.

The credentials come from ``backend["config"]`` (``bucket`` / ``username`` /
``password`` / ``basedir``). Upyun keys are absolute, so ``basedir`` is
normalised to a leading ``/``.
"""

from __future__ import annotations

from hashlib import sha256

try:
    from upyun import ED_AUTO, UpYun
except ImportError:  # pragma: no cover - optional dependency
    ED_AUTO = UpYun = None

__version__ = "0.3.0"
__author__ = "staugur"
__description__ = "将图片保存到又拍云"
__catalog__ = "upload"
__state__ = "disabled"

FIELDS = (
    ("bucket", "input", "Bucket", "云存储服务的名称"),
    ("username", "input", "操作员", "云存储操作员账号（具有读写删除权限）"),
    ("password", "password", "密码", "云存储操作员密码"),
    ("basedir", "input", "存储根目录", "图片存储到又拍云的基础目录，默认是根目录"),
)
REQUIRED = ("bucket", "username", "password")


def hook_manifest():
    return {
        "title": "又拍云存储",
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
                "label": "检查存储桶",
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
        {"type": "button", "text": "检查存储桶", "action": "ping", "with_form": True}
    )
    if backend.get("in_use"):
        children.insert(
            0, {"type": "alert", "level": "success", "text": "当前正在使用"}
        )
    return [{"type": "fieldset", "legend": "又拍云存储", "children": children}]


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
    return "/" + "/".join(parts) if parts else "/"


def _service(config: dict, timeout: int = 30):
    """Return an ``UpYun`` client or an error message."""
    if UpYun is None:
        return None, "Please install upyun module"
    for key, label in (
        ("bucket", "bucket"),
        ("username", "username"),
        ("password", "password"),
    ):
        if not str(config.get(key) or "").strip():
            return None, "The upyun %s parameter error" % label
    client = UpYun(
        str(config["bucket"]).strip(),
        str(config["username"]).strip(),
        str(config["password"]).strip(),
        timeout=timeout,
        endpoint=ED_AUTO,
    )
    return client, ""


def upimg_save(filename, stream, upload_path="", backend=None, **kwargs):
    config = _config(backend)
    if not filename or stream is None:
        return {"code": 1, "msg": "Parameter error"}
    client, error = _service(config)
    if error:
        return {"code": 1, "msg": error}

    data = stream if isinstance(stream, (bytes, bytearray)) else stream.read()
    key = _key(config.get("basedir"), upload_path, filename)
    try:
        client.put(key, data)
    except Exception as exc:
        return {"code": 1, "msg": str(exc)}

    return {
        "code": 0,
        "path": key,
        "size": len(data),
        "etag": sha256(data).hexdigest()[:32],
    }


def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None, **kwargs):
    config = _config(backend)
    client, error = _service(config, timeout=10)
    if error:
        return {"code": 1, "msg": error}

    save_result = save_result or {}
    key = save_result.get("path") or _key(
        config.get("basedir") or basedir, upload_path, filename
    )
    try:
        client.delete(key)
    except Exception as exc:
        return {"code": 1, "msg": str(exc)}
    return {"code": 0}


def action_ping(values=None, context=None, **kwargs):
    config = ((context or {}).get("backend") or {}).get("config") or {}
    merged = {key: _value(values, config, key) for key, _, _, _ in FIELDS}
    client, error = _service(merged, timeout=10)
    if error:
        return {"code": 1, "message": error}

    try:
        #: A 404 for the probe key still proves the credentials and the bucket
        #: are valid, so only auth failures are reported as errors.
        client.getinfo("__sapic_probe__")
    except Exception as exc:
        status = getattr(exc, "status", None)
        if status in (401, 403):
            return {"code": 1, "message": "invalid credentials or bucket"}
        if status is None:
            return {"code": 1, "message": str(exc)}
    return {"code": 0, "toast": {"level": "success", "text": "bucket is reachable"}}
