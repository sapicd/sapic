# -*- coding: utf-8 -*-
"""Web helpers: signed-cookie state, JSON response envelope and pagination.

Depends on the Flask application context (``jsonify`` / ``request``), so it
must not be imported by non-web modules.
"""

from __future__ import annotations

from typing import Any

from flask import Response, current_app, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..basis.vars import SESSION_COOKIE_NAME, SESSION_COOKIE_SALT
from .common import decode_cursor, encode_cursor


def _signer(salt: str) -> URLSafeTimedSerializer:
    """Build a serializer keyed by the application ``SECRET_KEY``."""
    return URLSafeTimedSerializer(current_app.secret_key, salt=salt)


def _cookie_options() -> dict:
    """Cookie attributes shared by every state cookie (httponly / secure / samesite)."""
    return {"httponly": True, "secure": request.is_secure, "samesite": "Lax"}


def set_cookie_state(
    response: Response,
    data: Any,
    max_age: int,
    name: str = SESSION_COOKIE_NAME,
    salt: str = SESSION_COOKIE_SALT,
) -> Response:
    """Sign ``data`` into a cookie named ``name`` and attach it to ``response``."""
    response.set_cookie(
        name,
        _signer(salt).dumps(data),
        max_age=max_age,
        **_cookie_options(),
    )
    return response


def get_cookie_state(
    max_age: int,
    name: str = SESSION_COOKIE_NAME,
    salt: str = SESSION_COOKIE_SALT,
) -> Any:
    """Verify and decode a state cookie; ``None`` when missing, tampered or expired."""
    token = request.cookies.get(name) or ""
    if not token:
        return None
    try:
        return _signer(salt).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def clear_cookie_state(
    response: Response, name: str = SESSION_COOKIE_NAME
) -> Response:
    """Delete the state cookie from ``response``."""
    response.delete_cookie(name, **_cookie_options())
    return response


def json_response(payload: dict, status: int = 200):
    return jsonify(payload), status


def ok(data=None, message: str = "", status: int = 200, **extra):
    """Standard success envelope: ``{code, message, data}``."""
    payload = {"code": "OK", "message": message}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return json_response(payload, status)


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
