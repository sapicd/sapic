# -*- coding: utf-8 -*-
"""Registration, login, password reset and personal access tokens."""

from __future__ import annotations

from hashlib import sha256

from flask import Blueprint, current_app, g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from ..basis.errors import ApiError, ErrorCode
from ..libs.auth import (
    current_csrf,
    current_user,
    generate_token,
    hash_token,
    login_required,
    login_user,
    logout_user,
)
from ..libs.mail import send_mail
from ..libs.settings import get_setting
from ..libs.users import (
    authenticate,
    change_password,
    create_user,
    normalize_username,
    serialize_user,
    update_profile,
)
from ..models import ApiToken, User
from ..models.base import now
from ..models.user import STATUS_DISABLED, STATUS_NORMAL, STATUS_PENDING
from ..utils.web import ok

bp = Blueprint("auth", __name__)

RESET_SALT = "sapic-reset-password"
RESET_MAX_AGE = 600


def _payload() -> dict:
    return request.get_json(silent=True) or request.form.to_dict()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=RESET_SALT)


def _password_fingerprint(password_hash: str) -> str:
    return sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def _reset_token(user: User) -> str:
    return _serializer().dumps(
        {"uid": user.id, "pv": _password_fingerprint(user.password_hash)}
    )


@bp.get("/auth/csrf")
@login_required
def csrf_token():
    return ok({"csrf": current_csrf()})


@bp.get("/auth/session")
def read_session():
    user = current_user()
    return ok(
        {
            "authenticated": user is not None,
            "user": serialize_user(user, True) if user else None,
            "csrf": current_csrf() if user else None,
        }
    )


@bp.post("/auth/register")
def register():
    if not current_app.config.get("ALLOW_REGISTER", True) or not get_setting(
        "allow_register", True
    ):
        raise ApiError("registration is disabled", ErrorCode.FORBIDDEN, 403)

    data = _payload()
    username = normalize_username(data.get("username", ""))
    reserved = {
        item.strip().lower()
        for item in str(get_setting("forbidden_username", "") or "").split(",")
        if item.strip()
    }
    if username in reserved:
        raise ApiError("username is reserved", ErrorCode.PARAM_ERROR)

    review = bool(get_setting("register_review", False))
    user = create_user(
        username=username,
        password=data.get("password", ""),
        email=data.get("email"),
        status=STATUS_PENDING if review else STATUS_NORMAL,
    )
    return ok({"user": serialize_user(user, True)}, status=201)


@bp.post("/auth/login")
def login():
    data = _payload()
    user = authenticate(data.get("username", ""), data.get("password", ""))
    csrf = login_user(user)
    return ok({"user": serialize_user(user, True), "csrf": csrf})


@bp.post("/auth/logout")
@login_required
def logout():
    logout_user()
    return ok({"logged_out": True})


@bp.post("/auth/password/forgot")
def forgot_password():
    data = _payload()
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise ApiError("email is required", ErrorCode.PARAM_ERROR)

    user = User.get_or_none(User.email == email)
    reset_token = None
    if user is not None and user.status != STATUS_DISABLED:
        reset_token = _reset_token(user)
        send_mail(
            to=user.email,
            subject="重置密码",
            body="10 分钟内有效，请访问重置密码页面并提交以下令牌：\n\n%s\n" % reset_token,
        )

    payload = {"sent": True}
    #: Without SMTP configured, expose the token to local/dev clients only.
    if reset_token and not (get_setting("smtp", {}) or {}).get("host"):
        if current_app.config.get("TESTING") or current_app.debug:
            payload["reset_token"] = reset_token
    return ok(payload, status=202)


@bp.post("/auth/password/reset")
def reset_password():
    data = _payload()
    token = data.get("token") or ""
    try:
        claims = _serializer().loads(token, max_age=RESET_MAX_AGE)
    except SignatureExpired as exc:
        raise ApiError("reset token expired", ErrorCode.PARAM_ERROR) from exc
    except BadSignature as exc:
        raise ApiError("invalid reset token", ErrorCode.PARAM_ERROR) from exc

    user = User.get_or_none(User.id == claims.get("uid"))
    if user is None or claims.get("pv") != _password_fingerprint(
        user.password_hash
    ):
        raise ApiError("invalid reset token", ErrorCode.PARAM_ERROR)

    change_password(user, data.get("password", ""))
    return ok({"reset": True})


@bp.put("/auth/profile")
@login_required
def edit_profile():
    user = update_profile(g.user, _payload())
    return ok({"user": serialize_user(user, True)})


@bp.put("/auth/password")
@login_required
def update_password():
    data = _payload()
    user = g.user
    if not check_password_hash(user.password_hash, data.get("old_password", "")):
        raise ApiError("current password is incorrect", ErrorCode.FORBIDDEN, 403)
    change_password(user, data.get("new_password", ""))
    csrf = login_user(user)
    return ok({"updated": True, "csrf": csrf})


@bp.get("/auth/tokens")
@login_required
def list_tokens():
    rows = (
        ApiToken.select()
        .where(ApiToken.owner == g.user)
        .order_by(ApiToken.created_at.desc())
    )
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "name": row.name,
                    "prefix": row.prefix,
                    "scopes": list(row.scopes or []),
                    "expires_at": row.expires_at,
                    "last_used_at": row.last_used_at,
                    "created_at": row.created_at,
                    "revoked": row.revoked_at is not None,
                }
                for row in rows
            ]
        }
    )


@bp.post("/auth/tokens")
@login_required
def create_token():
    data = _payload()
    token = generate_token()
    expires_in = data.get("expires_in")
    expires_at = None
    if expires_in:
        try:
            expires_at = now() + int(expires_in)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid expires_in", ErrorCode.PARAM_ERROR) from exc

    row = ApiToken.create(
        owner=g.user,
        name=(data.get("name") or "")[:64],
        token_hash=hash_token(token),
        prefix=token[:10],
        scopes=data.get("scopes") or ["upload"],
        expires_at=expires_at,
        created_at=now(),
    )
    return ok(
        {"id": row.id, "token": token, "prefix": row.prefix}, status=201
    )


@bp.delete("/auth/tokens/<int:token_id>")
@login_required
def revoke_token(token_id: int):
    row = ApiToken.get_or_none(
        (ApiToken.id == token_id) & (ApiToken.owner == g.user)
    )
    if row is None:
        raise ApiError("token not found", ErrorCode.NOT_FOUND, 404)
    row.revoked_at = now()
    row.save(only=[ApiToken.revoked_at])
    return ok({"revoked": True})
