# -*- coding: utf-8 -*-
"""v1 compatible endpoints: ``/api/upload`` and ``/api/sha/<sha>``.

Clients keep the legacy response shape (``{code: 0/1, msg, src, ...}``)
while the v2 service layer does the actual work.
"""

from __future__ import annotations

import base64
import binascii

from flask import Blueprint, jsonify, request, url_for
from werkzeug.utils import secure_filename

from ..errors import ApiError, ErrorCode
from ..models import Album, Image
from ..models.base import now
from ..models.image import STATUS_ENABLED
from ..security import current_user, resolve_pat
from ..services.images import (
    can_view,
    create_image,
    delete_image,
    public_url,
    serialize_image,
)
from ..services.settings import get_setting

bp = Blueprint("legacy", __name__)


def _legacy_user():
    """Authenticate with a PAT passed as ``token``, else the cookie session."""
    token = request.form.get("token") or request.args.get("token")
    if token:
        user = resolve_pat(token.strip())
        if user is None:
            raise ApiError("invalid token", ErrorCode.UNAUTHORIZED, 401)
        return user
    return current_user()


def _ensure_album(user, name: str):
    if not name or not user:
        return None
    album = Album.get_or_none((Album.owner == user) & (Album.name == name))
    if album is None:
        album = Album.create(
            owner=user,
            name=name[:100],
            visibility=get_setting("default_album_visibility", "private"),
            created_at=now(),
            updated_at=now(),
        )
    return album


def _field_value(name: str, default=None):
    return request.form.get(name) or request.args.get(name) or default


def _v1_payload(image: Image, fmt: str | None = None) -> dict:
    replicas = list(image.replicas)
    sender = replicas[0].backend.hook_name if replicas else ""
    src = public_url(image.sha)
    payload = {
        "code": 0,
        "msg": None,
        "sha": image.sha,
        "filename": image.filename,
        "sender": sender,
        "api": url_for("legacy.shamgr", sha=image.sha, _external=True),
        "tpl": src,
        "is_video": bool(image.is_video),
        "src": src,
    }
    if fmt == "data.src":
        payload["data"] = {"src": src}
    elif fmt:
        payload[fmt] = src
    return payload


@bp.errorhandler(ApiError)
def _legacy_api_error(exc: ApiError):
    return jsonify({"code": 1, "msg": exc.message}), 200


@bp.post("/api/upload")
def upload():
    user = _legacy_user()
    if user is None and not get_setting(
        "allow_anonymous_upload", False
    ):
        raise ApiError("Anonymous user is not sign in", ErrorCode.FORBIDDEN, 403)
    if user is not None and user.status in (-2, -1, 0):
        raise ApiError("account cannot upload", ErrorCode.FORBIDDEN, 403)

    #: v1 clients use ``picbed`` as the upload field.
    field = _field_value("_upload_field") or "picbed"
    file = request.files.get(field)
    filename = secure_filename(_field_value("filename") or "")

    if file is not None and file.filename:
        stream = file.stream.read()
        mime = file.mimetype or ""
        filename = file.filename
    else:
        raw = request.form.get(field) or ""
        if not raw:
            raise ApiError("No file or image format error", ErrorCode.PARAM_ERROR)
        if raw.startswith("http://") or raw.startswith("https://"):
            raise ApiError(
                "remote url upload is not supported",
                ErrorCode.PARAM_ERROR,
            )
        try:
            if raw.startswith("data:") and "," in raw:
                raw = raw.split(",", 1)[1]
            stream = base64.b64decode(raw)
        except (binascii.Error, ValueError) as exc:
            raise ApiError("Invalid base64 data", ErrorCode.PARAM_ERROR) from exc
        mime = ""
        if not filename:
            filename = "image.png"

    album_name = _field_value("album") or ""
    album = _ensure_album(user, album_name)
    expire = 0
    if _field_value("expire"):
        try:
            expire = int(_field_value("expire"))
        except (TypeError, ValueError) as exc:
            raise ApiError("Invalid expire param", ErrorCode.PARAM_ERROR) from exc

    image = create_image(
        owner=user,
        filename=filename,
        stream=stream,
        mime=mime,
        album=album,
        title=_field_value("title") or "",
        expire=expire,
    )
    return jsonify(_v1_payload(image, _field_value("format")))


@bp.route("/api/sha/<sha>", methods=["GET", "DELETE", "PUT"])
def shamgr(sha: str):
    user = _legacy_user()
    image = Image.get_or_none(
        (Image.sha == sha) & (Image.status == STATUS_ENABLED)
    )
    if image is None:
        return jsonify({"code": 3, "msg": "No data"})
    if not can_view(user, image):
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    if request.method == "GET":
        data = serialize_image(image)
        data.update(
            {
                "album": image.album.name if image.album else "",
                "sender": image.replicas[0].backend.hook_name
                if image.replicas
                else "",
                "ctime": image.created_at,
            }
        )
        return jsonify({"code": 0, "data": data})

    if image.owner_id != getattr(user, "id", None) and not getattr(
        user, "is_admin", False
    ):
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    if request.method == "DELETE":
        delete_image(image)
        return jsonify({"code": 0, "msg": "success"})

    #: PUT updates album/title, matching v1 semantics.
    album_name = _field_value("album")
    if album_name is not None:
        image.album = _ensure_album(image.owner, album_name)
    if _field_value("title") is not None:
        image.title = (_field_value("title") or "")[:255]
    image.updated_at = now()
    image.save(only=[Image.album, Image.title, Image.updated_at])
    return jsonify({"code": 0, "msg": "success"})
