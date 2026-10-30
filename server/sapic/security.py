# -*- coding: utf-8 -*-
"""Authentication primitives: cookie sessions, PATs and CSRF.

Cookie sessions are signed with ``SECRET_KEY`` and carry a
``session_version`` snapshot. Bumping the user's ``session_version`` (e.g. on
password change) revokes every existing session without server-side storage.
"""

from __future__ import annotations

import hmac
import secrets
from functools import wraps
from hashlib import sha256

from flask import g, request, session

from .errors import ApiError, ErrorCode
from .models import ApiToken, User
from .models.base import now
from .models.user import STATUS_DISABLED

TOKEN_PREFIX = "sp_"
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def login_user(user: User) -> str:
    """Start a cookie session and return the CSRF token."""
    session.clear()
    session.permanent = True
    session["uid"] = user.id
    session["sv"] = int(user.session_version or 0)
    csrf = secrets.token_urlsafe(32)
    session["csrf"] = csrf
    return csrf


def logout_user() -> None:
    session.clear()


def current_user() -> User | None:
    return getattr(g, "user", None)


def resolve_pat(token: str) -> User | None:
    """Resolve a personal access token to its owner."""
    row = ApiToken.get_or_none(ApiToken.token_hash == hash_token(token))
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at is not None and row.expires_at <= now():
        return None
    user = row.owner
    if user is None or user.status == STATUS_DISABLED:
        return None
    #: Best effort, never fail the request because of statistics.
    try:
        ApiToken.update(last_used_at=now()).where(
            ApiToken.id == row.id
        ).execute()
    except Exception:
        pass
    return user


def _load_current_user() -> None:
    g.user = None
    g.auth_type = None

    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        user = resolve_pat(auth[7:].strip())
        if user is not None:
            g.user = user
            g.auth_type = "token"
            return

    uid = session.get("uid")
    if uid is None:
        return
    user = User.get_or_none(User.id == uid)
    if user is None or user.status == STATUS_DISABLED:
        return
    if int(user.session_version or 0) != int(session.get("sv", -1)):
        #: Password changed or sessions revoked.
        session.clear()
        return
    g.user = user
    g.auth_type = "session"


def _csrf_protect() -> None:
    if request.method in SAFE_METHODS:
        return
    #: v1 protocol endpoints are token based and never carried a CSRF token.
    if request.path.startswith("/api/upload") or request.path.startswith(
        "/api/sha/"
    ):
        return
    if getattr(g, "auth_type", None) != "session":
        #: Bearer tokens are not vulnerable to CSRF.
        return
    token = request.headers.get("X-CSRF-Token") or request.form.get("_csrf", "")
    expected = session.get("csrf") or ""
    if not token or not expected or not hmac.compare_digest(
        str(token), str(expected)
    ):
        raise ApiError("invalid csrf token", ErrorCode.FORBIDDEN, 403)


def init_app(app) -> None:
    app.before_request(_load_current_user)
    app.before_request(_csrf_protect)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            raise ApiError(
                "authentication required", ErrorCode.UNAUTHORIZED, 401
            )
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            raise ApiError(
                "authentication required", ErrorCode.UNAUTHORIZED, 401
            )
        if not user.is_admin:
            raise ApiError("admin permission required", ErrorCode.FORBIDDEN, 403)
        return view(*args, **kwargs)

    return wrapper
