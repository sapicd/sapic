# -*- coding: utf-8 -*-
"""OpenAPI 3.0 document generated from the live route table.

Routes come from ``app.url_map``, so a new blueprint can never silently fall
behind the document: endpoints missing from :data:`OPERATIONS` are still listed
(with ``x-undocumented``) and only lack the hand-written details. Descriptions
live in one table instead of docstrings on 70+ views, which keeps this module
the single place to touch when an endpoint changes.
"""

from __future__ import annotations

import re
from typing import Any

from flask import Flask

from ..version import __version__

_REF_PREFIX = "#/components/schemas/"

#: Flask converter → JSON Schema type. ``any``/``string`` fall back to string.
_CONVERTER_TYPES = {"int": "integer", "float": "number", "path": "string"}

#: 不进文档的端点：文档只描述 JSON API。根路径是服务标识探针、油猴脚本返回
#: ``text/javascript``、Swagger 页面本身是 HTML、``/i`` 是 302 跳转、``/raw`` 输出
#: 图片字节——它们都没有 JSON 契约，Swagger UI 里既没有 schema 也试不了请求，列出来只是噪音。
HIDDEN_ENDPOINTS = {
    "index",
    "userscript.script",
    "docs.swagger_ui",
    "public.legacy_image",
    "public.image",
}

#: 整块不进文档的蓝图：管理员接口（站点设置 / 用户 / 存储后端）与钩子插件接口这一版
#: 不对外提供文档，连路由也不列。等它们稳定后再从集合里移除，并在 ``OPERATIONS`` 里补描述。
HIDDEN_BLUEPRINTS = {"settings", "users", "backends", "hooks"}


# --------------------------------------------------------------------- schemas


def _ref(name: str) -> dict:
    return {"$ref": _REF_PREFIX + name}


def _array(items: dict) -> dict:
    return {"type": "array", "items": items}


def _nullable(schema: dict) -> dict:
    return {**schema, "nullable": True}


_STRING = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_TS = {"type": "integer", "description": "10 位 Unix 时间戳（秒）"}
_FILE = {"type": "string", "format": "binary"}

SCHEMAS: dict[str, dict] = {
    "ErrorEnvelope": {
        "type": "object",
        "description": "失败响应：`code` 是错误枚举名（如 `NOT_FOUND`），`data` 为 null",
        "properties": {
            "code": {"type": "string", "example": "NOT_FOUND"},
            "message": {"type": "string", "example": "album not found"},
            "data": _nullable({"type": "object"}),
        },
    },
    "User": {
        "type": "object",
        "properties": {
            "id": _INT,
            "username": _STRING,
            "nickname": _STRING,
            "avatar": _STRING,
            "is_admin": _BOOL,
            "status": {"type": "integer", "description": "-2 已拒绝 / -1 待审核 / 0 已禁用 / 1 正常"},
            "labels": _array(_STRING),
            "email_verified": _BOOL,
            "created_at": _TS,
            "email": _nullable(_STRING),
            "status_reason": _STRING,
        },
    },
    "Session": {
        "type": "object",
        "properties": {
            "authenticated": _BOOL,
            "user": {"allOf": [_ref("User")], "nullable": True},
            "csrf": {
                "type": "string",
                "nullable": True,
                "description": "写操作要带回 `X-CSRF-Token` 头（仅 Cookie 会话需要）",
            },
        },
    },
    "LoginPayload": {
        "type": "object",
        "properties": {"user": _ref("User"), "csrf": _STRING},
    },
    "Image": {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "sha": {"type": "string", "description": "公开标识，`/raw/<sha>` 用它"},
            "filename": _STRING,
            "title": _STRING,
            "size": _INT,
            "mime": _STRING,
            "is_video": _BOOL,
            "width": _nullable(_INT),
            "height": _nullable(_INT),
            "visibility": _nullable({"type": "string", "enum": ["public", "private"]}),
            "plaza": _nullable(_BOOL),
            "plaza_effective": _BOOL,
            "tags": _array(_STRING),
            "album_id": _INT,
            "created_at": _TS,
            "expire_at": _nullable(_TS),
            "external": {"type": "boolean", "description": "外链登记（未下载字节）"},
            "src": {"type": "string", "description": "图片地址，公开图优先给存储直链"},
            "thumb": _nullable(_STRING),
            "tpl": {"type": "object", "description": "分享模板：URL / HTML / Markdown / rST"},
            "can_edit": _BOOL,
        },
    },
    "ImagePayload": {
        "type": "object",
        "properties": {"image": _ref("Image")},
    },
    "ImageList": {
        "type": "object",
        "description": "游标模式给 `next_cursor` / `has_more` / `limit`，页码模式给 `total` / `page` / `page_size`",
        "properties": {
            "items": _array(_ref("Image")),
            "next_cursor": _nullable(_STRING),
            "has_more": _BOOL,
            "limit": _INT,
            "total": _INT,
            "page": _INT,
            "page_size": _INT,
        },
    },
    "Album": {
        "type": "object",
        "properties": {
            "id": _INT,
            "name": _STRING,
            "description": _STRING,
            "visibility": {"type": "string", "enum": ["public", "private", "shared"]},
            "plaza": _BOOL,
            "cover_sha": _nullable(_STRING),
            "image_count": _INT,
            "role": {"type": "string", "enum": ["owner", "shared", "system"]},
            "permission": _nullable({"type": "string", "enum": ["read", "write"]}),
            "is_default": _BOOL,
            "is_system": _BOOL,
            "created_at": _TS,
            "updated_at": _TS,
        },
    },
    "AlbumPayload": {"type": "object", "properties": {"album": _ref("Album")}},
    "AlbumList": {
        "type": "object",
        "properties": {"items": _array(_ref("Album"))},
    },
    "Share": {
        "type": "object",
        "properties": {
            "user_id": _INT,
            "username": _STRING,
            "nickname": _STRING,
            "permission": {"type": "string", "enum": ["read", "write"]},
            "expires_at": _nullable(_TS),
            "created_at": _TS,
        },
    },
    "SharePayload": {
        "type": "object",
        "properties": {"share": _ref("Share"), "album": _ref("Album")},
    },
    "ShareList": {"type": "object", "properties": {"items": _array(_ref("Share"))}},
    "Token": {
        "type": "object",
        "properties": {
            "id": _INT,
            "name": _STRING,
            "prefix": {"type": "string", "description": "令牌前 10 位，用于辨认"},
            "scopes": _array({"type": "string", "enum": ["read", "upload", "write", "admin"]}),
            "album_id": _nullable(_INT),
            "album_name": {"type": "string", "description": "空串表示跟随用户默认相册"},
            "expires_at": _nullable(_TS),
            "last_used_at": _nullable(_TS),
            "created_at": _TS,
            "revoked": _BOOL,
        },
    },
    "TokenPayload": {
        "type": "object",
        "description": "`token` 只在这里出现一次，之后无法再取回",
        "properties": {"id": _INT, "token": _STRING, "prefix": _STRING},
    },
    "TokenList": {"type": "object", "properties": {"items": _array(_ref("Token"))}},
    "UserPayload": {"type": "object", "properties": {"user": _ref("User")}},
    "SiteInfo": {
        "type": "object",
        "description": "前台展示用的站点配置（`/api/v2/site`）",
        "properties": {
            "name": _STRING,
            "keywords": _STRING,
            "description": _STRING,
            "logo": _STRING,
            "background": _STRING,
            "background_mobile": _STRING,
            "background_opacity": {"type": "number"},
            "icp": _STRING,
            "footer": _STRING,
            "announcement": {"type": "string", "description": "纯文本 + `**加粗**` / `[文字](链接)`"},
            "login_notice": _STRING,
            "upload_notice": _STRING,
            "upload_enabled": _BOOL,
            "upload_image_max_size": _INT,
            "upload_video_max_size": _INT,
            "upload_count_limit": _INT,
            "upload_allowed_ext": _STRING,
            "allow_video": _BOOL,
            "image_expire_default_days": _INT,
            "image_expire_max_days": _INT,
            "plaza_enabled": _BOOL,
            "allow_register": _BOOL,
            "password_login": _BOOL,
            "mail_enabled": _BOOL,
            "allow_anonymous_upload": _BOOL,
            "version": _STRING,
        },
    },
    "HealthInfo": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ok", "degraded"]},
            "version": _STRING,
            "database": _BOOL,
        },
    },
}

SECURITY_SCHEMES: dict[str, dict] = {
    "session": {
        "type": "apiKey",
        "in": "cookie",
        "name": "sapic_sid",
        "description": "浏览器登录会话；写操作还要带 `X-CSRF-Token` 头",
    },
    "pat": {
        "type": "http",
        "scheme": "bearer",
        "description": "个人访问令牌（`sp_...`），不同端点要求不同 scope",
    },
}

TAGS = [
    {"name": "站点", "description": "公开站点配置与健康检查"},
    {"name": "认证", "description": "会话、注册登录、邮箱验证与访问令牌"},
    {"name": "上传", "description": "图片/视频上传"},
    {"name": "图片", "description": "个人图库：查询、修改、删除"},
    {"name": "相册", "description": "相册与共享授权"},
    {"name": "广场", "description": "公开图片广场（站点开启后才有数据）"},
    {"name": "待补文档", "description": "路由存在但尚未编写文档"},
]


# ------------------------------------------------------------------- metadata


def _q(
    name: str,
    description: str,
    type_: str = "string",
    required: bool = False,
    **extra: Any,
) -> dict:
    return {
        "name": name,
        "in": "query",
        "required": required,
        "description": description,
        "schema": {"type": type_, **extra},
    }


def _json_body(properties: dict[str, dict], required: tuple[str, ...] = ()) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = list(required)
    return {
        "required": bool(required),
        "content": {"application/json": {"schema": schema}},
    }


def _form_body(properties: dict[str, dict], required: tuple[str, ...] = ()) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = list(required)
    return {
        "required": bool(required),
        "content": {"multipart/form-data": {"schema": schema}},
    }


_CURSOR_PARAMS = [
    _q("limit", "每页数量（默认 20，最多 100）", "integer"),
    _q("cursor", "上一页返回的 `next_cursor`"),
]

_PAGE_PARAMS = [
    _q("page", "页码，从 1 开始；带 `page` 时返回页码模式"),
    _q("page_size", "每页数量（默认 15）", "integer"),
]

_VISIBILITY = {"type": "string", "enum": ["public", "private"]}

OPERATIONS: dict[str, dict] = {
    # ------------------------------------------------------------- 站点
    "health.health": {
        "summary": "健康检查",
        "tag": "站点",
        "auth": "none",
        "description": "数据库探活；不可用时返回 503 与 `code=SERVICE_UNAVAILABLE`。",
        "data": _ref("HealthInfo"),
    },
    "site.site": {
        "summary": "站点公开配置",
        "tag": "站点",
        "auth": "none",
        "description": "前端启动时读取，匿名可访问。",
        "data": _ref("SiteInfo"),
    },
    "docs.openapi_json": {
        "summary": "OpenAPI 文档",
        "tag": "站点",
        "auth": "none",
        "description": "本页展示的文档源，可直接导入 Apifox / Postman / Insomnia。",
        "data": {"type": "object", "description": "OpenAPI 3.0 文档"},
    },
    # ------------------------------------------------------------- 认证
    "auth.read_session": {
        "summary": "当前会话",
        "tag": "认证",
        "auth": "none",
        "description": "未登录时返回 `authenticated=false`；PAT 鉴权同样算已认证。",
        "data": _ref("Session"),
    },
    "auth.csrf_token": {
        "summary": "读取当前 CSRF 令牌",
        "tag": "认证",
        "auth": "login",
        "data": {
            "type": "object",
            "properties": {"csrf": _STRING},
        },
    },
    "auth.register": {
        "summary": "注册",
        "tag": "认证",
        "auth": "none",
        "status": 201,
        "description": "关闭注册或 `register_review` 打开时行为不同：后者建号后是待审核状态。",
        "body": _json_body(
            {
                "username": _STRING,
                "password": _STRING,
                "email": _STRING,
            },
            ("username", "password"),
        ),
        "data": _ref("UserPayload"),
        "errors": {403: "注册或密码登录已关闭", 409: "用户名/邮箱已被占用"},
    },
    "auth.login": {
        "summary": "登录",
        "tag": "认证",
        "auth": "none",
        "body": _json_body({"username": _STRING, "password": _STRING}, ("username", "password")),
        "data": _ref("LoginPayload"),
        "errors": {401: "用户名或密码错误", 403: "账号待审核/已禁用/未开放密码登录"},
    },
    "auth.logout": {
        "summary": "退出登录",
        "tag": "认证",
        "auth": "login",
        "data": {"type": "object", "properties": {"logged_out": _BOOL}},
    },
    "auth.oidc_start": {
        "summary": "发起统一登录",
        "tag": "认证",
        "auth": "none",
        "redirect": True,
        "path": {"name": "Provider 名（见 `/auth/identities`）"},
    },
    "auth.oidc_callback": {
        "summary": "统一登录回调",
        "tag": "认证",
        "auth": "none",
        "redirect": True,
        "path": {"name": "Provider 名"},
        "params": [_q("code", "Provider 回传的授权码"), _q("state", "防重放状态值")],
    },
    "auth.read_identities": {
        "summary": "可用的第三方登录",
        "tag": "认证",
        "auth": "login",
        "data": {
            "type": "object",
            "properties": {
                "items": _array(
                    {
                        "type": "object",
                        "properties": {
                            "name": _STRING,
                            "title": _STRING,
                            "bound": _BOOL,
                        },
                    }
                )
            },
        },
    },
    "auth.unbind_identity": {
        "summary": "解绑第三方身份",
        "tag": "认证",
        "auth": "login",
        "path": {"name": "Provider 名"},
        "body": _json_body({"password": _STRING}, ("password",)),
        "errors": {400: "该身份未绑定", 403: "密码错误"},
    },
    "auth.delete_account": {
        "summary": "自助注销",
        "tag": "认证",
        "auth": "login",
        "description": "必须提交当前密码；名下还有未删除的图片时直接 409，管理员不能自删。",
        "body": _json_body({"password": _STRING}, ("password",)),
        "data": {"type": "object", "properties": {"deleted": _BOOL}},
        "errors": {403: "密码错误或账号是管理员", 409: "名下还有图片"},
    },
    "auth.forgot_password": {
        "summary": "发送重置邮件",
        "tag": "认证",
        "auth": "none",
        "status": 202,
        "description": "邮箱未验证或未配置 SMTP 时不会签发令牌，但响应一致。",
        "body": _json_body({"email": _STRING}, ("email",)),
    },
    "auth.reset_password": {
        "summary": "用令牌重置密码",
        "tag": "认证",
        "auth": "none",
        "body": _json_body({"token": _STRING, "password": _STRING}, ("token", "password")),
        "data": {"type": "object", "properties": {"reset": _BOOL}},
        "errors": {400: "令牌无效或已过期"},
    },
    "auth.send_email_verification": {
        "summary": "重新发送邮箱验证",
        "tag": "认证",
        "auth": "login",
        "data": {"type": "object", "properties": {"sent": _BOOL, "verify_token": _STRING}},
        "errors": {503: "站点未配置 SMTP"},
    },
    "auth.confirm_email": {
        "summary": "提交邮箱验证令牌",
        "tag": "认证",
        "auth": "login",
        "body": _json_body({"token": _STRING}, ("token",)),
        "data": {
            "type": "object",
            "properties": {"verified": _BOOL, "user": _ref("User")},
        },
        "errors": {400: "令牌无效或已过期"},
    },
    "auth.upload_avatar": {
        "summary": "上传头像（服务端裁剪后写入）",
        "tag": "认证",
        "auth": "login",
        "status": 201,
        "form": _form_body({"file": _FILE}, ("file",)),
        "data": {"type": "object", "properties": {"avatar": _STRING, "user": _ref("User")}},
        "errors": {413: "超过 2 MB"},
    },
    "auth.edit_profile": {
        "summary": "修改资料",
        "tag": "认证",
        "auth": "login",
        "description": "`username` 不可改；换邮箱后 `email_verified` 会重置为 false。",
        "body": _json_body({"nickname": _STRING, "email": _STRING, "avatar": _STRING}),
        "data": _ref("UserPayload"),
        "errors": {409: "邮箱已被占用"},
    },
    "auth.read_settings": {
        "summary": "个人偏好",
        "tag": "认证",
        "auth": "login",
        "data": {"type": "object", "properties": {"settings": {"type": "object"}}},
    },
    "auth.edit_settings": {
        "summary": "保存个人偏好",
        "tag": "认证",
        "auth": "login",
        "description": "键与默认值见 `libs/user_settings.py`；未知键直接 400。",
        "body": _json_body(
            {
                "userscript_enabled": _BOOL,
                "bg_image": _STRING,
                "bg_image_mobile": _STRING,
                "bg_opacity": _nullable({"type": "number"}),
                "hotlink_enabled": _BOOL,
                "hotlink_allow_hosts": _STRING,
                "hotlink_allow_empty": _BOOL,
            }
        ),
        "data": {"type": "object", "properties": {"settings": {"type": "object"}}},
    },
    "auth.update_password": {
        "summary": "修改密码",
        "tag": "认证",
        "auth": "login",
        "description": "成功后吊销其它会话，并给当前会话发新 CSRF。",
        "body": _json_body({"old_password": _STRING, "new_password": _STRING}),
        "data": {"type": "object", "properties": {"updated": _BOOL, "csrf": _STRING}},
        "errors": {403: "当前密码不正确"},
    },
    "auth.list_tokens": {
        "summary": "访问令牌列表",
        "tag": "认证",
        "auth": "login",
        "data": _ref("TokenList"),
    },
    "auth.create_token": {
        "summary": "新建访问令牌",
        "tag": "认证",
        "auth": "login",
        "status": 201,
        "description": "`scopes` 缺省为 read/upload/write；`album_id` 是上传默认相册。",
        "body": _json_body(
            {
                "name": _STRING,
                "expires_in": {"type": "integer", "description": "秒；省略表示永久"},
                "scopes": _array({"type": "string", "enum": ["read", "upload", "write", "admin"]}),
                "album_id": _INT,
            }
        ),
        "data": _ref("TokenPayload"),
        "errors": {403: "申请 admin scope 但不是管理员", 404: "相册不存在或没有写权限"},
    },
    "auth.revoke_token": {
        "summary": "撤销访问令牌",
        "tag": "认证",
        "auth": "login",
        "path": {"token_id": "令牌 ID"},
        "data": {"type": "object", "properties": {"revoked": _BOOL}},
        "errors": {404: "令牌不存在"},
    },
    # ------------------------------------------------------------- 上传
    "uploads.upload": {
        "summary": "上传图片或视频",
        "tag": "上传",
        "auth": "optional",
        "status": 201,
        "description": (
            "`file` 与 `url` 二选一；`album_id` 省略时用 PAT 的默认相册，"
            "再兜底到用户的默认相册（匿名上传进系统相册）。"
        ),
        "form": _form_body(
            {
                "file": _FILE,
                "url": {"type": "string", "description": "图片地址，由服务端抓取"},
                "album_id": {"type": "integer", "description": "目标相册（需写权限）"},
                "title": _STRING,
                "expire": {"type": "integer", "description": "有效期秒数，0 表示永久"},
            }
        ),
        "data": _ref("ImagePayload"),
        "errors": {
            403: "账号不可用、关闭了匿名上传，或站点已冻结上传",
            413: "超过单文件大小上限",
        },
    },
    # ------------------------------------------------------------- 图片
    "images.list_images": {
        "summary": "个人图库",
        "tag": "图片",
        "auth": "login",
        "description": "只含自己的图片与共享给自己的相册；管理员需显式 `scope=all` 看全站公开图。",
        "params": [
            _q("scope", "`mine`（默认）或 `all`（仅管理员）", enum=["mine", "all"]),
            _q("album_id", "按相册筛选", "integer"),
            _q("keyword", "文件名或标题关键词"),
            _q("tag", "按标签筛选"),
            *_CURSOR_PARAMS,
            *_PAGE_PARAMS,
        ],
        "data": _ref("ImageList"),
        "errors": {403: "非管理员请求 `scope=all`"},
    },
    "images.read_image": {
        "summary": "图片详情",
        "tag": "图片",
        "auth": "login",
        "path": {"sha": "图片 sha"},
        "data": _ref("ImagePayload"),
        "errors": {404: "图片不存在或无权访问"},
    },
    "images.update_image": {
        "summary": "修改图片属性",
        "tag": "图片",
        "auth": "login",
        "path": {"sha": "图片 sha"},
        "description": "`album_id` 不能置空（图片必须属于一个相册）；`expire_at` 是绝对时间戳。",
        "body": _json_body(
            {
                "title": _STRING,
                "album_id": _INT,
                "visibility": _VISIBILITY,
                "tags": _array(_STRING),
                "plaza": _nullable(_BOOL),
                "expire_at": _nullable(_INT),
            }
        ),
        "data": _ref("ImagePayload"),
        "errors": {403: "不是所有者", 404: "图片或目标相册不存在"},
    },
    "images.remove_image": {
        "summary": "删除图片",
        "tag": "图片",
        "auth": "login",
        "path": {"sha": "图片 sha"},
        "data": {"type": "object", "properties": {"deleted": _BOOL}},
        "errors": {403: "不是所有者", 404: "图片不存在"},
    },
    "images.import_external": {
        "summary": "登记外链图片",
        "tag": "图片",
        "auth": "login",
        "description": "只登记地址、不下载字节；单请求最多 100 条。",
        "body": _json_body(
            {
                "items": {
                    "type": "array",
                    "description": "字符串数组，或 `{url, filename, title}` 对象数组",
                    "items": {"type": "object"},
                },
                "album_id": _INT,
            },
            ("items",),
        ),
        "data": {
            "type": "object",
            "properties": {
                "imported": _array(_ref("Image")),
                "failed": _array(
                    {
                        "type": "object",
                        "properties": {"url": _STRING, "message": _STRING},
                    }
                ),
            },
        },
    },
    "images.batch_delete": {
        "summary": "批量删除",
        "tag": "图片",
        "auth": "login",
        "body": _json_body({"shas": _array(_STRING)}, ("shas",)),
        "data": {"type": "object", "properties": {"deleted": _INT}},
        "errors": {404: "其中一张不存在或不属于当前账号"},
    },
    "images.batch_update": {
        "summary": "批量修改属性",
        "tag": "图片",
        "auth": "login",
        "description": "一次最多 100 张；只改传入的字段。",
        "body": _json_body(
            {
                "shas": _array(_STRING),
                "title": _STRING,
                "album_id": _INT,
                "visibility": _VISIBILITY,
                "tags": _array(_STRING),
                "plaza": _nullable(_BOOL),
            },
            ("shas",),
        ),
        "data": {"type": "object", "properties": {"updated": _INT}},
    },
    # ------------------------------------------------------------- 相册
    "albums.list_albums": {
        "summary": "相册列表",
        "tag": "相册",
        "auth": "login",
        "description": "含自己的相册与共享给自己的相册；管理员额外拿到系统相册（`role=system`）。",
        "data": _ref("AlbumList"),
    },
    "albums.create_album": {
        "summary": "新建相册",
        "tag": "相册",
        "auth": "login",
        "status": 201,
        "body": _json_body(
            {
                "name": _STRING,
                "visibility": {"type": "string", "enum": ["public", "private", "shared"]},
                "description": _STRING,
                "plaza": _BOOL,
            },
            ("name",),
        ),
        "data": _ref("AlbumPayload"),
    },
    "albums.update_album": {
        "summary": "修改相册",
        "tag": "相册",
        "auth": "login",
        "path": {"album_id": "相册 ID"},
        "body": _json_body(
            {
                "name": _STRING,
                "description": _STRING,
                "visibility": {"type": "string", "enum": ["public", "private", "shared"]},
                "plaza": _BOOL,
                "cover_sha": _STRING,
            }
        ),
        "data": _ref("AlbumPayload"),
        "errors": {404: "相册不存在或不是自己的"},
    },
    "albums.delete_album": {
        "summary": "删除相册",
        "tag": "相册",
        "auth": "login",
        "path": {"album_id": "相册 ID"},
        "data": {"type": "object", "properties": {"deleted": _BOOL}},
        "errors": {409: "默认相册不可删 / 相册里还有图片"},
    },
    "albums.list_shares": {
        "summary": "相册成员列表",
        "tag": "相册",
        "auth": "login",
        "path": {"album_id": "相册 ID"},
        "data": _ref("ShareList"),
    },
    "albums.create_share": {
        "summary": "添加相册成员",
        "tag": "相册",
        "auth": "login",
        "path": {"album_id": "相册 ID"},
        "description": "按用户名添加；私有相册添加成员后自动变为 `shared`。",
        "body": _json_body(
            {
                "username": _STRING,
                "permission": {"type": "string", "enum": ["read", "write"]},
                "expires_in": {"type": "integer", "description": "秒；省略表示不过期"},
            },
            ("username",),
        ),
        "data": _ref("SharePayload"),
        "errors": {400: "不能共享给自己", 404: "用户不存在或未激活"},
    },
    "albums.update_share": {
        "summary": "调整成员权限或有效期",
        "tag": "相册",
        "auth": "login",
        "path": {"album_id": "相册 ID", "user_id": "成员用户 ID"},
        "body": _json_body(
            {
                "permission": {"type": "string", "enum": ["read", "write"]},
                "expires_in": {"type": "integer", "description": "秒"},
            }
        ),
        "data": _ref("SharePayload"),
        "errors": {404: "授权记录不存在"},
    },
    "albums.delete_share": {
        "summary": "移除相册成员",
        "tag": "相册",
        "auth": "login",
        "path": {"album_id": "相册 ID", "user_id": "成员用户 ID"},
        "data": {"type": "object", "properties": {"deleted": _BOOL}},
        "errors": {404: "授权记录不存在"},
    },
    # ------------------------------------------------------------- 广场
    "plaza.plaza": {
        "summary": "图片广场",
        "tag": "广场",
        "auth": "none",
        "description": "匿名可读；站点关闭广场时 404。只列作者显式发布且可见性为 public 的图片。",
        "params": _CURSOR_PARAMS,
        "data": _ref("ImageList"),
        "errors": {404: "站点未开启广场"},
    },
}


# -------------------------------------------------------------------- builder


def _convert_path(rule: str) -> str:
    """``<int:album_id>`` → ``{album_id}``."""
    return re.sub(r"<(?:[a-zA-Z_]+:)?([a-zA-Z_]+)>", r"{\1}", rule)


def _path_parameter_types(rule: str) -> dict[str, str]:
    types: dict[str, str] = {}
    for converter, name in re.findall(r"<(?:(?P<c>[a-zA-Z_]+):)?(?P<n>[a-zA-Z_]+)>", rule):
        types[name] = _CONVERTER_TYPES.get(converter, "string")
    return types


def _envelope(data: dict | None) -> dict:
    return {
        "type": "object",
        "properties": {
            "code": {"type": "string", "example": "OK"},
            "message": {"type": "string", "example": ""},
            "data": data or _nullable({"type": "object"}),
        },
    }


def _error_response(description: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": _ref("ErrorEnvelope")}},
    }


def _security(auth: str) -> list[dict] | None:
    if auth == "none":
        return []
    schemes = [{"session": []}, {"pat": []}]
    if auth == "optional":
        #: 空对象表示「也可以不带凭据」，与匿名上传的语义一致。
        return [*schemes, {}]
    return schemes


def _binary_response(meta: dict) -> dict:
    content_type = meta.get("content_type", "application/octet-stream")
    return {
        "200": {
            "description": meta.get("response_desc") or "文件内容",
            "content": {content_type: {"schema": {"type": "string", "format": "binary"}}},
        },
        "302": {"description": "跳转到存储后端的公开地址"},
        "403": {"description": "被防盗链规则拒绝"},
        "404": {"description": "图片不存在、已过期或不可见"},
    }


def _redirect_response() -> dict:
    return {"302": {"description": "跳转（Provider 授权页或前端页面）"}}


def _responses(meta: dict, method: str) -> dict:
    if meta.get("binary"):
        return _binary_response(meta)
    if meta.get("redirect"):
        return _redirect_response()

    status = str(meta.get("status") or 200)
    envelope = _envelope(meta.get("data"))
    responses: dict[str, Any] = {
        status: {
            "description": meta.get("response_desc") or "成功",
            "content": {"application/json": {"schema": envelope}},
        }
    }

    auth = meta.get("auth", "none")
    errors: dict[int, str] = {400: "参数不合法（PARAM_ERROR）"}
    if auth in ("login", "admin"):
        errors[401] = "未登录或凭据无效（UNAUTHORIZED）"
        errors[403] = "权限不足（FORBIDDEN）"
    elif auth == "optional":
        errors[403] = "无权限（FORBIDDEN）"
    errors.update(meta.get("errors") or {})
    for code, description in sorted(errors.items()):
        responses[str(code)] = _error_response(description)
    return responses


def _tag_for(meta: dict) -> str:
    return meta.get("tag") or "待补文档"


def _undocumented_summary(endpoint: str, method: str) -> str:
    blueprint, _, name = endpoint.partition(".")
    readable = (name or blueprint).replace("_", " ")
    return "%s %s（未编写文档）" % (method, readable)


def _operation(rule, method: str) -> dict:
    meta = OPERATIONS.get(rule.endpoint) or {}
    op: dict[str, Any] = {
        "tags": [_tag_for(meta)],
        "summary": meta.get("summary") or _undocumented_summary(rule.endpoint, method),
        "operationId": "%s_%s" % (rule.endpoint.replace(".", "_"), method.lower()),
    }
    if meta.get("description"):
        op["description"] = meta["description"]
    if not meta:
        op["x-undocumented"] = True

    parameters = []
    descriptions = meta.get("path") or {}
    for name, type_ in _path_parameter_types(rule.rule).items():
        parameters.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": type_},
                "description": descriptions.get(name, ""),
            }
        )
    parameters.extend(meta.get("params") or [])
    if parameters:
        op["parameters"] = parameters

    security = _security(meta.get("auth", "none"))
    if security is not None:
        op["security"] = security

    if "form" in meta:
        op["requestBody"] = meta["form"]
    elif "body" in meta:
        op["requestBody"] = meta["body"]

    op["responses"] = _responses(meta, method)
    return op


def build_spec(app: Flask) -> dict:
    """Build the OpenAPI document for ``app`` from its live route table."""
    paths: dict[str, dict] = {}
    for rule in app.url_map.iter_rules():
        #: 静态文件不是 API；``/static`` 由 Flask 自带。
        if rule.endpoint == "static" or rule.rule.startswith("/static/"):
            continue
        if rule.endpoint in HIDDEN_ENDPOINTS:
            continue
        if rule.endpoint.split(".", 1)[0] in HIDDEN_BLUEPRINTS:
            continue
        methods = sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
        if not methods:
            continue
        path = _convert_path(rule.rule)
        operations = paths.setdefault(path, {})
        for method in methods:
            operations[method.lower()] = _operation(rule, method)

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "sapic API",
            "description": (
                "所有 `/api/v2/*` 响应都是 `{code, message, data}` 信封；成功时 `code` 恒为 "
                "`OK`，失败时是错误枚举名。写操作可用 Cookie 会话（需 `X-CSRF-Token` 头）"
                "或 PAT（`Authorization: Bearer sp_...`）。"
            ),
            "version": __version__,
        },
        "servers": [{"url": "/"}],
        "tags": TAGS,
        "paths": {
            path: dict(sorted(operations.items()))
            for path, operations in sorted(paths.items())
        },
        "components": {
            "schemas": SCHEMAS,
            "securitySchemes": SECURITY_SCHEMES,
        },
    }


__all__ = [
    "HIDDEN_BLUEPRINTS",
    "HIDDEN_ENDPOINTS",
    "OPERATIONS",
    "SCHEMAS",
    "TAGS",
    "build_spec",
]
