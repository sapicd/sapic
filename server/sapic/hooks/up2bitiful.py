# -*- coding: utf-8 -*-
"""up2bitiful — store objects in Bitiful S4.

S4 speaks the S3 protocol, and Bitiful's Python SDK *is* boto3 (the official
guide only asks for a different endpoint, region and key pair), so this driver
keeps no signing code of its own.

Driver contract (v2): ``upimg_save(filename, stream, upload_path, backend=...)``
returns ``{"code": 0, "path": <bucket key>, "size": <bytes>, "etag": <hash>}``
plus ``src`` when the backend has a public ``domain``. Without it the service
layer falls back to ``/raw/<sha>``.

``upimg_url`` covers the private-bucket case with a presigned GET; ``/raw``
relays the body, so the Address never reaches the browser.

The credentials come from ``backend["config"]`` (``bucket`` / ``access_key`` /
``secret_key`` / ``basedir`` / ``domain``). Bitiful child accounts start with no
permissions at all: a 403 ``AccessDenied`` means the key was never granted the
bucket (or directory), not that the secret is wrong.
"""

from __future__ import annotations

import mimetypes
from hashlib import sha256
from threading import Lock

try:
    import boto3
    from botocore.config import Config
except ImportError:  # pragma: no cover - optional dependency
    boto3 = None
    Config = None

__version__ = "0.5.0"
__author__ = "staugur"
__description__ = "将图片保存到缤纷云 S4"
__catalog__ = "upload"
__state__ = "disabled"

#: The only public endpoint and region Bitiful documents.
ENDPOINT = "https://s3.bitiful.net"
REGION = "cn-east-1"
#: Presigned URLs cannot outlive seven days; ``/raw`` only needs minutes.
MAX_EXPIRES = 7 * 24 * 3600
#: Read probe used by the admin "check bucket" action.
PROBE_KEY = "__sapic_probe__"

FIELDS = (
    (
        "domain",
        "input",
        "访问域名",
        "绑定到存储桶的 CDN 域名，如 https://img.example.com；私有桶留空，由 sapic 转发读取",
    ),
    (
        "thumb_suffix",
        "input",
        "缩略图参数",
        "图片处理后缀，如 ?w=400&fmt=webp；留空则列表页加载原图",
    ),
    ("bucket", "input", "Bucket", "S4 存储桶名称"),
    (
        "access_key",
        "input",
        "AccessKey",
        "子账户的 AccessKey（需先在控制台授权该桶或目录）",
    ),
    ("secret_key", "password", "SecretKey", "子账户的 SecretKey"),
    ("basedir", "input", "存储根目录", "图片存储到缤纷云的基础目录，默认是根目录"),
)
REQUIRED = ("bucket", "access_key", "secret_key")

#: boto3 clients own a connection pool, so one per credential set is reused by
#: every worker thread instead of being rebuilt for each upload or read.
_CLIENTS: dict[tuple[str, str], object] = {}
_CLIENT_LOCK = Lock()


def hook_manifest():
    return {
        "title": "缤纷云存储",
        "title_key": "hooks.up2bitiful.title",
        "description_key": "hooks.up2bitiful.description",
        "catalog": "upload",
        "config_schema": [
            {
                "type": kind,
                "key": key,
                "label": label,
                "label_key": "hooks.up2bitiful.fields.%s.label" % key,
                "placeholder": hint,
                "placeholder_key": "hooks.up2bitiful.fields.%s.hint" % key,
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
    return [{"type": "fieldset", "legend": "缤纷云存储", "children": children}]


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


def _error_code(exc) -> str:
    response = getattr(exc, "response", None)
    error = response.get("Error") if isinstance(response, dict) else None
    if isinstance(error, dict):
        return str(error.get("Code") or "").strip()
    return ""


def _error_message(exc) -> str:
    """``ClientError`` carries a code/message; anything else falls back to str."""
    response = getattr(exc, "response", None)
    error = response.get("Error") if isinstance(response, dict) else None
    if isinstance(error, dict):
        code = str(error.get("Code") or "").strip()
        message = str(error.get("Message") or "").strip()
        if code and message:
            return "%s: %s" % (code, message)
        return message or code or str(exc)
    return str(exc)


def _client(config: dict):
    """Return a cached ``boto3`` client or an error message."""
    if boto3 is None or Config is None:
        return None, "Please install boto3 module"
    for key, label in (
        ("bucket", "bucket"),
        ("access_key", "access_key"),
        ("secret_key", "secret_key"),
    ):
        if not str(config.get(key) or "").strip():
            return None, "The bitiful %s parameter error" % label

    access_key = str(config["access_key"]).strip()
    secret_key = str(config["secret_key"]).strip()
    cache_key = (access_key, secret_key)
    with _CLIENT_LOCK:
        client = _CLIENTS.get(cache_key)
    if client is not None:
        return client, ""

    try:
        client = boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            region_name=REGION,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual"},
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=15,
                read_timeout=60,
            ),
        )
    except Exception as exc:
        return None, _error_message(exc)

    with _CLIENT_LOCK:
        _CLIENTS.setdefault(cache_key, client)
        return _CLIENTS[cache_key], ""


def upimg_save(filename, stream, upload_path="", backend=None, **kwargs):
    config = _config(backend)
    if not filename or stream is None:
        return {"code": 1, "message": "Parameter error"}
    client, error = _client(config)
    if error:
        return {"code": 1, "message": error}
    bucket = str(config.get("bucket") or "").strip()
    if not bucket:
        return {"code": 1, "message": "The bitiful bucket parameter error"}

    data = stream if isinstance(stream, (bytes, bytearray)) else stream.read()
    key = _key(config.get("basedir"), upload_path, filename)
    content_type = (
        mimetypes.guess_type(str(filename))[0] or "application/octet-stream"
    )
    try:
        response = client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except Exception as exc:
        return {"code": 1, "message": _error_message(exc)}

    result = {
        "code": 0,
        "path": key,
        "size": len(data),
        "etag": str((response or {}).get("ETag") or "").strip('"')
        or sha256(data).hexdigest()[:32],
    }
    #: 私有桶不需要域名：没有域名时不给 src，读取一律走 /raw 签名转发。
    domain = str(config.get("domain") or "").strip().rstrip("/")
    if domain:
        result["src"] = "%s/%s" % (domain, key)
    return result


def _expires(value) -> int:
    """Presigned URL lifetime, clamped to what S4 accepts (1s .. 7d)."""
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        seconds = 0
    return min(max(seconds, 1), MAX_EXPIRES)


def upimg_url(save_result, filename="", backend=None, expires=300, **kwargs):
    """Presigned GET for a private bucket; ``/raw`` proxies the body."""
    config = _config(backend)
    client, error = _client(config)
    if error:
        return {"code": 1, "message": error}

    bucket = str(config.get("bucket") or "").strip()
    key = str((save_result or {}).get("path") or "").strip()
    if not bucket or not key:
        return {"code": 1, "message": "The bitiful object key parameter error"}
    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=_expires(expires),
        )
    except Exception as exc:
        return {"code": 1, "message": _error_message(exc)}
    return {"code": 0, "url": url}


def upimg_delete(sha, upload_path, filename, basedir, save_result, backend=None, **kwargs):
    config = _config(backend)
    client, error = _client(config)
    if error:
        return {"code": 1, "message": error}

    bucket = str(config.get("bucket") or "").strip()
    save_result = save_result or {}
    key = save_result.get("path") or _key(
        config.get("basedir") or basedir, upload_path, filename
    )
    if not bucket or not key:
        return {"code": 1, "message": "The bitiful object key parameter error"}
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except Exception as exc:
        return {"code": 1, "message": _error_message(exc)}
    return {"code": 0}


def action_ping(values=None, context=None, **kwargs):
    config = ((context or {}).get("backend") or {}).get("config") or {}
    merged = {key: _value(values, config, key) for key, _, _, _ in FIELDS}
    client, error = _client(merged)
    if error:
        return {"code": 1, "message": error}

    try:
        #: 探测一个不存在的键：404 说明凭据与桶都没问题，403 才是没授权。
        client.head_object(Bucket=str(merged["bucket"]).strip(), Key=PROBE_KEY)
    except Exception as exc:
        if _error_code(exc) not in ("404", "NoSuchKey", "NotFound"):
            return {"code": 1, "message": _error_message(exc)}
    return {"code": 0, "toast": {"level": "success", "text": "bucket is reachable"}}
