# -*- coding: utf-8 -*-
"""passport — sign in through a Passport (OIDC) provider.

The hook owns only the provider conversation, following the standard
authorization-code flow: the discovery document decides the endpoints, the
token endpoint returns ``id_token``/``access_token``, and the userinfo endpoint
returns the claims. ``sapic.views.auth`` owns the browser redirects, the state
cookie and the local session, so nothing here touches Flask.

Contract used by the core::

    oidc_authorize_url(config, redirect_uri, state) -> str
    oidc_exchange(config, code, redirect_uri) -> {issuer, subject, ...}

Failures raise ``ValueError`` with an English message.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode
from json import loads
from time import time
from urllib.parse import urlencode

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None

__version__ = "0.2.1"
__author__ = "staugur"
__description__ = "使用 Passport 统一登录（OIDC）"
__catalog__ = "auth"
__state__ = "disabled"

TIMEOUT = 15
DISCOVERY_TTL = 300
DEFAULT_SCOPES = "openid profile email"

#: (key, node type, label, hint)；``input`` 的 hint 是占位文案，``switch`` 的 hint 是说明提示。
FIELDS = (
    ("issuer", "input", "Issuer 地址", "Passport 服务地址，如 https://passport.example.com"),
    ("client_id", "input", "Client ID", "Passport 后台创建 OIDC 应用后获得"),
    ("client_secret", "password", "Client Secret", "OIDC 应用密钥"),
    ("scopes", "input", "Scope", DEFAULT_SCOPES),
    ("button_text", "input", "按钮文案", "登录页按钮文案，默认「通过 Passport 登录」"),
)
#: 输入框下方要补充说明的字段：``key -> help``（占位文案放不下这些取舍）。
FIELD_HELP = {
    "scopes": (
        "留空即用上面的默认 scope；多请求的 scope 只影响 provider 返回哪些 claim，"
        "sapic 只消费身份字段（sub / 邮箱 / 昵称），role 等自定义声明不会改变本站权限。"
    ),
}
REQUIRED = ("issuer", "client_id", "client_secret")

#: Discovery cache: one entry is enough, the provider rarely changes.
_DISCOVERY = {"key": "", "doc": {}, "expires": 0.0}


def _field_node(key: str, kind: str, label: str, hint: str) -> dict:
    """One ``config_schema`` entry: a switch carries its hint as help text."""
    if kind == "switch":
        return {
            "type": kind,
            "key": key,
            "label": label,
            "default": True,
            "help": hint,
            "active_text": "开启",
            "inactive_text": "关闭",
        }
    node = {
        "type": kind,
        "key": key,
        "label": label,
        "placeholder": hint,
        "required": key in REQUIRED,
    }
    if FIELD_HELP.get(key):
        node["help"] = FIELD_HELP[key]
    return node


def hook_manifest():
    return {
        "title": "Passport 统一登录",
        "catalog": "auth",
        "config_schema": [_field_node(*field) for field in FIELDS],
        "actions": [
            {
                "name": "ping",
                "label": "检查 discovery",
                "scope": "admin",
                "with_form": True,
            }
        ],
        "slots": [{"name": "login.after_form"}],
    }


def slot_login_after_form(context=None, **kwargs):
    config = (context or {}).get("config") or {}
    if not config.get("issuer") or not config.get("client_id"):
        #: 未配置时不在登录页出现，避免把用户引到一个 404 的路由。
        return []
    text = str(config.get("button_text") or "").strip() or "通过 Passport 登录"
    return [
        {"type": "divider", "label": "或"},
        {
            "type": "link",
            "text": text,
            "href": "/api/v2/auth/oidc/passport",
            "icon": "builtin:link",
        },
    ]


def _issuer(config: dict) -> str:
    return str((config or {}).get("issuer") or "").strip().rstrip("/")


def _settings(config: dict) -> tuple[str, str, str, str]:
    """Validated ``(issuer, client_id, client_secret, scopes)``."""
    config = config or {}
    issuer = _issuer(config)
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(config.get("client_secret") or "").strip()
    if not issuer or not client_id or not client_secret:
        raise ValueError("passport is not configured")
    scopes = str(config.get("scopes") or "").strip() or DEFAULT_SCOPES
    return issuer, client_id, client_secret, scopes


def _discovery(issuer: str) -> dict:
    """Fetch and cache ``/.well-known/openid-configuration``."""
    cached = _DISCOVERY
    if cached["key"] == issuer and time() < cached["expires"]:
        return cached["doc"]
    if requests is None:
        raise ValueError("Please install requests module")

    response = requests.get(
        "%s/.well-known/openid-configuration" % issuer, timeout=TIMEOUT
    )
    if response.status_code != 200:
        raise ValueError("discovery document is unavailable")
    doc = response.json() or {}
    if not doc.get("authorization_endpoint") or not doc.get("token_endpoint"):
        raise ValueError("discovery document is incomplete")
    _DISCOVERY.update(
        {"key": issuer, "doc": doc, "expires": time() + DISCOVERY_TTL}
    )
    return doc


def _id_token_claims(token: str) -> dict:
    """Decode the payload of an ``id_token``.

    The token is read straight from the provider's token endpoint over TLS, so
    the payload is trusted for identification; signature verification would
    need the JWKS keys and is out of scope for a login helper.
    """
    if not token or token.count(".") < 2:
        return {}
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return loads(urlsafe_b64decode(payload.encode("utf-8")) or b"{}")
    except Exception:
        return {}


def _identity(claims: dict, issuer: str) -> dict:
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise ValueError("subject is missing from the provider claims")
    #: Passport 的 sub 就是用户 uid（22 位小写），昵称会随用户改名而变化，
    #: 所以本地账号名一律取 uid，昵称只作显示名。
    #: Passport 只把验证过的手机号/邮箱入库，缺字段按已验证处理。
    verified = claims.get("email_verified", True)
    if isinstance(verified, str):
        verified = verified.strip().lower() in ("true", "1", "yes")
    return {
        "issuer": str(claims.get("iss") or issuer),
        "subject": subject,
        "username": subject,
        "nickname": str(claims.get("nickname") or claims.get("name") or ""),
        "email": str(claims.get("email") or ""),
        #: 只有 provider 明确验证过的邮箱才允许自动关联本地老账号。
        "email_verified": bool(verified),
    }


def oidc_authorize_url(config=None, redirect_uri="", state="") -> str:
    issuer, client_id, _, scopes = _settings(config)
    doc = _discovery(issuer)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
    }
    return "%s?%s" % (doc["authorization_endpoint"], urlencode(params))


def oidc_exchange(config=None, code="", redirect_uri="") -> dict:
    issuer, client_id, client_secret, _ = _settings(config)
    if not code:
        raise ValueError("authorization code is missing")
    if requests is None:
        raise ValueError("Please install requests module")

    doc = _discovery(issuer)
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(
        doc["token_endpoint"],
        data=payload,
        headers={"Accept": "application/json"},
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        raise ValueError("token exchange failed")
    tokens = response.json() or {}

    claims = {}
    endpoint = doc.get("userinfo_endpoint")
    access_token = tokens.get("access_token")
    if endpoint and access_token:
        info = requests.get(
            endpoint,
            headers={"Authorization": "Bearer %s" % access_token},
            timeout=TIMEOUT,
        )
        if info.status_code != 200:
            raise ValueError("userinfo request failed")
        claims = info.json() or {}
    if not claims.get("sub"):
        claims = _id_token_claims(tokens.get("id_token"))
    return _identity(claims, issuer)


def action_ping(values=None, context=None, **kwargs):
    """Check that the discovery document is reachable and complete."""
    config = dict((context or {}).get("config") or {})
    config.update({key: value for key, value in (values or {}).items() if value})
    try:
        issuer, _, _, _ = _settings(config)
        _discovery(issuer)
    except Exception as exc:
        return {"code": 1, "message": str(exc)}

    return {
        "code": 0,
        "message": "discovery ok",
        "toast": {"level": "success", "text": "discovery 正常：%s" % issuer},
    }
