# -*- coding: utf-8 -*-
from sapic.libs.userscript import USERSCRIPT_VERSION


def register_and_login(client, username="alice"):
    client.post(
        "/api/v2/auth/register",
        json={
            "username": username,
            "password": "secret123",
            "email": "%s@example.com" % username,
        },
    )
    response = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return response.get_json()["data"]["csrf"]


def create_token(client, csrf, scopes):
    response = client.post(
        "/api/v2/auth/tokens",
        json={"name": "userscript", "scopes": scopes},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["token"]


def enable(client, csrf, enabled=True):
    response = client.put(
        "/api/v2/auth/settings",
        json={"userscript_enabled": enabled},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()


def test_userscript_requires_login(app):
    assert app.test_client().get("/api/v2/userscript.user.js").status_code == 401


def test_userscript_is_off_by_default(app, client):
    register_and_login(client)
    assert client.get("/api/v2/userscript.user.js").status_code == 404


def test_userscript_serves_script_when_enabled(app, client):
    csrf = register_and_login(client)
    enable(client, csrf)

    response = client.get("/api/v2/userscript.user.js")
    assert response.status_code == 200
    assert response.mimetype == "text/javascript"
    assert response.headers["Cache-Control"] == "no-store"

    body = response.get_data(as_text=True)
    #: 脚本自己按站点根地址拼 API，且源码里不能出现任何令牌。
    assert "http://localhost/api/v2/uploads" in body
    assert "@version      %s" % USERSCRIPT_VERSION in body
    assert "GM_xmlhttpRequest" in body
    assert "@exclude      http://localhost/*" in body
    #: 更新地址要跟着安装地址走，否则装完就再也收不到更新。
    assert "@updateURL    http://localhost/api/v2/userscript.user.js" in body
    assert "@downloadURL  http://localhost/api/v2/userscript.user.js" in body
    assert "sp_" not in body


def test_old_root_install_url_is_gone(app, client):
    """脚本地址已挪到 /api/v2 下，老地址不能再是有效安装入口。"""
    csrf = register_and_login(client)
    enable(client, csrf)

    assert client.get("/sapic.user.js").status_code == 404


def test_userscript_install_url_accepts_upload_token(app, client):
    csrf = register_and_login(client)
    enable(client, csrf)
    token = create_token(client, csrf, ["upload"])

    anonymous = app.test_client()
    response = anonymous.get("/api/v2/userscript.user.js?token=%s" % token)
    assert response.status_code == 200
    #: 令牌只在 URL 里用于放行，不会被写进脚本文本。
    assert token not in response.get_data(as_text=True)


def test_userscript_url_token_needs_upload_scope(app, client):
    csrf = register_and_login(client)
    enable(client, csrf)

    anonymous = app.test_client()
    for scopes in (["read"], ["write"]):
        token = create_token(client, csrf, scopes)
        assert anonymous.get("/api/v2/userscript.user.js?token=%s" % token).status_code == 401


def test_userscript_disabling_revokes_the_install_url(app, client):
    csrf = register_and_login(client)
    enable(client, csrf)
    token = create_token(client, csrf, ["upload"])
    anonymous = app.test_client()
    assert anonymous.get("/api/v2/userscript.user.js?token=%s" % token).status_code == 200

    enable(client, csrf, False)
    assert anonymous.get("/api/v2/userscript.user.js?token=%s" % token).status_code == 404
