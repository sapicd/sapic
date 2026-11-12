# -*- coding: utf-8 -*-
"""Passport (OIDC) login: the start/callback flow and the hook contract."""

from urllib.parse import parse_qs, urlparse

from sapic.libs.settings import set_setting
from sapic.libs.users import bind_oidc_identity, create_user, resolve_oidc_user
from sapic.models import User

CONFIG = {
    "issuer": "https://passport.example.com",
    "client_id": "sp-client",
    "client_secret": "sp-secret",
}

DISCOVERY = {
    "issuer": "https://passport.example.com",
    "authorization_endpoint": "https://passport.example.com/oidc/authorize",
    "token_endpoint": "https://passport.example.com/oidc/token",
    "userinfo_endpoint": "https://passport.example.com/oidc/userinfo",
    "scopes_supported": ["openid", "profile", "email"],
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeRequests:
    """Minimal stand-in for ``requests`` used by the hook."""

    def __init__(self, token=None, userinfo=None, discovery=None):
        self.discovery = discovery or DISCOVERY
        self.token = token or {"access_token": "at-1", "id_token": ""}
        self.userinfo = userinfo or {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if url.endswith("/.well-known/openid-configuration"):
            return FakeResponse(200, self.discovery)
        return FakeResponse(200, self.userinfo)

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return FakeResponse(200, self.token)


def enable_hook(app, config=None):
    with app.app_context():
        set_setting("hooks_state", {"passport": True})
        set_setting("hooks_config", {"passport": config or CONFIG})
        app.extensions["hooks"].reload()


def hook_module(app):
    return app.extensions["hooks"].get("passport").module


def identity(module, monkeypatch, **claims):
    payload = {
        "issuer": CONFIG["issuer"],
        "subject": "u-1",
        "username": "alice",
        "nickname": "Alice",
        "email": "alice@example.com",
        #: Passport 只在库里存验证过的邮箱，钩子输出已归一化为 True。
        "email_verified": True,
    }
    payload.update(claims)
    monkeypatch.setattr(
        module, "oidc_exchange", lambda config, code, redirect_uri: dict(payload)
    )


def start_flow(client, monkeypatch, module, query="?next=/albums"):
    monkeypatch.setattr(
        module,
        "oidc_authorize_url",
        lambda config, redirect_uri, state: "%s?state=%s"
        % (DISCOVERY["authorization_endpoint"], state),
    )
    response = client.get("/api/v2/auth/oidc/passport" + query)
    state = parse_qs(urlparse(response.headers["Location"]).query)["state"][0]
    return response, state


def test_hook_is_disabled_and_declares_the_login_slot(app):
    hook = app.extensions["hooks"].get("passport")
    assert hook is not None
    assert hook.meta["__catalog__"] == "auth"
    assert hook.enabled is False

    manifest = app.extensions["hooks"].manifest("passport")
    keys = [field["key"] for field in manifest["config_schema"]]
    assert keys == [
        "issuer",
        "client_id",
        "client_secret",
        "scopes",
        "button_text",
    ]
    assert manifest["slots"] == [
        {"name": "login.after_form", "mode": "declarative"}
    ]
    #: scope 的取舍写在输入框下方的 help 里，不能塞进占位文案（会被截断）。
    scopes = {field["key"]: field for field in manifest["config_schema"]}["scopes"]
    assert scopes["placeholder"] == "openid profile email"
    assert "role" in scopes["help"]


def test_login_slot_only_renders_when_configured(app):
    module = hook_module(app)
    assert module.slot_login_after_form(context={"config": {}}) == []

    nodes = module.slot_login_after_form(
        context={"config": {"issuer": CONFIG["issuer"], "client_id": "sp-client"}}
    )
    link = next(node for node in nodes if node["type"] == "link")
    assert link["href"] == "/api/v2/auth/oidc/passport"


def test_authorize_url_follows_the_discovery_document(app, monkeypatch):
    module = hook_module(app)
    fake = FakeRequests()
    monkeypatch.setattr(module, "requests", fake)
    monkeypatch.setattr(
        module, "_DISCOVERY", {"key": "", "doc": {}, "expires": 0.0}
    )

    url = module.oidc_authorize_url(
        config=CONFIG, redirect_uri="https://app.example/cb", state="st-1"
    )

    assert url.startswith(DISCOVERY["authorization_endpoint"] + "?")
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["sp-client"]
    assert query["state"] == ["st-1"]
    assert query["scope"] == ["openid profile email"]


def test_exchange_prefers_userinfo_claims(app, monkeypatch):
    module = hook_module(app)
    fake = FakeRequests(
        userinfo={
            "sub": "u-9",
            "nickname": "Bobby",
            "email": "bobby@example.com",
        }
    )
    monkeypatch.setattr(module, "requests", fake)
    monkeypatch.setattr(
        module, "_DISCOVERY", {"key": "", "doc": {}, "expires": 0.0}
    )

    claims = module.oidc_exchange(
        config=CONFIG, code="code-1", redirect_uri="https://app.example/cb"
    )

    assert claims == {
        "issuer": CONFIG["issuer"],
        "subject": "u-9",
        #: 账号名取 uid（sub），昵称只作显示名。
        "username": "u-9",
        "nickname": "Bobby",
        "email": "bobby@example.com",
        "email_verified": True,
    }
    token_call = next(call for call in fake.calls if call[0] == "post")
    assert token_call[2]["data"]["grant_type"] == "authorization_code"
    userinfo_call = next(
        call for call in fake.calls if call[1] == DISCOVERY["userinfo_endpoint"]
    )
    assert userinfo_call[2]["headers"]["Authorization"] == "Bearer at-1"


def test_identity_treats_missing_email_verified_as_verified(app):
    module = hook_module(app)
    claims = {"sub": "u-1", "email": "bob@example.com"}

    #: Passport 只存验证过的邮箱，缺字段按已验证处理。
    assert module._identity(claims, CONFIG["issuer"])["email_verified"] is True

    #: Provider 显式给出 false 时仍然尊重它的说法。
    explicit = module._identity(
        {**claims, "email_verified": False}, CONFIG["issuer"]
    )
    assert explicit["email_verified"] is False


def test_start_redirects_and_sets_the_state_cookie(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)
    response, state = start_flow(client, monkeypatch, module)

    assert response.status_code == 302
    assert state
    assert "sapic-oidc" in response.headers.get("Set-Cookie", "")


def test_callback_links_by_email_and_starts_a_session(app, client, monkeypatch):
    user_id = local_user(app, username="alice", email="alice@example.com")
    enable_hook(app)
    module = hook_module(app)
    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch)

    response = client.get(
        "/api/v2/auth/oidc/passport/callback?code=code-1&state=%s" % state
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/albums"

    session = client.get("/api/v2/auth/session").get_json()["data"]
    assert session["authenticated"] is True
    assert session["user"]["username"] == "alice"

    with app.app_context():
        user = User.get_by_id(user_id)
        assert user.oidc_subject == "u-1"
        assert user.oidc_issuer == CONFIG["issuer"]


def test_second_login_reuses_the_bound_account(app, client, monkeypatch):
    user_id = local_user(app)
    enable_hook(app)
    module = hook_module(app)

    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch, email="carol@example.com")
    client.get("/api/v2/auth/oidc/passport/callback?code=c1&state=%s" % state)
    first = client.get("/api/v2/auth/session").get_json()["data"]["user"]

    #: 上游改名后仍然绑定到同一个本地账号，也不会再建新账号。
    _, state = start_flow(client, monkeypatch, module)
    identity(
        module,
        monkeypatch,
        email="carol@example.com",
        username="carol-renamed",
        nickname="Renamed",
    )
    client.get("/api/v2/auth/oidc/passport/callback?code=c2&state=%s" % state)
    second = client.get("/api/v2/auth/session").get_json()["data"]["user"]

    assert first["id"] == second["id"] == user_id
    with app.app_context():
        assert User.select().count() == 1


def test_callback_rejects_a_forged_state(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)
    identity(module, monkeypatch)

    response = client.get(
        "/api/v2/auth/oidc/passport/callback?code=code-1&state=forged"
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"


def test_new_account_is_created_with_a_default_album(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)
    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch)

    response = client.get(
        "/api/v2/auth/oidc/passport/callback?code=code-1&state=%s" % state
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/albums"

    session = client.get("/api/v2/auth/session").get_json()["data"]
    assert session["authenticated"] is True
    assert session["user"]["username"] == "alice"

    albums = client.get("/api/v2/albums").get_json()["data"]["items"]
    assert [album["name"] for album in albums] == ["默认相册"]


def test_new_account_names_the_user_after_the_uid(app):
    with app.app_context():
        #: provider 只给昵称（会随改名变化）时，账号名取 uid（subject）。
        user = resolve_oidc_user(
            issuer=CONFIG["issuer"], subject="kz3n8qvx2mp7rt9wf4yds", nickname="阿伟"
        )
        assert user.username == "kz3n8qvx2mp7rt9wf4yds"
        assert user.nickname == "阿伟"


def test_start_rejects_an_unknown_provider(client):
    response = client.get("/api/v2/auth/oidc/missing")
    assert response.status_code == 404


def local_user(app, username="carol", email="carol@example.com", verified=True):
    with app.app_context():
        user = create_user(username=username, password="secret123", email=email)
        #: 邮箱关联要求本地地址已验证，测试默认按已验证的账号准备。
        if verified:
            user.email_verified = True
            user.save(only=[User.email_verified])
        return user.id


def login(client, username="carol", password="secret123"):
    response = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password},
    )
    return response.get_json()["data"]["csrf"]


def test_verified_email_links_the_migrated_account(app, client, monkeypatch):
    user_id = local_user(app)
    enable_hook(app)
    module = hook_module(app)
    _, state = start_flow(client, monkeypatch, module)
    identity(
        module,
        monkeypatch,
        subject="u-2",
        username="carol-oidc",
        email="carol@example.com",
        email_verified=True,
    )

    response = client.get(
        "/api/v2/auth/oidc/passport/callback?code=c&state=%s" % state
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/albums"
    with app.app_context():
        user = User.get_by_id(user_id)
        assert user.oidc_subject == "u-2"
        assert User.select().count() == 1


def test_unverified_email_is_not_linked(app, client, monkeypatch):
    user_id = local_user(app)
    enable_hook(app)
    module = hook_module(app)
    _, state = start_flow(client, monkeypatch, module)
    identity(
        module,
        monkeypatch,
        subject="u-3",
        email="carol@example.com",
        email_verified=False,
    )

    response = client.get(
        "/api/v2/auth/oidc/passport/callback?code=c&state=%s" % state
    )

    #: provider 声明邮箱未验证时不关联老账号，而是按新用户建号。
    assert response.headers["Location"] == "/albums"
    with app.app_context():
        assert User.get_by_id(user_id).oidc_subject is None
        assert User.select().count() == 2


def test_unverified_local_email_is_not_linked(app, client, monkeypatch):
    user_id = local_user(app, verified=False)
    enable_hook(app)
    module = hook_module(app)
    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch, email="carol@example.com")

    response = client.get(
        "/api/v2/auth/oidc/passport/callback?code=c&state=%s" % state
    )

    #: 本地邮箱没过验证流程时不关联旧账号，而是按新用户建号。
    assert response.headers["Location"] == "/albums"
    with app.app_context():
        assert User.get_by_id(user_id).oidc_subject is None
        assert User.select().count() == 2


def test_bind_flow_links_the_signed_in_account(app, client, monkeypatch):
    user_id = local_user(app)
    enable_hook(app)
    module = hook_module(app)
    login(client)

    _, state = start_flow(
        client, monkeypatch, module, query="?bind=1&next=/settings"
    )
    identity(module, monkeypatch, subject="u-4", email="carol@example.com")

    response = client.get(
        "/api/v2/auth/oidc/passport/callback?code=c&state=%s" % state
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/settings?identity=bound"
    with app.app_context():
        assert User.get_by_id(user_id).oidc_subject == "u-4"


def test_bind_requires_a_signed_in_user(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)
    monkeypatch.setattr(
        module,
        "oidc_authorize_url",
        lambda config, redirect_uri, state: "https://x/authorize",
    )

    assert client.get("/api/v2/auth/oidc/passport?bind=1").status_code == 401


def test_identities_list_and_password_checked_unbind(app, client):
    user_id = local_user(app)
    enable_hook(app)
    csrf = login(client)

    items = client.get("/api/v2/auth/identities").get_json()["data"]["items"]
    passport = next(item for item in items if item["name"] == "passport")
    assert passport["bound"] is False
    query = parse_qs(urlparse(passport["bind_url"]).query)
    assert query == {"bind": ["1"], "next": ["/settings"]}

    with app.app_context():
        bind_oidc_identity(User.get_by_id(user_id), CONFIG["issuer"], "u-5")

    items = client.get("/api/v2/auth/identities").get_json()["data"]["items"]
    assert next(item for item in items if item["name"] == "passport")["bound"]

    headers = {"X-CSRF-Token": csrf}
    missing = client.delete("/api/v2/auth/identities/passport", headers=headers)
    assert missing.status_code == 403
    wrong = client.delete(
        "/api/v2/auth/identities/passport",
        json={"password": "nope"},
        headers=headers,
    )
    assert wrong.status_code == 403

    response = client.delete(
        "/api/v2/auth/identities/passport",
        json={"password": "secret123"},
        headers=headers,
    )
    assert response.status_code == 200
    with app.app_context():
        assert User.get_by_id(user_id).oidc_subject is None


def test_password_login_switch_blocks_login_and_registration(app, client):
    with app.app_context():
        set_setting("password_login", False)

    login_response = client.post(
        "/api/v2/auth/login",
        json={"username": "carol", "password": "secret123"},
    )
    assert login_response.status_code == 403
    assert login_response.get_json()["code"] == "FORBIDDEN"

    register_response = client.post(
        "/api/v2/auth/register",
        json={"username": "bob", "password": "secret123"},
    )
    assert register_response.status_code == 403


def test_login_slot_renders_the_button_over_http(app, client):
    enable_hook(app)

    response = client.get("/api/v2/hooks/slots/login.after_form")

    assert response.status_code == 200
    blocks = response.get_json()["data"]["blocks"]
    assert [block["hook"] for block in blocks] == ["passport"]
    link = next(node for node in blocks[0]["nodes"] if node["type"] == "link")
    assert link["href"] == "/api/v2/auth/oidc/passport"
