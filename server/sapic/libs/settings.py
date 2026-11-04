# -*- coding: utf-8 -*-
"""Site settings persisted in the ``settings`` table."""

from __future__ import annotations

from ..models import Setting
from ..models.base import now

DEFAULTS = {
    #: 站点展示
    "site_name": "sapic",
    "site_keywords": "",
    "site_description": "",
    "site_logo": "",
    "site_background": "",
    "site_background_mobile": "",
    "site_background_opacity": 0.6,
    "site_icp": "",
    "site_footer": "SaintIC. All rights reserved.",
    "site_announcement": "",
    "site_about": "",
    #: 是否开放图片广场（只有主动发布的公开图片会出现在里面）。
    "plaza_enabled": True,
    #: 上传
    "allow_anonymous_upload": False,
    "upload_notice": "",
    "upload_allowed_ext": "jpg,jpeg,png,gif,webp,bmp,ico,svg,mp4,webm,mov",
    "upload_max_size": 20,
    "upload_count_limit": 10,
    "allow_video": True,
    #: 系统
    "allow_register": True,
    "register_review": False,
    #: 关闭后只允许 OIDC 等外部身份登录，本地注册与密码登录一并停用。
    "password_login": True,
    "forbidden_username": "admin,root,sys,anonymous",
    #: 默认相册是上传的兜底归属，默认公开才能拿到可外链地址。
    "default_album_visibility": "public",
    "external_base_url": "",
    "smtp": {},
    #: 钩子：启用状态（{name: bool}）、配置（{name: {key: value}}）与第三方
    #: 钩子模块名（[module]），由 /api/v2/hooks 系列接口写入，不走键白名单。
    "hooks_state": {},
    "hooks_config": {},
    "hooks_imported": [],
}


def get_setting(key: str, default=None):
    """Read a setting, falling back to built-in defaults."""
    row = Setting.get_or_none(Setting.key == key)
    if row is None:
        return DEFAULTS.get(key, default)
    return row.value


def set_setting(key: str, value):
    """Create or update a setting."""
    row = Setting.get_or_none(Setting.key == key)
    if row is None:
        return Setting.create(key=key, value=value, updated_at=now())
    row.value = value
    row.updated_at = now()
    row.save(only=[Setting.value, Setting.updated_at])
    return row
