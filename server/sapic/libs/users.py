# -*- coding: utf-8 -*-
"""User creation and authentication."""

from __future__ import annotations

import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from ..basis.db import db
from ..basis.errors import ApiError, ErrorCode
from ..models import User
from ..models.base import now
from ..models.user import (
    STATUS_DISABLED,
    STATUS_NORMAL,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from .albums import default_album
from .images import create_image, public_url

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
    if user.status == STATUS_DISABLED:
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
    auto_register: bool = True,
    status: int = STATUS_NORMAL,
) -> User:
    """Find the local account bound to an OIDC identity, creating it if allowed.

    ``issuer``/``subject`` are persisted on the user row (see
    ``User.oidc_issuer``/``oidc_subject``), so a provider account maps back to
    the same local user even when the upstream display name changes.
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

    if not auto_register:
        raise ApiError("account is not linked", ErrorCode.FORBIDDEN, 403)

    email = (email or "").strip().lower() or None
    if email and User.get_or_none(User.email == email):
        #: 邮箱已被本地账号占用时不自动合并，避免他人的账号被接管。
        email = None

    with db.atomic():
        user = User.create(
            username=_oidc_username(username or nickname),
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
        #: 权限以相册为维度，账号必须立刻拥有兜底相册。
        default_album(user)
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
        user.email = email
    if data.get("avatar") is not None:
        user.avatar = (data["avatar"] or "").strip()[:255]
    user.updated_at = now()
    user.save(only=[User.nickname, User.email, User.avatar, User.updated_at])
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
    user.avatar = public_url(image.sha)[:255]
    user.updated_at = now()
    user.save(only=[User.avatar, User.updated_at])
    return user


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
    "resolve_oidc_user",
    "serialize_user",
    "update_avatar",
    "update_profile",
]
