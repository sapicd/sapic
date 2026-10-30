# -*- coding: utf-8 -*-
"""Public image delivery: ``/i/<sha>``.

The public URL is stable and storage agnostic. Local replicas are streamed
with range support; remote replicas are proxied by redirecting to the URL
returned by the driver.
"""

from __future__ import annotations

from flask import Blueprint, redirect, send_file

from ..errors import ApiError, ErrorCode
from ..models import Image
from ..models.album import VISIBILITY_PUBLIC
from ..models.image import STATUS_ENABLED
from ..security import current_user
from ..services.images import can_view, effective_visibility
from ..services.storage import local_path, replicas_for

bp = Blueprint("public", __name__)


@bp.get("/i/<sha>")
def image(sha: str):
    row = Image.get_or_none(
        (Image.sha == sha) & (Image.status == STATUS_ENABLED)
    )
    if row is None:
        raise ApiError("image not found", ErrorCode.NOT_FOUND, 404)
    if not can_view(current_user(), row):
        raise ApiError("permission denied", ErrorCode.FORBIDDEN, 403)

    public = effective_visibility(row) == VISIBILITY_PUBLIC
    for replica in replicas_for(row):
        path = local_path(replica)
        if path is not None:
            response = send_file(path, conditional=True)
            if public:
                response.cache_control.public = True
                response.cache_control.max_age = 31536000
                response.cache_control.immutable = True
            else:
                response.cache_control.private = True
                response.cache_control.max_age = 0
            return response
        if replica.url:
            return redirect(replica.url)

    raise ApiError("image data is unavailable", ErrorCode.NOT_FOUND, 404)
