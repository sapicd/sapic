# -*- coding: utf-8 -*-
"""Registration, login, password reset and personal access tokens."""

from __future__ import annotations

import logging
import secrets
from hashlib import sha256

from flask import Blueprint, current_app, g, redirect, request, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from ..basis.common import as_bool
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
from ..libs.hook import get_hook_manager
from ..libs.mail import send_mail
from ..libs.settings import get_setting
from ..libs.storage import hook_config
from ..libs.users import (
    authenticate,
    change_password,
    create_user,
    normalize_username,
    resolve_oidc_user,
    serialize_user,
    update_avatar,
    update_profile,
)
from ..models import ApiToken, User
from ..models.base import now
from ..models.user import STATUS_DISABLED, STATUS_NORMAL, STATUS_PENDING
from ..utils.web import (
    clear_cookie_state,
    get_cookie_state,
    ok,
    set_cookie_state,
)

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)

RESET_SALT = "sapic-reset-password"
RESET_MAX_AGE = 600
AVATAR_MAX_BYTES = 2 * 1024 * 1024

#: OIDC state cookie; scoped to the redirect dance only.
OIDC_COOKIE = "sapic-oidc"
OIDC_SALT = "sapic-oidc-state"
OIDC_STATE_MAX_AGE = 600


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


def _oidc_hook(name: str):
    """Resolve an enabled hook that speaks the OIDC contract."""
    hook = get_hook_manager().get(name)
    if (
        hook is None
        or not hook.enabled
        or not callable(getattr(hook.module, "oidc_authorize_url", None))
        or not callable(getattr(hook.module, "oidc_exchange", None))
    ):
        raise ApiError("oidc provider is unavailable", ErrorCode.NOT_FOUND, 404)
    return hook


def _oidc_redirect_uri(name: str) -> str:
    return url_for("auth.oidc_callback", name=name, _external=True)


def _safe_next(value) -> str:
    """Only same-site paths are accepted as the post-login target."""
    path = str(value or "")
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    return path


@bp.get("/auth/oidc/<name>")
def oidc_start(name: str):
    """Kick off the authorization-code flow for a hook-based provider."""
    hook = _oidc_hook(name)
    state = secrets.token_urlsafe(24)
    try:
        location = hook.module.oidc_authorize_url(
            config=hook_config(name),
            redirect_uri=_oidc_redirect_uri(name),
            state=state,
        )
    except ValueError as exc:
        raise ApiError(str(exc), ErrorCode.PARAM_ERROR) from exc
    except Exception as exc:
        logger.exception("oidc provider %s is unreachable", name)
        raise ApiError(
            "oidc provider is unreachable", ErrorCode.BAD_GATEWAY, 502
        ) from exc

    response = redirect(location)
    return set_cookie_state(
        response,
        {"state": state, "next": _safe_next(request.args.get("next"))},
        OIDC_STATE_MAX_AGE,
        OIDC_COOKIE,
        OIDC_SALT,
    )


@bp.get("/auth/oidc/<name>/callback")
def oidc_callback(name: str):
    """Finish the flow: bind the identity, then start a normal session."""
    hook = _oidc_hook(name)
    if request.args.get("error"):
        return redirect("/login?oidc=denied")

    saved = get_cookie_state(OIDC_STATE_MAX_AGE, OIDC_COOKIE, OIDC_SALT)
    state = request.args.get("state") or ""
    if not isinstance(saved, dict) or not state or saved.get("state") != state:
        raise ApiError("invalid oidc state", ErrorCode.PARAM_ERROR)

    code = request.args.get("code")
    if not code:
        raise ApiError("missing oidc code", ErrorCode.PARAM_ERROR)

    try:
        identity = hook.module.oidc_exchange(
            config=hook_config(name),
            code=code,
            redirect_uri=_oidc_redirect_uri(name),
        )
    except Exception:
        logger.exception("oidc token exchange failed for %s", name)
        return redirect("/login?oidc=error")

    config = hook_config(name)
    review = bool(get_setting("register_review", False))
    try:
        user = resolve_oidc_user(
            issuer=identity.get("issuer") or config.get("issuer") or "",
            subject=identity.get("subject") or "",
            username=identity.get("username") or "",
            nickname=identity.get("nickname") or "",
            email=identity.get("email") or "",
            auto_register=as_bool(config.get("auto_register", True)),
            status=STATUS_PENDING if review else STATUS_NORMAL,
        )
    except ApiError:
        logger.warning("oidc login rejected for %s", name)
        return redirect("/login?oidc=error")

    login_user(user)
    response = redirect(_safe_next(saved.get("next")))
    return clear_cookie_state(response, OIDC_COOKIE)


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


@bp.post("/auth/avatar")
@login_required
def upload_avatar():
    """Store a cropped avatar in the user's default album."""
    file = request.files.get("file")
    if file is None or not file.filename:
        raise ApiError("file is required", ErrorCode.PARAM_ERROR)
    stream = file.stream.read()
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)
    if len(stream) > AVATAR_MAX_BYTES:
        raise ApiError(
            "avatar must be smaller than 2 MB", ErrorCode.PAYLOAD_TOO_LARGE, 413
        )

    user = update_avatar(g.user, file.filename, stream, file.mimetype or "")
    return ok(
        {"avatar": user.avatar, "user": serialize_user(user, True)}, status=201
    )


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
