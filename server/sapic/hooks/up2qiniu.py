# -*- coding: utf-8 -*-
"""up2qiniu — store objects in Qiniu Cloud.

Driver contract (v2): ``upimg_save(filename, stream, upload_path, backend=...)``
returns ``{"code": 0, "path": <bucket key>, "size": <bytes>, "etag": <hash>}``
plus ``src`` when the backend has a public ``domain``. Without it the service
layer falls back to ``/raw/<sha>``.

``upimg_url`` covers the private-bucket case: a backend marked ``private`` never
links to ``src`` (the bucket refuses anonymous reads), so the service layer asks
for a signed address (``private_download_url``) and relays the body itself.

The credentials come from ``backend["config"]`` (``bucket`` / ``access_key`` /
``secret_key`` / ``basedir`` / ``domain``). The SDK is optional and only
imported when the driver is actually used, with an English hint when it is
missing.
"""

from __future__ import annotations

from hashlib import sha256

try:
    from qiniu import Auth, BucketManager, put_data
except ImportError:  # pragma: no cover - optional dependency
    Auth = BucketManager = put_data = None

__version__ = "0.5.0"
__author__ = "staugur"
__description__ = "将图片保存到七牛云"
__catalog__ = "upload"
__state__ = "disabled"

FIELDS = (
    ("domain", "input", "加速域名", "绑定到存储桶的加速域名，如 https://static.example.com"),
    (
        "thumb_suffix",
        "input",
        "缩略图参数",
        "图片处理后缀，如 ?imageView2/2/w/400；留空则列表页加载原图",
    ),
    ("bucket", "input", "Bucket", "云存储服务的名称"),
    ("access_key", "password", "AccessKey", "七牛云个人密钥的 AK"),
    ("secret_key", "password", "SecretKey", "七牛云个人密钥的 SK"),
    ("basedir", "input", "存储根目录", "图片存储到七牛云的基础目录，默认是根目录"),
)
REQUIRED = ("domain", "bucket", "access_key", "secret_key")


def hook_manifest():
    return {
        "title": "七牛云存储",
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
    return [{"type": "fieldset", "legend": "七牛云存储", "children": children}]


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


def _auth(config: dict):
    """Return an ``Auth`` instance or an error message."""
    if Auth is None:
        return None, "Please install qiniu module"
    for key, label in (
        ("bucket", "bucket"),
        ("access_key", "access_key"),
        ("secret_key", "secret_key"),
    ):
        if not str(config.get(key) or "").strip():
            return None, "The qiniu %s parameter error" % label
    return (
        Auth(str(config["access_key"]).strip(), str(config["secret_key"]).strip()),
        "",
    )


def upimg_save(filename, stream, upload_path="", backend=None, **kwargs):
    config = _config(backend)
    if not filename or stream is None:
        return {"code": 1, "message": "Parameter error"}
    auth, error = _auth(config)
    if error:
        return {"code": 1, "message": error}

    domain = str(config.get("domain") or "").strip().rstrip("/")
    if not domain:
        return {"code": 1, "message": "The qiniu domain parameter error"}

    data = stream if isinstance(stream, (bytes, bytearray)) else stream.read()
    bucket = str(config["bucket"]).strip()
    key = _key(config.get("basedir"), upload_path, filename)
    token = auth.upload_token(bucket, key, 60)
    try:
        ret, info = put_data(token, key, data)
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    if not info.ok():
        return {"code": info.status_code or 1, "message": info.error or "qiniu upload failed"}

    return {
        "code": 0,
        "path": key,
        "size": len(data),
        "etag": (ret or {}).get("hash") or sha256(data).hexdigest()[:32],
        "src": "%s/%s" % (domain, key),
    }


def upimg_url(save_result, filename="", backend=None, expires=300, **kwargs):
    """Signed read address for a private bucket.

    Qiniu private downloads need the bound domain plus a token, so ``domain`` is
    required for this driver even when the bucket is private.
    """
    config = _config(backend)
    auth, error = _auth(config)
    if error:
        return {"code": 1, "message": error}

    domain = str(config.get("domain") or "").strip().rstrip("/")
    key = str((save_result or {}).get("path") or "").strip()
    if not domain or not key:
        return {"code": 1, "message": "The qiniu domain or object key parameter error"}
    try:
        url = auth.private_download_url(
            "%s/%s" % (domain, key), expires=int(expires or 300)
        )
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    return {"code": 0, "url": url}


def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None, **kwargs):
    config = _config(backend)
    auth, error = _auth(config)
    if error:
        return {"code": 1, "message": error}

    save_result = save_result or {}
    key = save_result.get("path") or _key(
        config.get("basedir") or basedir, upload_path, filename
    )
    try:
        _, info = BucketManager(auth).delete(str(config["bucket"]).strip(), key)
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    if not info.ok():
        return {"code": info.status_code or 1, "message": info.error or "qiniu delete failed"}
    return {"code": 0}


def action_ping(values=None, context=None, **kwargs):
    config = ((context or {}).get("backend") or {}).get("config") or {}
    merged = {key: _value(values, config, key) for key, _, _, _ in FIELDS}
    auth, error = _auth(merged)
    if error:
        return {"code": 1, "message": error}

    try:
        _, info = BucketManager(auth).stat(
            str(merged["bucket"]).strip(), "__sapic_probe__"
        )
    except Exception as exc:
        return {"code": 1, "message": str(exc)}
    #: 612 means "no such file", i.e. the credentials and the bucket are fine.
    if info.status_code in (401, 403):
        return {"code": 1, "message": "invalid access key or bucket"}
    return {"code": 0, "toast": {"level": "success", "text": "bucket is reachable"}}
