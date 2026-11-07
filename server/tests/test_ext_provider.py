# -*- coding: utf-8 -*-
"""A third-party auth provider plugs in without touching the core.

The package lives in ``HOOK_PKG_STORAGE_DIR`` and is registered by module name,
exactly like an installed distribution: no entry point, no core change.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sapic.libs.settings import set_setting
from sapic.libs.users import create_user

MODULE = "github_login"

PROVIDER = '''
__version__ = "0.1.0"
__author__ = "tester"
__catalog__ = "auth"
__state__ = "disabled"


def hook_manifest():
    return {
        "title": "GitHub 登录",
        "catalog": "auth",
        "slots": [{"name": "login.after_form"}],
    }


def identity_issuer(config=None):
    return "github"


def oidc_authorize_url(config=None, redirect_uri="", state=""):
    return "https://github.com/login/oauth/authorize?state=%s" % state


def oidc_exchange(config=None, code="", redirect_uri=""):
    return {
        "issuer": "github",
        #: 契约允许 OIDC 写法的 sub，核心会归一化成 subject。
        "sub": "42",
        "username": "octocat",
        "nickname": "The Octocat",
        "email": "octocat@example.com",
        "email_verified": False,
    }


def slot_login_after_form(context=None, **kwargs):
    return [
        {
            "type": "link",
            "text": "GitHub",
            "href": "/api/v2/auth/oidc/@MODULE@",
        }
    ]
'''.replace("@MODULE@", MODULE)


def install(app):
    target = Path(app.config["HOOK_PKG_STORAGE_DIR"])
    target.mkdir(parents=True, exist_ok=True)
    (target / ("%s.py" % MODULE)).write_text(PROVIDER, encoding="utf-8")
    if str(target) not in sys.path:
        sys.path.append(str(target))
    with app.app_context():
        set_setting("hooks_imported", [MODULE])
        set_setting("hooks_state", {MODULE: True})
        set_setting("hooks_config", {MODULE: {"client_id": "cid"}})
        app.extensions["hooks"].reload()


def uninstall(app):
    sys.modules.pop(MODULE, None)
    target = str(app.config["HOOK_PKG_STORAGE_DIR"])
    if target in sys.path:
        sys.path.remove(target)
    with app.app_context():
        set_setting("hooks_imported", [])
        set_setting("hooks_state", {})


def test_third_party_provider_is_recognised(app):
    install(app)
    try:
        manifest = app.extensions["hooks"].manifest(MODULE)
        assert manifest["family"] == "third"
        assert manifest["kind"] == "provider"
        assert manifest["warnings"] == []
    finally:
        uninstall(app)


def test_third_party_provider_starts_the_flow(app, client):
    install(app)
    try:
        response = client.get("/api/v2/auth/oidc/%s" % MODULE)

        assert response.status_code == 302
        location = response.headers["Location"]
        assert location.startswith("https://github.com/login/oauth/authorize")
        assert parse_qs(urlparse(location).query)["state"]
    finally:
        uninstall(app)


def test_third_party_provider_completes_a_login(app, client):
    install(app)
    try:
        start = client.get("/api/v2/auth/oidc/%s" % MODULE)
        state = parse_qs(urlparse(start.headers["Location"]).query)["state"][0]

        done = client.get(
            "/api/v2/auth/oidc/%s/callback?code=c1&state=%s" % (MODULE, state)
        )

        assert done.status_code == 302
        session = client.get("/api/v2/auth/session").get_json()["data"]
        assert session["authenticated"] is True
        assert session["user"]["username"] == "octocat"
    finally:
        uninstall(app)


def test_third_party_provider_lists_in_identities(app, client):
    install(app)
    try:
        with app.app_context():
            create_user(username="carol", password="secret123")
        login = client.post(
            "/api/v2/auth/login",
            json={"username": "carol", "password": "secret123"},
        )
        assert login.status_code == 200

        items = client.get("/api/v2/auth/identities").get_json()["data"]["items"]
        entry = next(item for item in items if item["name"] == MODULE)

        #: identity_issuer() 提供命名空间，绑定判定不依赖配置里有没有 issuer。
        assert entry["bound"] is False
        assert entry["title"] == "GitHub 登录"
    finally:
        uninstall(app)
