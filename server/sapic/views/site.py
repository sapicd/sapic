# -*- coding: utf-8 -*-
"""Public site metadata consumed by the web front-end."""

from __future__ import annotations

from flask import Blueprint

from ..libs.mail import smtp_ready
from ..libs.settings import get_setting
from ..utils.web import ok
from ..version import __version__

bp = Blueprint("site", __name__)


@bp.get("/site")
def site():
    return ok(
        {
            "name": get_setting("site_name", "sapic"),
            "keywords": get_setting("site_keywords", ""),
            "description": get_setting("site_description", ""),
            "logo": get_setting("site_logo", ""),
            "background": get_setting("site_background", ""),
            "background_mobile": get_setting("site_background_mobile", ""),
            "background_opacity": get_setting("site_background_opacity", 0.6),
            "icp": get_setting("site_icp", ""),
            "footer": get_setting("site_footer", ""),
            "announcement": get_setting("site_announcement", ""),
            "login_notice": get_setting("login_notice", ""),
            "upload_notice": get_setting("upload_notice", ""),
            #: 关闭后前端把上传区标成「已暂停」，只挡新增，历史图片不受影响。
            "upload_enabled": bool(get_setting("upload_enabled", True)),
            #: 按媒体类型分开的单文件上限（MB）。
            "upload_image_max_size": get_setting("upload_image_max_size", 10),
            "upload_video_max_size": get_setting("upload_video_max_size", 20),
            "upload_count_limit": get_setting("upload_count_limit", 10),
            "upload_allowed_ext": get_setting("upload_allowed_ext", ""),
            "allow_video": bool(get_setting("allow_video", True)),
            #: 单位天：默认有效期与单图上限，0 表示永久 / 不限制。
            "image_expire_default_days": int(
                get_setting("image_expire_default_days", 0) or 0
            ),
            "image_expire_max_days": int(
                get_setting("image_expire_max_days", 0) or 0
            ),
            "plaza_enabled": bool(get_setting("plaza_enabled", False)),
            "allow_register": bool(get_setting("allow_register", True)),
            "password_login": bool(get_setting("password_login", True)),
            #: 只有配置了 SMTP 才能寄验证码/重置链接，前端据此隐藏不可用的入口。
            "mail_enabled": smtp_ready(),
            "allow_anonymous_upload": bool(
                get_setting("allow_anonymous_upload", False)
            ),
            "version": __version__,
        }
    )
