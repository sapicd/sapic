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
    #: 默认关闭：个人自建图床用不到「被陌生人发现」这套逻辑，公开 UGC 还会带来
    #: 内容审核与投诉成本；面向社区/作品集的部署（含专业版）再在后台开启。
    "plaza_enabled": False,
    #: 上传
    "allow_anonymous_upload": False,
    "upload_notice": "",
    "upload_allowed_ext": "jpg,jpeg,png,gif,webp,bmp,ico,svg,mp4,webm,mov",
    #: 单文件大小上限（MB），按媒体类型分开：视频通常比图片大。
    "upload_image_max_size": 10,
    "upload_video_max_size": 20,
    "upload_count_limit": 10,
    "allow_video": True,
    #: URL 上传的抓取代理，兜底用：直连抓不到（被墙 / 本地解析不了）才走它。
    #: 填一个 ``http(s)://[user:pass@]host:port``，留空表示只用直连；
    #: 存储后端的内部地址永远不走代理。
    "upload_fetch_proxy": "",
    #: 图片有效期（天）。``default`` 是客户端未指定时给新图设的寿命，
    #: ``max`` 是单图允许申请的上限；两者 0 都表示不启用该规则（默认永久）。
    #: 上限生效后「永久图片」被禁止，未指定时按上限处理。
    "image_expire_default_days": 0,
    "image_expire_max_days": 0,
    #: 上传只同步写 priority 数值最小的后端（数值越小越优先），其余启用的
    #: 后端在后台异步补副本。
    #: 关掉后只保留单副本（省空间/流量），失败也不会影响上传结果。
    "storage_replica": True,
    #: 系统
    "allow_register": True,
    "register_review": False,
    #: 关闭后只允许 OIDC 等外部身份登录，本地注册与密码登录一并停用。
    "password_login": True,
    #: 是否允许用户使用自己定义的存储后端（scope=user）。默认关：v2 目前只开放
    #: 管理员维护的系统后端，该开关与 libs/storage.list_backends 的 scope 判断配套，
    #: 关着时即使库里有用户后端行也不会被上传链路选中。
    "allow_user_backends": False,
    #: 每个用户最多能建几个自定义存储后端。
    "user_backend_limit": 3,
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
