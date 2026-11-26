# -*- coding: utf-8 -*-
"""oidc — sign in through any standard OpenID Connect provider.

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

__version__ = "0.3.0"
__author__ = "staugur"
__description__ = "标准 OpenID Connect 统一登录"
__catalog__ = "auth"
__state__ = "disabled"

TIMEOUT = 15
DISCOVERY_TTL = 300
DEFAULT_SCOPES = "openid profile email"

#: (key, node type, label, hint)；``input`` 的 hint 是占位文案，``switch`` 的 hint 是说明提示。
FIELDS = (
    ("issuer", "input", "Issuer 地址", "OIDC 服务地址，如 https://id.example.com"),
    ("client_id", "input", "Client ID", "在 OIDC 服务端创建应用后获得"),
    ("client_secret", "password", "Client Secret", "OIDC 应用密钥"),
    ("scopes", "input", "Scope", DEFAULT_SCOPES),
    ("button_text", "input", "按钮文案", "登录页按钮文案，默认「通过 OIDC 登录」"),
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
            "label_key": "hooks.oidc.fields.%s.label" % key,
            "default": True,
            "help": hint,
            "help_key": "hooks.oidc.fields.%s.hint" % key,
            "active_text": "开启",
            "inactive_text": "关闭",
        }
    node = {
        "type": kind,
        "key": key,
        "label": label,
        "label_key": "hooks.oidc.fields.%s.label" % key,
        "placeholder": hint,
        "placeholder_key": "hooks.oidc.fields.%s.hint" % key,
        "required": key in REQUIRED,
    }
    if FIELD_HELP.get(key):
        node["help"] = FIELD_HELP[key]
        node["help_key"] = "hooks.oidc.fields.%s.help" % key
    return node


def hook_manifest():
    return {
        "title": "OIDC 统一登录",
        "title_key": "hooks.oidc.title",
        "description_key": "hooks.oidc.description",
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
    #: 管理员填了自定义文案就照用；没填时带上 i18n 键，让英文界面能翻译。
    text = str(config.get("button_text") or "").strip()
    link = {
        "type": "link",
        "text": text or "通过 OIDC 登录",
        "href": "/api/v2/auth/oidc",
        "icon": "builtin:link",
    }
    if not text:
        link["text_key"] = "hooks.oidc.signIn"
    return [
        {"type": "divider", "label": "或", "label_key": "common.or"},
        link,
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
        raise ValueError("oidc is not configured")
    scopes = str(config.get("scopes") or "").strip() or DEFAULT_SCOPES
    return issuer, client_id, client_secret, scopes


def _excerpt(payload) -> str:
    """Single-line body preview so logs name the failing step and the reason."""
    return " ".join(str(payload or "").split())[:200]


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
        raise ValueError(
            "discovery document is unavailable (HTTP %s): %s"
            % (response.status_code, _excerpt(response.text))
        )
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
        #: 把拿到的 claim 名带进消息：缺 sub 通常意味着 provider 侧的 scope
        #: 交集把 openid 丢了，只看「subject is missing」排查不了。
        raise ValueError(
            "subject is missing from the provider claims (got: %s)"
            % (", ".join(sorted(claims)) or "empty response")
        )
    #: OIDC 标准 claim 里 preferred_username 才是用户可读的用户名，sub 通常是
    #: 机器标识（UUID），直接当账号名难读也不友好。所以用户名优先取
    #: preferred_username，拿不到才回落 sub；登录判定只看 issuer+sub，username
    #: 仅作本地账号名与显示，下游 _oidc_username 会去掉非法字符并去重。
    #: 昵称链补 preferred_username，让只回 preferred_username 的 provider 也有显示名。
    #: 部分 provider 只把验证过的邮箱入库，缺字段按已验证处理。
    verified = claims.get("email_verified", True)
    if isinstance(verified, str):
        verified = verified.strip().lower() in ("true", "1", "yes")
    username = str(claims.get("preferred_username") or "").strip()
    return {
        "issuer": str(claims.get("iss") or issuer),
        "subject": subject,
        "username": username or subject,
        "nickname": str(
            claims.get("nickname")
            or claims.get("preferred_username")
            or claims.get("name")
            or ""
        ).strip(),
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
        raise ValueError(
            "token exchange failed (HTTP %s): %s"
            % (response.status_code, _excerpt(response.text))
        )
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
            raise ValueError(
                "userinfo request failed (HTTP %s): %s"
                % (info.status_code, _excerpt(info.text))
            )
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
        "toast": {"level": "success", "text": "discovery ok: %s" % issuer},
    }
