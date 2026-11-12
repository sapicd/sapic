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
from ..libs import ext
from ..libs.auth import (
    DEFAULT_PAT_SCOPES,
    PAT_SCOPES,
    SCOPE_ADMIN,
    current_csrf,
    current_user,
    generate_token,
    hash_token,
    login_required,
    login_user,
    logout_user,
    require_scope,
)
from ..libs.hook import get_hook_manager
from ..libs.mail import send_mail, smtp_ready
from ..libs.settings import get_setting
from ..libs.storage import hook_config
from ..libs.user_settings import get_user_settings, set_user_settings
from ..libs.users import (
    authenticate,
    bind_oidc_identity,
    change_password,
    create_user,
    mark_email_verified,
    normalize_username,
    resolve_oidc_user,
    self_delete,
    serialize_user,
    unbind_oidc_identity,
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
VERIFY_SALT = "sapic-verify-email"
VERIFY_MAX_AGE = 24 * 3600
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


def _verify_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=VERIFY_SALT)


def _mail_verification(user: User) -> str:
    """Mail a verification token, returning it for local/dev callers."""
    token = _verify_serializer().dumps({"uid": user.id, "email": user.email})
    send_mail(
        to=user.email,
        subject="验证邮箱",
        body="24 小时内有效，请提交以下令牌完成邮箱验证：\n\n%s\n" % token,
    )
    return token


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


def _password_login_enabled() -> bool:
    return bool(get_setting("password_login", True))


@bp.post("/auth/register")
def register():
    if not _password_login_enabled():
        raise ApiError("password login is disabled", ErrorCode.FORBIDDEN, 403)
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
    if user.email:
        #: 新注册的邮箱默认未验证，先寄一封；SMTP 未配置时只记日志。
        _mail_verification(user)
    return ok({"user": serialize_user(user, True)}, status=201)


@bp.post("/auth/login")
def login():
    if not _password_login_enabled():
        raise ApiError("password login is disabled", ErrorCode.FORBIDDEN, 403)
    data = _payload()
    user = authenticate(data.get("username", ""), data.get("password", ""))
    csrf = login_user(user)
    return ok({"user": serialize_user(user, True), "csrf": csrf})


#: Rejections are internal English messages; the login page localises the flags.
_OIDC_FAILURES = (
    ("not linked", "unlinked"),
    ("not active", "inactive"),
    ("invalid oidc identity", "invalid"),
)


def _oidc_failure_flag(exc: ApiError) -> str:
    """Map a rejection to a flag so the login page can explain what happened."""
    message = (exc.message or "").lower()
    for needle, flag in _OIDC_FAILURES:
        if needle in message:
            return flag
    return "error"


def _oidc_hook(name: str):
    """Resolve an enabled hook that implements the provider contract."""
    hook = get_hook_manager().get(name)
    #: 契约判断在 libs.ext：只要包声明 __catalog__="auth" 并实现两个函数，
    #: 第三方 Provider 无需改动核心代码即可接入 /auth/oidc/<name>。
    if hook is None or not hook.enabled or not ext.is_provider(hook.module):
        raise ApiError("oidc provider is unavailable", ErrorCode.NOT_FOUND, 404)
    return hook


def _oidc_redirect_uri(name: str) -> str:
    return url_for("auth.oidc_callback", name=name, _external=True)


def _safe_next(value) -> str:
    """Only same-site paths are accepted as the post-login target."""
    path = str(value or "")
    #: 浏览器把 `\` 归一成 `/`，所以 `/\evil.com` 等同 `//evil.com`。
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return "/"
    return path


def _with_flag(path: str, key: str, value: str) -> str:
    """Append a query flag to a same-site path, keeping existing params."""
    return "%s%s%s=%s" % (path, "&" if "?" in path else "?", key, value)


def _finish_bind(name: str, issuer: str, subject: str, bind_uid: int, saved: dict):
    """Link the identity returned by the provider to the signed-in account."""
    user = current_user()
    if user is None or user.id != bind_uid:
        raise ApiError("login is required to bind", ErrorCode.UNAUTHORIZED, 401)

    target = _safe_next(saved.get("next"))
    try:
        bind_oidc_identity(user, issuer, subject)
    except ApiError as exc:
        logger.warning("oidc bind rejected for %s: %s", name, exc.message)
        #: 身份已被别的账号占用时给独立标记，页面才能提示「先去那边解绑」，
        #: 否则只能看到笼统的「绑定失败」。
        flag = "conflict" if exc.code == ErrorCode.CONFLICT else "error"
        response = redirect(_with_flag(target, "identity", flag))
    else:
        logger.info("oidc identity %s bound to user %s", name, user.username)
        response = redirect(_with_flag(target, "identity", "bound"))
    return clear_cookie_state(response, OIDC_COOKIE)


@bp.get("/auth/oidc/<name>")
def oidc_start(name: str):
    """Kick off the authorization-code flow for a hook-based provider."""
    hook = _oidc_hook(name)
    user = current_user()
    binding = as_bool(request.args.get("bind"))
    if binding and user is None:
        raise ApiError("login is required to bind", ErrorCode.UNAUTHORIZED, 401)

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
            "oidc provider is unreachable", ErrorCode.SERVICE_UNAVAILABLE, 502
        ) from exc

    payload = {"state": state, "next": _safe_next(request.args.get("next"))}
    if binding:
        payload["bind_uid"] = user.id
    response = redirect(location)
    return set_cookie_state(
        response, payload, OIDC_STATE_MAX_AGE, OIDC_COOKIE, OIDC_SALT
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

    config = hook_config(name)
    try:
        claims = hook.module.oidc_exchange(
            config=config,
            code=code,
            redirect_uri=_oidc_redirect_uri(name),
        )
    except ValueError as exc:
        #: 与 Provider 的对话失败（discovery / token / userinfo）和「claims 缺
        #: subject」是两类问题：分开处理，页面才不会把「令牌交换失败」说成
        #: 「Provider 没返回 subject」，日志里也能看到上游返回的状态与原因。
        logger.warning("oidc provider %s rejected the exchange: %s", name, exc)
        return redirect("/login?oidc=provider")
    except Exception:
        logger.exception("oidc token exchange failed for %s", name)
        return redirect("/login?oidc=error")

    try:
        identity = ext.normalize_identity(claims)
    except ValueError as exc:
        #: 第三方 Provider 返回的 claims 缺 subject 时不能落库，按无效身份处理。
        logger.warning("oidc provider %s returned an invalid identity: %s", name, exc)
        return redirect("/login?oidc=invalid")

    #: 命名空间以 provider_issuer 为准：它是账号页判定「已绑定」时比对的同一
    #: 个值，用 claims 里的 iss 会让写入与比对不一致（比如末尾斜杠不同）。
    issuer = ext.provider_issuer(hook.module, config) or identity["issuer"]
    subject = identity["subject"]
    bind_uid = saved.get("bind_uid")
    if bind_uid:
        return _finish_bind(name, issuer, subject, bind_uid, saved)

    review = bool(get_setting("register_review", False))
    try:
        user = resolve_oidc_user(
            issuer=issuer,
            subject=subject,
            username=identity["username"],
            nickname=identity["nickname"],
            email=identity["email"],
            email_verified=identity["email_verified"],
            status=STATUS_PENDING if review else STATUS_NORMAL,
        )
    except ApiError as exc:
        logger.warning("oidc login rejected for %s: %s", name, exc.message)
        return redirect("/login?oidc=%s" % _oidc_failure_flag(exc))

    #: 走审核的站点里，新号是待审核状态，不能直接发会话。
    if user.status != STATUS_NORMAL:
        return redirect("/login?oidc=inactive")
    login_user(user)
    response = redirect(_safe_next(saved.get("next")))
    return clear_cookie_state(response, OIDC_COOKIE)


@bp.get("/auth/identities")
@login_required
def read_identities():
    """List sign-in providers and whether this account is linked to them."""
    user = current_user()
    manager = get_hook_manager()
    items = []
    for name, hook in sorted(manager.hooks.items()):
        #: 任何满足 Provider 契约的第三方钩子都会出现在这里，无需核心登记。
        if not hook.enabled or not ext.is_provider(hook.module):
            continue
        namespace = ext.provider_issuer(hook.module, hook_config(name))
        items.append(
            {
                "name": name,
                "title": (manager.manifest(name) or {}).get("title") or name,
                "bound": bool(
                    user.oidc_subject
                    and namespace
                    and ext.normalize_issuer(user.oidc_issuer) == namespace
                ),
                "bind_url": url_for(
                    "auth.oidc_start", name=name, bind=1, next="/settings"
                ),
            }
        )
    return ok({"items": items})


@bp.delete("/auth/identities/<name>")
@login_required
def unbind_identity(name: str):
    """Unlink a provider after re-checking the password.

    Requiring the password keeps OIDC-only accounts (random local password) from
    locking themselves out by removing their only sign-in method.
    """
    _oidc_hook(name)
    user = current_user()
    password = str(_payload().get("password") or "")
    if not password or not check_password_hash(
        user.password_hash or "", password
    ):
        raise ApiError("password is incorrect", ErrorCode.FORBIDDEN, 403)
    unbind_oidc_identity(user)
    return ok({"unbound": True})


@bp.post("/auth/logout")
@login_required
def logout():
    logout_user()
    return ok({"logged_out": True})


@bp.delete("/auth/account")
@login_required
def delete_account():
    """Self-service account deletion.

    ``self_delete`` requires the current password and an empty gallery; admins
    cannot remove themselves (another admin has to do it) so the console never
    ends up without an owner.
    """
    user = current_user()
    self_delete(user, str(_payload().get("password") or ""))
    logout_user()
    logger.info("Account %s deleted itself", user.username)
    return ok({"deleted": True})


@bp.post("/auth/password/forgot")
def forgot_password():
    data = _payload()
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise ApiError("email is required", ErrorCode.PARAM_ERROR)

    user = User.get_or_none(User.email == email)
    reset_token = None
    #: 只有验证过的邮箱才允许找回密码，未验证地址可能只是被别人填进账号。
    if (
        user is not None
        and user.email_verified
        and user.status != STATUS_DISABLED
    ):
        reset_token = _reset_token(user)
        send_mail(
            to=user.email,
            subject="重置密码",
            body="10 分钟内有效，请访问重置密码页面并提交以下令牌：\n\n%s\n" % reset_token,
        )

    payload = {"sent": True}
    #: Without SMTP configured, expose the token to local/dev clients only.
    if reset_token and not smtp_ready():
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


@bp.post("/auth/email/verify")
@login_required
def send_email_verification():
    """Mail a verification token to the account's current address."""
    user = g.user
    if not user.email:
        raise ApiError("email is not set", ErrorCode.PARAM_ERROR)
    if user.email_verified:
        raise ApiError("email is already verified", ErrorCode.CONFLICT, 409)

    token = _mail_verification(user)
    payload = {"sent": True}
    if not smtp_ready():
        #: 本地/测试环境没有邮件服务，直接把令牌回给调用方；线上则明确报错，
        #: 不能假装「已发送」让用户等一封永远到不了的邮件。
        if current_app.config.get("TESTING") or current_app.debug:
            payload["verify_token"] = token
        else:
            raise ApiError(
                "mail service is not configured",
                ErrorCode.SERVICE_UNAVAILABLE,
                503,
            )
    return ok(payload, status=202)


@bp.post("/auth/email/confirm")
def confirm_email():
    """Mark the address verified once the mailed token checks out."""
    token = (_payload().get("token") or "").strip()
    if not token:
        raise ApiError("token is required", ErrorCode.PARAM_ERROR)
    try:
        claims = _verify_serializer().loads(token, max_age=VERIFY_MAX_AGE)
    except SignatureExpired as exc:
        raise ApiError("verification token expired", ErrorCode.PARAM_ERROR) from exc
    except BadSignature as exc:
        raise ApiError("invalid verification token", ErrorCode.PARAM_ERROR) from exc

    user = User.get_or_none(User.id == claims.get("uid"))
    if user is None:
        raise ApiError("invalid verification token", ErrorCode.PARAM_ERROR)
    mark_email_verified(user, claims.get("email") or "")
    logger.info("email verified for user %s", user.username)
    return ok({"verified": True, "user": serialize_user(user, True)})


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


@bp.get("/auth/settings")
@login_required
def read_settings():
    """Per-user preferences: userscript switch and personal background."""
    return ok({"settings": get_user_settings(g.user)})


@bp.put("/auth/settings")
@login_required
def edit_settings():
    return ok({"settings": set_user_settings(g.user, _payload())})


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


def _token_scopes(value) -> list[str]:
    """Validate the requested scopes; only an omitted value falls back to the default set."""
    if value is None:
        return list(DEFAULT_PAT_SCOPES)
    if not isinstance(value, list):
        raise ApiError("scopes must be a list", ErrorCode.PARAM_ERROR)
    scopes: list[str] = []
    for item in value:
        scope = str(item).strip()
        if scope not in PAT_SCOPES:
            raise ApiError("invalid scope", ErrorCode.PARAM_ERROR)
        if scope not in scopes:
            scopes.append(scope)
    if not scopes:
        raise ApiError("at least one scope is required", ErrorCode.PARAM_ERROR)
    if SCOPE_ADMIN in scopes:
        if not g.user.is_admin:
            raise ApiError("admin scope requires an admin account", ErrorCode.FORBIDDEN, 403)
        #: 签发 admin 令牌要求当前凭据本身带 admin，否则 write 令牌即可给自己提权。
        require_scope(SCOPE_ADMIN)
    return scopes


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

    scopes = _token_scopes(data.get("scopes"))
    row = ApiToken.create(
        owner=g.user,
        name=(data.get("name") or "")[:64],
        token_hash=hash_token(token),
        prefix=token[:10],
        scopes=scopes,
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
