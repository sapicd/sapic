# -*- coding: utf-8 -*-
"""User creation and authentication."""

from __future__ import annotations

import logging
import re
import secrets

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from ..basis.db import db
from ..basis.errors import ApiError, ErrorCode
from ..models import (
    Album,
    AlbumShare,
    ApiToken,
    Image,
    StorageBackend,
    UploadTicket,
    User,
    UserBackend,
    UserSetting,
)
from ..models.base import now
from ..models.image import STATUS_ENABLED
from ..models.storage import SCOPE_USER
from ..models.user import (
    STATUS_DISABLED,
    STATUS_NORMAL,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from .albums import default_album
from .images import create_image, delete_image, image_src
from .mail import send_mail
from .settings import get_setting

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^[a-zA-Z][0-9a-zA-Z_]{3,31}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 6


def normalize_username(username: str) -> str:
    """Usernames are stored lower-case so PostgreSQL and MySQL agree."""
    return (username or "").strip().lower()


def validate_username(username: str) -> str:
    username = normalize_username(username)
    if not USERNAME_RE.match(username):
        raise ApiError(
            "username must be 4-32 chars, start with a letter",
            ErrorCode.PARAM_ERROR,
        )
    return username


def validate_password(password: str) -> str:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            "password must be at least %d characters" % MIN_PASSWORD_LENGTH,
            ErrorCode.PARAM_ERROR,
        )
    return password


def validate_email(email: str | None) -> str | None:
    if not email:
        return None
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError("invalid email address", ErrorCode.PARAM_ERROR)
    return email


def create_user(
    username: str,
    password: str,
    email: str | None = None,
    is_admin: bool = False,
    status: int = STATUS_NORMAL,
) -> User:
    """Create a user and their default album in one transaction."""
    username = validate_username(username)
    validate_password(password)
    email = validate_email(email)

    if User.get_or_none(User.username == username):
        raise ApiError("username already exists", ErrorCode.CONFLICT, 409)
    if email and User.get_or_none(User.email == email):
        raise ApiError("email already exists", ErrorCode.CONFLICT, 409)

    with db.atomic():
        user = User.create(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            nickname=username,
            is_admin=is_admin,
            status=status,
            labels=[],
            created_at=now(),
            updated_at=now(),
        )
        #: 权限以相册为维度，账号必须立刻拥有兜底相册。
        default_album(user)
    return user


def authenticate(username: str, password: str) -> User:
    """Verify credentials, returning the user or raising 401."""
    username = normalize_username(username)
    user = User.get_or_none(User.username == username)
    if user is None or not check_password_hash(user.password_hash, password):
        raise ApiError(
            "invalid username or password", ErrorCode.UNAUTHORIZED, 401
        )
    #: 只有正常状态的账号能登录；待审核/已拒绝的账号即便密码正确也不放行。
    if user.status == STATUS_PENDING:
        raise ApiError("account is pending review", ErrorCode.FORBIDDEN, 403)
    if user.status == STATUS_REJECTED:
        raise ApiError("account was rejected", ErrorCode.FORBIDDEN, 403)
    if user.status != STATUS_NORMAL:
        raise ApiError("account is disabled", ErrorCode.FORBIDDEN, 403)
    return user


def change_password(user: User, new_password: str) -> User:
    validate_password(new_password)
    user.password_hash = generate_password_hash(new_password)
    #: Revoke all existing sessions.
    user.session_version = (user.session_version or 0) + 1
    user.updated_at = now()
    user.save(only=[User.password_hash, User.session_version, User.updated_at])
    return user


def bind_oidc_identity(user: User, issuer: str, subject: str) -> User:
    """Attach an OIDC identity to an existing account.

    An identity may only serve one account, so re-binding it to someone else is
    rejected instead of silently stealing the login.
    """
    issuer = (issuer or "").strip()[:255]
    subject = (subject or "").strip()[:255]
    if not issuer or not subject:
        raise ApiError("invalid oidc identity", ErrorCode.PARAM_ERROR)

    bound = User.get_or_none(
        (User.oidc_issuer == issuer) & (User.oidc_subject == subject)
    )
    if bound is not None and bound.id != user.id:
        raise ApiError("identity is already bound", ErrorCode.CONFLICT, 409)

    user.oidc_issuer = issuer
    user.oidc_subject = subject
    user.updated_at = now()
    user.save(only=[User.oidc_issuer, User.oidc_subject, User.updated_at])
    return user


def unbind_oidc_identity(user: User) -> User:
    """Drop the OIDC identity so the account falls back to its password."""
    user.oidc_issuer = None
    user.oidc_subject = None
    user.updated_at = now()
    user.save(only=[User.oidc_issuer, User.oidc_subject, User.updated_at])
    return user


def _oidc_username(hint: str) -> str:
    """Derive a unique local username from the provider's claims."""
    base = re.sub(r"[^0-9a-zA-Z_]", "", hint or "")[:28]
    if not base or not base[0].isalpha():
        base = "u%s" % base
    base = base.ljust(4, "_")
    candidate = base
    index = 1
    while User.get_or_none(User.username == candidate):
        index += 1
        suffix = str(index)
        candidate = "%s%s" % (base[: 32 - len(suffix)], suffix)
    return candidate


def resolve_oidc_user(
    issuer: str,
    subject: str,
    username: str = "",
    nickname: str = "",
    email: str = "",
    email_verified: bool = False,
    status: int = STATUS_NORMAL,
) -> User:
    """Find the local account for an OIDC identity, creating it when needed.

    ``issuer``/``subject`` are persisted on the user row (see
    ``User.oidc_issuer``/``oidc_subject``), so a provider account maps back to
    the same local user even when the upstream display name changes.

    An identity already bound wins; otherwise a provider-verified email may
    link the identity to an existing verified account; anything else becomes a
    brand new local account (the main sign-up path for provider users).
    """
    issuer = (issuer or "").strip()[:255]
    subject = (subject or "").strip()[:255]
    if not issuer or not subject:
        raise ApiError("invalid oidc identity", ErrorCode.PARAM_ERROR)

    user = User.get_or_none(
        (User.oidc_issuer == issuer) & (User.oidc_subject == subject)
    )
    if user is not None:
        if user.status != STATUS_NORMAL:
            raise ApiError("account is not active", ErrorCode.FORBIDDEN, 403)
        return user

    email = (email or "").strip().lower() or None
    if email_verified and email:
        #: 两边都要验证过：provider 声明邮箱已验证，且本地账号的邮箱本身
        #: 通过过验证流程。否则等于允许「抢填他人邮箱」的账号被接管。
        local = User.get_or_none(User.email == email)
        if (
            local is not None
            and local.email_verified
            and not local.oidc_issuer
            and not local.oidc_subject
        ):
            if local.status != STATUS_NORMAL:
                raise ApiError("account is not active", ErrorCode.FORBIDDEN, 403)
            logger.info("oidc identity linked by email to user %s", local.username)
            return bind_oidc_identity(local, issuer, subject)

    if email and User.get_or_none(User.email == email):
        #: 邮箱已被本地账号占用时新建账号不抢这个地址，否则会撞唯一约束。
        email = None

    #: 新用户的正常入口：按 provider 信息建号，并立刻建好兜底相册。
    #: 账号名只取稳定标识（优先 provider 给的用户名，其次 subject/uid），
    #: 昵称会随用户改名而变化，只写进 nickname 作显示名。
    with db.atomic():
        user = User.create(
            username=_oidc_username(username or subject),
            email=email,
            #: OIDC 账号没有本地密码，随机值让密码登录不可能成功。
            password_hash=generate_password_hash(secrets.token_urlsafe(32)),
            nickname=(nickname or username or "")[:64],
            status=status,
            labels=[],
            oidc_issuer=issuer,
            oidc_subject=subject,
            created_at=now(),
            updated_at=now(),
        )
        default_album(user)
    return user


def mark_email_verified(user: User, email: str) -> User:
    """Mark the account's address verified once the mailed token checks out."""
    email = (email or "").strip().lower()
    if not user.email or email != user.email:
        raise ApiError("email does not match", ErrorCode.PARAM_ERROR)
    if not user.email_verified:
        user.email_verified = True
        user.updated_at = now()
        user.save(only=[User.email_verified, User.updated_at])
    return user


def update_profile(user: User, data: dict) -> User:
    """Update the fields a user may edit themselves.

    ``username`` is immutable: it is the login identifier and part of the
    upload path, so renaming it would orphan existing objects.
    """
    if data.get("nickname") is not None:
        user.nickname = (data["nickname"] or "").strip()[:64]
    if "email" in data:
        email = validate_email(data.get("email"))
        if email and User.get_or_none(
            (User.email == email) & (User.id != user.id)
        ):
            raise ApiError("email already exists", ErrorCode.CONFLICT, 409)
        if email != user.email:
            #: 换了地址就必须重新验证，旧地址的验证状态不能沿用。
            user.email_verified = False
        user.email = email
    if data.get("avatar") is not None:
        user.avatar = (data["avatar"] or "").strip()[:255]
    user.updated_at = now()
    user.save(
        only=[
            User.nickname,
            User.email,
            User.email_verified,
            User.avatar,
            User.updated_at,
        ]
    )
    return user


def update_avatar(
    user: User, filename: str, stream: bytes, mime: str = ""
) -> User:
    """Store a cropped avatar in the user's default album.

    Avatars are ordinary images: they inherit the album visibility, so the
    "上传即入默认相册" rule keeps the permission model intact.
    """
    if not stream:
        raise ApiError("empty file", ErrorCode.PARAM_ERROR)
    image = create_image(
        owner=user,
        filename=filename or "avatar.png",
        stream=stream,
        mime=mime or "image/png",
        album=default_album(user),
    )
    user.avatar = image_src(image)[:255]
    user.updated_at = now()
    user.save(only=[User.avatar, User.updated_at])
    return user


#: 审核结果邮件标题，状态值 → 文案。
REVIEW_SUBJECTS = {
    STATUS_NORMAL: "账号审核通过",
    STATUS_REJECTED: "账号审核未通过",
}


def notify_review(user: User, status: int, reason: str = "") -> bool:
    """Mail the review result to the applicant.

    Only verified mailboxes are used: an unverified address may belong to
    someone else. Delivery failures are swallowed by :func:`send_mail`, so a
    broken SMTP setup never turns a successful review into an error.
    """
    if not user.email or not user.email_verified:
        return False
    subject = REVIEW_SUBJECTS.get(status)
    if subject is None:
        return False

    site = str(get_setting("site_name", "sapic") or "sapic")
    base = str(current_app.config.get("EXTERNAL_BASE_URL") or "").rstrip("/")
    name = user.nickname or user.username
    if status == STATUS_NORMAL:
        body = "\n".join(
            [
                "%s，你好：" % name,
                "",
                "你在 %s 的注册申请已审核通过，现在可以登录了。" % site,
                "登录地址：%s/login" % base,
                "",
                "如果这不是你本人的操作，请忽略本邮件。",
            ]
        )
    else:
        body = "\n".join(
            [
                "%s，你好：" % name,
                "",
                "很遗憾，你在 %s 的注册申请未通过审核。" % site,
                "原因：%s" % (reason or "未填写"),
                "",
                "如有疑问，请联系站点管理员。",
            ]
        )
    return send_mail(user.email, "[%s] %s" % (site, subject), body)


def self_delete(user: User, password: str) -> None:
    """Delete the caller's own account after a password re-check.

    Two guards keep this from destroying data by accident: an admin cannot wipe
    the console's own entry point (another admin must do it), and an account
    still holding images has to delete them first — otherwise ``purge_user``
    would remove them without the owner ever seeing what went away.
    """
    if user.is_admin:
        raise ApiError(
            "admins cannot delete their own account", ErrorCode.FORBIDDEN, 403
        )
    if not password or not check_password_hash(user.password_hash or "", password):
        raise ApiError("password is incorrect", ErrorCode.FORBIDDEN, 403)

    owned = Image.select().where(
        (Image.owner == user) & (Image.status == STATUS_ENABLED)
    ).count()
    if owned:
        raise ApiError(
            "delete your %d image(s) before closing the account" % owned,
            ErrorCode.CONFLICT,
            409,
        )
    purge_user(user)


def purge_user(user: User) -> None:
    """Delete an account together with everything it owns.

    Unlike ``delete_image`` (soft delete), the rows go away for real: the
    username and the image ``sha`` have to become reusable, so replicas are
    removed from the storage backends first. Images other people uploaded into
    this account's albums are moved to their own default album instead of being
    dropped with the album.
    """
    album_ids = [album.id for album in Album.select().where(Album.owner == user)]
    personal = [
        backend.id
        for backend in StorageBackend.select().where(
            (StorageBackend.owner == user) & (StorageBackend.scope == SCOPE_USER)
        )
    ]

    with db.atomic():
        if album_ids:
            for image in Image.select().where(
                (Image.album.in_(album_ids)) & (Image.owner != user)
            ):
                if image.owner is not None:
                    image.album = default_album(image.owner)
                    image.save(only=[Image.album])

        for image in Image.select().where(Image.owner == user):
            delete_image(image)
            image.delete_instance()

        AlbumShare.delete().where(AlbumShare.grantee == user).execute()
        if album_ids:
            AlbumShare.delete().where(AlbumShare.album.in_(album_ids)).execute()
        UploadTicket.delete().where(UploadTicket.owner == user).execute()
        if album_ids:
            #: 别人的票据指向被删相册时只解除引用，票据本身留给其所有者。
            UploadTicket.update(album=None).where(
                UploadTicket.album.in_(album_ids)
            ).execute()
            Album.delete().where(Album.id.in_(album_ids)).execute()

        if personal:
            UploadTicket.update(backend=None).where(
                UploadTicket.backend.in_(personal)
            ).execute()
            UserBackend.delete().where(UserBackend.backend.in_(personal)).execute()
            StorageBackend.delete().where(StorageBackend.id.in_(personal)).execute()

        ApiToken.delete().where(ApiToken.owner == user).execute()
        UserSetting.delete().where(UserSetting.user == user).execute()
        UserBackend.delete().where(UserBackend.user == user).execute()
        user.delete_instance()


def serialize_user(user: User, include_private: bool = False) -> dict:
    data = {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "avatar": user.avatar,
        "is_admin": bool(user.is_admin),
        "status": user.status,
        "labels": list(user.labels or []),
        "email_verified": bool(user.email_verified),
        "created_at": user.created_at,
    }
    if include_private:
        data["email"] = user.email
        data["status_reason"] = user.status_reason or ""
    return data


__all__ = [
    "STATUS_DISABLED",
    "STATUS_NORMAL",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "authenticate",
    "change_password",
    "create_user",
    "normalize_username",
    "notify_review",
    "purge_user",
    "resolve_oidc_user",
    "serialize_user",
    "update_avatar",
    "update_profile",
]
