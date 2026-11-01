# -*- coding: utf-8 -*-
"""Authentication primitives: signed-cookie sessions, PATs and CSRF.

Login state lives in a signed cookie (itsdangerous, salt
``SESSION_COOKIE_SALT``) carrying ``{uid, sv, csrf}``; nothing is stored on the
server. ``sv`` snapshots ``User.session_version``, so bumping it (e.g. on
password change) revokes every existing session.
"""

from __future__ import annotations

import hmac
import secrets
from functools import wraps
from hashlib import sha256

from flask import current_app, g, request

from ..basis.errors import ApiError, ErrorCode
from ..basis.vars import SESSION_COOKIE_NAME
from ..models import ApiToken, User
from ..models.base import now
from ..models.user import STATUS_DISABLED
from ..utils.web import clear_cookie_state, get_cookie_state, set_cookie_state

TOKEN_PREFIX = "sp_"
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def _session_ttl() -> int:
    return int(current_app.config.get("SESSION_TTL") or 7 * 24 * 3600)


def login_user(user: User) -> str:
    """Start a cookie session and return the CSRF token.

    The cookie itself is attached to the outgoing response by the
    ``after_request`` hook registered in :func:`init_app`.
    """
    csrf = secrets.token_urlsafe(32)
    g.login_state = {
        "uid": user.id,
        "sv": int(user.session_version or 0),
        "csrf": csrf,
    }
    return csrf


def logout_user() -> None:
    """Drop the login-state cookie on the outgoing response."""
    g.login_state = None
    g.login_state_cleared = True


def current_user() -> User | None:
    return getattr(g, "user", None)


def current_csrf() -> str:
    return getattr(g, "csrf", "") or ""


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
    g.csrf = ""
    g.login_state = None
    g.login_state_cleared = False

    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        user = resolve_pat(auth[7:].strip())
        if user is not None:
            g.user = user
            g.auth_type = "token"
            return

    state = get_cookie_state(_session_ttl(), SESSION_COOKIE_NAME)
    if not isinstance(state, dict):
        return

    try:
        uid = int(state["uid"])
        version = int(state.get("sv", -1))
    except (KeyError, TypeError, ValueError):
        g.login_state_cleared = True
        return

    user = User.get_or_none(User.id == uid)
    if user is None or user.status == STATUS_DISABLED:
        g.login_state_cleared = True
        return
    if int(user.session_version or 0) != version:
        #: Password changed or sessions revoked.
        g.login_state_cleared = True
        return

    g.user = user
    g.auth_type = "session"
    g.csrf = state.get("csrf", "")


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
    expected = current_csrf()
    if not token or not expected or not hmac.compare_digest(
        str(token), str(expected)
    ):
        raise ApiError("invalid csrf token", ErrorCode.FORBIDDEN, 403)


def _save_login_state(response):
    """Write or clear the login-state cookie on the outgoing response."""
    state = getattr(g, "login_state", None)
    if isinstance(state, dict):
        return set_cookie_state(
            response, state, _session_ttl(), SESSION_COOKIE_NAME
        )
    if getattr(g, "login_state_cleared", False):
        return clear_cookie_state(response, SESSION_COOKIE_NAME)
    return response


def init_app(app) -> None:
    app.before_request(_load_current_user)
    app.before_request(_csrf_protect)
    app.after_request(_save_login_state)


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
