# -*- coding: utf-8 -*-
"""Public site metadata consumed by the web front-end."""

from __future__ import annotations

from flask import Blueprint

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
            "about": get_setting("site_about", ""),
            "upload_notice": get_setting("upload_notice", ""),
            "upload_max_size": get_setting("upload_max_size", 20),
            "upload_count_limit": get_setting("upload_count_limit", 10),
            "upload_allowed_ext": get_setting("upload_allowed_ext", ""),
            "allow_video": bool(get_setting("allow_video", True)),
            "allow_register": bool(get_setting("allow_register", True)),
            "allow_anonymous_upload": bool(
                get_setting("allow_anonymous_upload", False)
            ),
            "version": __version__,
        }
    )
