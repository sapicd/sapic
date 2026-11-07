# -*- coding: utf-8 -*-
"""v1 client compatibility: ``POST /api/upload``.

PicGo / uPic / Typora are configured once with an endpoint and a token, so
keeping the v1 path working is cheaper than asking every user to reconfigure.
The endpoint accepts the v1 form fields (``picbed`` for a file, a URL or a
base64/Data-URI string) and answers with the v1 envelope (``{code, msg, ...}``)
rather than the v2 one.

Authentication is the v2 model: a session cookie, a ``Bearer`` token, or the
``token`` form field old clients already send (a PAT, *not* a v1 LinkToken).
"""

from __future__ import annotations

import base64
import binascii
from mimetypes import guess_extension
from uuid import uuid4

from flask import Blueprint, g, jsonify, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.albums import default_album
from ..libs.auth import (
    SCOPE_UPLOAD,
    csrf_valid,
    current_user,
    resolve_pat,
)
from ..libs.images import (
    anonymous_upload_allowed,
    check_upload_limits,
    create_image,
    download_image,
    fetch_limit_mb,
    image_src,
    resolve_expire_seconds,
)
from ..libs.settings import get_setting
from ..models import Album, ImageBackend
from ..models.album import VISIBILITY_PUBLIC
from ..models.base import now
from ..models.user import STATUS_DISABLED, STATUS_PENDING, STATUS_REJECTED

bp = Blueprint("legacy", __name__)

#: 与 v2 原生上传同一口径：这三种状态的账号不能上传。
BLOCKED_STATUS = (STATUS_REJECTED, STATUS_PENDING, STATUS_DISABLED)

#: v1 默认的表单字段名，可通过 ``_upload_field`` 覆盖。
DEFAULT_FIELD = "picbed"


def _v1_error(message: str, status: int = 400):
    """v1 clients parse ``{code, msg}``, not the v2 envelope."""
    return jsonify({"code": 1, "msg": message, "data": None}), status


def _decode_base64(raw: str) -> tuple[bytes, str]:
    """Decode plain base64 or a ``data:<mime>;base64,`` payload."""
    mime = ""
    payload = raw.strip()
    if payload.lower().startswith("data:") and "," in payload:
        header, payload = payload.split(",", 1)
        mime = header[5:].split(";", 1)[0]
    #: 部分客户端把 + 编码成了空格，v1 也做同样的还原。
    payload = payload.replace(" ", "+")
    try:
        stream = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ApiError("invalid base64 payload", ErrorCode.PARAM_ERROR) from exc
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)
    return stream, mime


def _fallback_filename(mime: str) -> str:
    """``截屏`` 之类的名字会被清洗掉，没有后缀时按 MIME 补一个。"""
    ext = guess_extension(mime or "") or ".png"
    return "%s%s" % (uuid4().hex[:8], ext)


def _legacy_album(user, name: str):
    """v1 passed the album as a plain string; create it on first use."""
    if user is None:
        return None
    name = (name or "").strip()
    if not name:
        return default_album(user)
    album = Album.get_or_none((Album.owner == user) & (Album.name == name))
    if album is not None:
        return album
    visibility = get_setting("default_album_visibility", VISIBILITY_PUBLIC)
    return Album.create(
        owner=user,
        name=name[:100],
        visibility=visibility,
        description="",
        created_at=now(),
        updated_at=now(),
    )


def _sender_of(image) -> str:
    replica = (
        ImageBackend.select(ImageBackend)
        .where((ImageBackend.image == image) & (ImageBackend.is_primary == True))
        .first()
    )
    return replica.backend.hook_name if replica is not None else ""


def _authenticate():
    """Session (with CSRF) or a PAT in ``Authorization`` / ``token``."""
    user = current_user()
    if user is not None:
        if getattr(g, "auth_type", None) == "session" and not csrf_valid():
            raise ApiError(
                "browser sessions must send X-CSRF-Token; use an access token "
                "for API clients",
                ErrorCode.FORBIDDEN,
                403,
            )
        return user

    token = (
        request.form.get("token") or request.headers.get("X-Token") or ""
    ).strip()
    if token:
        resolved = resolve_pat(token)
        if resolved is not None:
            owner, scopes = resolved
            if SCOPE_UPLOAD not in scopes:
                raise ApiError(
                    "token scope does not allow upload", ErrorCode.FORBIDDEN, 403
                )
            return owner
        raise ApiError("invalid token", ErrorCode.UNAUTHORIZED, 401)
    return None


def _handle_upload():
    user = _authenticate()
    if user is None:
        if not anonymous_upload_allowed():
            raise ApiError(
                "anonymous upload is disabled", ErrorCode.FORBIDDEN, 403
            )
    elif user.status in BLOCKED_STATUS:
        raise ApiError("account cannot upload", ErrorCode.FORBIDDEN, 403)

    field = (request.form.get("_upload_field") or DEFAULT_FIELD).strip()
    filename = (request.form.get("filename") or "").strip()
    mime = ""

    upload = request.files.get(field)
    if upload is not None and upload.filename:
        filename = upload.filename
        mime = upload.mimetype or ""
        stream = upload.stream.read()
    else:
        raw = (request.form.get(field) or "").strip()
        if not raw:
            raise ApiError("no file or image data", ErrorCode.PARAM_ERROR)
        if raw.startswith(("http://", "https://")):
            stream, remote_name, mime = download_image(
                raw, fetch_limit_mb() * 1024 * 1024
            )
            filename = filename or remote_name
        else:
            stream, mime = _decode_base64(raw)
            filename = filename or _fallback_filename(mime)

    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)
    check_upload_limits(filename, len(stream))

    album = _legacy_album(user, request.form.get("album") or "")
    image = create_image(
        owner=user,
        filename=filename,
        stream=stream,
        mime=mime,
        album=album,
        title=request.form.get("title") or "",
        expire=resolve_expire_seconds(request.form.get("expire")),
    )

    src = image_src(image)
    body = {
        "code": 0,
        "msg": "",
        "filename": image.filename,
        "sha": image.sha,
        "size": image.size,
        "src": src,
        "url": src,
        "is_video": bool(image.is_video),
        "sender": _sender_of(image),
        "api": request.url,
        "tpl": src,
    }
    #: v1 的 ``format`` 参数：``imgUrl`` 或 ``data.src`` 决定图片地址放在哪。
    fmt = (request.form.get("format") or "").strip()
    if fmt:
        if "." in fmt:
            outer, inner = fmt.split(".", 1)
            body[outer] = {inner: src}
        else:
            body[fmt] = src
    return jsonify(body), 200


@bp.post("/api/upload")
def upload():
    #: 兼容端点用 v1 信封表达错误，避免老客户端读到 v2 的 ``code: "FORBIDDEN"``。
    try:
        return _handle_upload()
    except ApiError as exc:
        status = exc.status_code if exc.status_code >= 400 else 400
        return _v1_error(exc.message, status)
