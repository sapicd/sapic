# -*- coding: utf-8 -*-
"""Public plaza: images their owners explicitly published for everyone to see.

The plaza is an exposure channel, not a permission boundary: each entry keeps
its own visibility, so only public images show up here (see
:func:`sapic.libs.images.plaza_query`).
"""

from __future__ import annotations

from flask import Blueprint, request

from ..basis.errors import ApiError, ErrorCode
from ..libs.images import album_serializer, plaza_query
from ..libs.settings import get_setting
from ..models import Image
from ..utils.web import ok, paginate

bp = Blueprint("plaza", __name__)


@bp.get("/plaza")
def plaza():
    if not get_setting("plaza_enabled", False):
        raise ApiError("plaza is disabled", ErrorCode.NOT_FOUND, 404)

    try:
        limit = int(request.args.get("limit", 24))
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid limit", ErrorCode.PARAM_ERROR) from exc

    #: ``paginate`` orders by ``(created_at, id)`` descending itself.
    query = plaza_query()
    serialize, prefetch = album_serializer()
    return ok(
        paginate(
            query,
            Image,
            serialize,
            limit=limit,
            cursor=request.args.get("cursor"),
            prefetch=prefetch,
        )
    )
