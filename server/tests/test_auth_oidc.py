# -*- coding: utf-8 -*-
"""Passport (OIDC) login: the start/callback flow and the hook contract."""

from urllib.parse import parse_qs, urlparse

from sapic.libs.settings import set_setting
from sapic.models import User

CONFIG = {
    "issuer": "https://passport.example.com",
    "client_id": "sp-client",
    "client_secret": "sp-secret",
    "auto_register": True,
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
    response = client.get("/api/v1/auth/oidc/passport" + query)
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
        "auto_register",
    ]
    assert manifest["slots"] == [
        {"name": "login.after_form", "mode": "declarative"}
    ]


def test_login_slot_only_renders_when_configured(app):
    module = hook_module(app)
    assert module.slot_login_after_form(context={"config": {}}) == []

    nodes = module.slot_login_after_form(
        context={"config": {"issuer": CONFIG["issuer"], "client_id": "sp-client"}}
    )
    link = next(node for node in nodes if node["type"] == "link")
    assert link["href"] == "/api/v1/auth/oidc/passport"


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
            "preferred_username": "bobby",
            "name": "Bobby",
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
        "username": "bobby",
        "nickname": "Bobby",
        "email": "bobby@example.com",
    }
    token_call = next(call for call in fake.calls if call[0] == "post")
    assert token_call[2]["data"]["grant_type"] == "authorization_code"
    userinfo_call = next(
        call for call in fake.calls if call[1] == DISCOVERY["userinfo_endpoint"]
    )
    assert userinfo_call[2]["headers"]["Authorization"] == "Bearer at-1"


def test_start_redirects_and_sets_the_state_cookie(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)
    response, state = start_flow(client, monkeypatch, module)

    assert response.status_code == 302
    assert state
    assert "sapic-oidc" in response.headers.get("Set-Cookie", "")


def test_callback_creates_the_user_and_starts_a_session(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)
    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch)

    response = client.get(
        "/api/v1/auth/oidc/passport/callback?code=code-1&state=%s" % state
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/albums"

    session = client.get("/api/v1/auth/session").get_json()["data"]
    assert session["authenticated"] is True
    assert session["user"]["username"] == "alice"

    with app.app_context():
        user = User.get(User.username == "alice")
        assert user.oidc_subject == "u-1"
        assert user.oidc_issuer == CONFIG["issuer"]


def test_second_login_reuses_the_bound_account(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)

    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch)
    client.get("/api/v1/auth/oidc/passport/callback?code=c1&state=%s" % state)
    first = client.get("/api/v1/auth/session").get_json()["data"]["user"]

    #: 上游改名后仍然绑定到同一个本地账号，也不会再建新账号。
    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch, username="alice-renamed", nickname="Renamed")
    client.get("/api/v1/auth/oidc/passport/callback?code=c2&state=%s" % state)
    second = client.get("/api/v1/auth/session").get_json()["data"]["user"]

    assert first["id"] == second["id"]
    with app.app_context():
        assert User.select().count() == 1


def test_callback_rejects_a_forged_state(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)
    identity(module, monkeypatch)

    response = client.get(
        "/api/v1/auth/oidc/passport/callback?code=code-1&state=forged"
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"


def test_unlinked_account_is_rejected_without_auto_register(app, client, monkeypatch):
    enable_hook(app, dict(CONFIG, auto_register=False))
    module = hook_module(app)
    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch)

    response = client.get(
        "/api/v1/auth/oidc/passport/callback?code=code-1&state=%s" % state
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/login?oidc=error"
    session = client.get("/api/v1/auth/session").get_json()["data"]
    assert session["authenticated"] is False


def test_start_rejects_an_unknown_provider(client):
    response = client.get("/api/v1/auth/oidc/missing")
    assert response.status_code == 404


def test_oidc_users_get_a_default_album(app, client, monkeypatch):
    enable_hook(app)
    module = hook_module(app)
    _, state = start_flow(client, monkeypatch, module)
    identity(module, monkeypatch)
    client.get("/api/v1/auth/oidc/passport/callback?code=code-1&state=%s" % state)

    albums = client.get("/api/v1/albums").get_json()["data"]["items"]
    assert [album["name"] for album in albums] == ["默认相册"]


def test_login_slot_renders_the_button_over_http(app, client):
    enable_hook(app)

    response = client.get("/api/v1/hooks/slots/login.after_form")

    assert response.status_code == 200
    blocks = response.get_json()["data"]["blocks"]
    assert [block["hook"] for block in blocks] == ["passport"]
    link = next(node for node in blocks[0]["nodes"] if node["type"] == "link")
    assert link["href"] == "/api/v1/auth/oidc/passport"
