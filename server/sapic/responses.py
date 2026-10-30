# -*- coding: utf-8 -*-
"""JSON response helpers and cursor pagination."""

from __future__ import annotations

import base64
import binascii

from flask import jsonify

from .errors import ApiError, ErrorCode

OK = "OK"


def json_response(payload: dict, status: int = 200):
    return jsonify(payload), status


def ok(data=None, message: str = "", status: int = 200, **extra):
    """Standard success envelope: ``{code, message, data}``."""
    payload = {"code": OK, "message": message}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return json_response(payload, status)


def encode_cursor(*values) -> str:
    raw = ":".join(str(v) for v in values)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[int, int]:
    """Decode a ``created_at:id`` cursor."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_at, row_id = raw.split(":", 1)
        return int(created_at), int(row_id)
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError) as exc:
        raise ApiError(
            "invalid cursor", ErrorCode.PARAM_ERROR, 400
        ) from exc


def paginate(query, model, serializer, limit: int = 20, cursor: str | None = None):
    """Cursor pagination ordered by ``(created_at, id)`` descending.

    ``model`` must expose ``created_at`` and an integer ``id``.
    """
    limit = max(1, min(int(limit or 20), 100))
    if cursor:
        created_at, row_id = decode_cursor(cursor)
        query = query.where(
            (model.created_at < created_at)
            | ((model.created_at == created_at) & (model.id < row_id))
        )

    rows = list(
        query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "items": [serializer(row) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "limit": limit,
    }
