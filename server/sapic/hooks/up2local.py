# -*- coding: utf-8 -*-
"""up2local — save objects under a local directory.

Driver contract (v2):

``upimg_save(filename, stream, upload_path, backend=...)`` returns
``{"code": 0, "path": <object key>, "size": <bytes>, "etag": <hash>}``.
The public URL is decided by the service layer, so switching storage does
not change external links.

``upimg_delete(sha, upload_path, filename, basedir, save_result)`` removes
the object; failures must not raise.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

__version__ = "0.3.0"
__author__ = "staugur"
__description__ = "将图片保存到本地目录"
__catalog__ = "upload"
__state__ = "enabled"


def _root(backend=None, **kwargs) -> str:
    config = (backend or {}).get("config") or {}
    return config.get("root") or kwargs.get("root") or ""


def upimg_save(filename, stream, upload_path="", backend=None, **kwargs):
    root = _root(backend, **kwargs)
    if not root or not filename:
        return {"code": 1, "msg": "Parameter error"}

    key = "/".join(
        part.strip("/")
        for part in (str(upload_path or ""), filename)
        if part and part.strip("/")
    )
    target = Path(root) / key
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = stream if isinstance(stream, (bytes, bytearray)) else stream.read()
        target.write_bytes(data)
    except OSError as exc:
        return {"code": 1, "msg": str(exc)}

    return {
        "code": 0,
        "path": key,
        "size": len(data),
        "etag": sha256(data).hexdigest()[:32],
    }


def upimg_delete(sha, upload_path, filename, basedir, save_result):
    key = (save_result or {}).get("path") or "/".join(
        part for part in (upload_path, filename) if part
    )
    target = Path(basedir or "") / key
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass
    return {"code": 0}


def upimg_exists(save_result):
    target = Path(save_result.get("basedir", "")) / save_result.get("path", "")
    return {"code": 0, "exists": bool(target and target.is_file())}
