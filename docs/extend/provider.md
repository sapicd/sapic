# 登录 Provider（`catalog = "auth"`）

内置的 `passport` 钩子（OIDC 统一登录）就是按这份契约实现的，第三方包照着实现即可接入，
核心代码不需要改。

钩子只负责**与 Provider 对话**：拼授权地址、用授权码换用户信息。
浏览器跳转、state Cookie、本地会话与建号/绑定全部由核心
（`sapic/views/auth.py`、`sapic/libs/users.py`）负责，钩子里不要碰 Flask。

## 契约

```python
__catalog__ = "auth"          # 必需：否则不会被识别为 Provider

def oidc_authorize_url(config, redirect_uri, state) -> str
def oidc_exchange(config, code, redirect_uri) -> dict
def identity_issuer(config) -> str        # 可选
```

| 函数 | 说明 |
| --- | --- |
| `oidc_authorize_url` | 返回把浏览器送去 Provider 的完整地址。参数 `config` 是后台保存的钩子配置，`state` 必须原样带上（核心用 Cookie 校验回跳）。失败抛 `ValueError`（英文消息），核心返回 400。 |
| `oidc_exchange` | 用 `code` 换用户信息并返回下面的字典。抛异常时核心跳 `/login?oidc=error`。 |
| `identity_issuer` | 返回身份命名空间，写进本地账号的 `oidc_issuer`。缺省用 `config["issuer"]`（适合 OIDC 的 issuer 地址）；非 OIDC 的 Provider（如 GitHub）用它声明一个固定值，否则「已绑定」判定会拿不到值。 |

`oidc_exchange` 的返回值：

| 键 | 必需 | 说明 |
| --- | --- | --- |
| `subject` | ✅ | Provider 内稳定不变的唯一 ID（OIDC 的 `sub`、GitHub 的 `id`）。也接受 `sub` 别名，会被归一化成 `subject`。 |
| `issuer` | | 不返回则用 `identity_issuer()` / `config["issuer"]`。 |
| `username` | | 建号时用作本地账号名；缺省用 `subject`。会被清洗成 `[0-9a-zA-Z_]`。 |
| `nickname` | | 显示名，上游改名不影响本地账号。 |
| `email` | | 用于「双方邮箱都验证过就自动关联老账号」。 |
| `email_verified` | | 布尔（也接受 `"true"` / `1`）。默认 `false`：Provider 没明确验证过邮箱时不要传 `true`，否则等于允许抢填他人邮箱接管账号。 |

校验由 `sapic/libs/ext.py` 的 `normalize_identity()` 统一做：类型、长度都会收敛，
没有 `subject` 一律判为无效（跳 `/login?oidc=invalid`），不会落下空身份。

## 登录与绑定流程

```text
GET /api/v2/auth/oidc/<name>[?bind=1&next=/settings]
   → 302 到 Provider 授权页，同时种下签名 state Cookie（10 分钟）
GET /api/v2/auth/oidc/<name>/callback?code=...&state=...
   → 校验 state → oidc_exchange → 绑定或登录 → 302 回 next
```

- `<name>` 是**钩子名**（模块名）。包名写成 `sapic_oauth_github`，地址就是
  `/api/v2/auth/oidc/sapic_oauth_github`。
- `bind=1` 表示把身份绑到当前登录账号（要求已登录），完成后回 `next` 并带
  `?identity=bound`（失败 `identity=error`）。
- 登录失败的回跳标记：`denied`（用户在 Provider 拒绝）、`error`（换 token 失败）、
  `invalid`（身份无效）、`unlinked`（该身份没绑定本地账号）、`inactive`（账号待审核/被禁用）。
- 解绑：`DELETE /api/v2/auth/identities/<name>`，请求体带当前密码。
  要求密码是为了防止只有第三方登录的账号把自己锁在门外。
- 登录页按钮由钩子自己在 `login.after_form` 插槽里声明，所以每个 Provider 的文案/图标
  都可以不同，核心不用登记。

账号解析顺序（`sapic/libs/users.py` 的 `resolve_oidc_user`）：

1. `(issuer, subject)` 已绑定 → 直接登录（账号非正常状态则拒绝）；
2. Provider 声明邮箱已验证、且本地同邮箱账号本身也验证过、且该账号还没绑过任何身份 →
   自动关联；
3. 否则按 Provider 信息**新建本地账号**（`register_review` 开启时落到待审核，
   不直接发会话），并创建默认相册。

## 最小可用示例

```python
# sapic_oauth_github/__init__.py
from urllib.parse import urlencode

try:
    import requests
except ImportError:  # 可选依赖，缺失时给用户可读提示
    requests = None

__version__ = "0.1.0"
__author__ = "you"
__description__ = "使用 GitHub 登录"
__catalog__ = "auth"
__state__ = "disabled"        # 装好后到后台启用并填 client_id/client_secret

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USERINFO_URL = "https://api.github.com/user"
TIMEOUT = 15


def hook_manifest():
    return {
        "title": "GitHub 登录",
        "catalog": "auth",
        "config_schema": [
            {"type": "input", "key": "client_id", "label": "Client ID", "required": True},
            {
                "type": "password",
                "key": "client_secret",
                "label": "Client Secret",
                "required": True,
            },
        ],
        "slots": [{"name": "login.after_form"}],
    }


def identity_issuer(config=None):
    return "github"


def oidc_authorize_url(config=None, redirect_uri="", state=""):
    client_id = str((config or {}).get("client_id") or "").strip()
    if not client_id:
        raise ValueError("github is not configured")
    return "%s?%s" % (
        AUTHORIZE_URL,
        urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": "read:user",
            }
        ),
    )


def oidc_exchange(config=None, code="", redirect_uri=""):
    if requests is None:
        raise ValueError("Please install requests module")
    config = config or {}
    token = requests.post(
        TOKEN_URL,
        data={
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Accept": "application/json"},
        timeout=TIMEOUT,
    )
    if token.status_code != 200:
        raise ValueError("token exchange failed")
    access_token = (token.json() or {}).get("access_token")
    if not access_token:
        raise ValueError("access token is missing")

    info = requests.get(
        USERINFO_URL,
        headers={"Authorization": "Bearer %s" % access_token},
        timeout=TIMEOUT,
    )
    if info.status_code != 200:
        raise ValueError("userinfo request failed")
    user = info.json() or {}

    return {
        "issuer": "github",
        "subject": str(user.get("id") or ""),
        "username": user.get("login") or "",
        "nickname": user.get("name") or "",
        "email": user.get("email") or "",
        #: GitHub 的个人资料邮箱不一定验证过，不要在这里传 True，
        #: 否则可能凭一个他人邮箱自动关联到别人的本地账号。
        "email_verified": False,
    }


def slot_login_after_form(context=None, **kwargs):
    config = (context or {}).get("config") or {}
    if not config.get("client_id"):
        return []          # 没配置就不显示按钮，避免点进 404
    return [
        {"type": "divider", "label": "或"},
        {
            "type": "link",
            "text": "使用 GitHub 登录",
            "href": "/api/v2/auth/oidc/sapic_oauth_github",
            "icon": "brand:github",
        },
    ]
```

Provider 拿到的 `config` 只有后台钩子页保存的键（`hooks_config[<hook>]`），
不像存储驱动那样有「每个后端一份配置」。需要多套凭据就接入多个 Provider 包
（一个站点通常只配一个）。

## 现有实现参考

内置 `server/sapic/hooks/passport.py`：走 OIDC discovery 文档，
`oidc_authorize_url` 从 `/.well-known/openid-configuration` 取授权端点，
`oidc_exchange` 用 `id_token` / userinfo 取 claims，并带 5 分钟 discovery 缓存。

## 已知限制

- 本地账号目前只保存**一组** `(oidc_issuer, oidc_subject)`。同时接入多个 Provider 时，
  同一个账号只能绑定其中一个；再绑另一个会覆盖旧的（旧的登录方式随即失效）。
  多身份并存需要单独的身份表，属于后续工作。
- 契约基于「授权码 + 服务端换 token」，不支持隐式流或纯前端 token 流程；
  需要那样做的 Provider 应在钩子里自行完成，只把最终身份交给核心。
