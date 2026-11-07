# -*- coding: utf-8 -*-
from sapic.models import UserSetting


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


def read_settings(client):
    response = client.get("/api/v2/auth/settings")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["settings"]


def put_settings(client, csrf, values):
    return client.put(
        "/api/v2/auth/settings", json=values, headers={"X-CSRF-Token": csrf}
    )


def test_settings_defaults(app, client):
    register_and_login(client)
    assert read_settings(client) == {
        "userscript_enabled": False,
        "bg_image": "",
        "bg_image_mobile": "",
        "bg_opacity": None,
        "hotlink_enabled": False,
        "hotlink_allow_hosts": "",
        "hotlink_allow_empty": True,
    }


def test_settings_require_login(client):
    assert client.get("/api/v2/auth/settings").status_code == 401


def test_settings_roundtrip_and_partial_update(app, client):
    csrf = register_and_login(client)
    response = put_settings(
        client,
        csrf,
        {
            "userscript_enabled": True,
            "bg_image": "https://cdn.example.com/a.jpg",
            "bg_opacity": 0.35,
        },
    )
    assert response.status_code == 200, response.get_json()
    settings = response.get_json()["data"]["settings"]
    assert settings["userscript_enabled"] is True
    assert settings["bg_image"] == "https://cdn.example.com/a.jpg"
    assert settings["bg_opacity"] == 0.35

    #: 只提交一个键时其它键保持原值，UI 才能分块保存。
    assert put_settings(client, csrf, {"bg_image_mobile": "/static/m.jpg"}).status_code == 200
    settings = read_settings(client)
    assert settings["bg_image_mobile"] == "/static/m.jpg"
    assert settings["bg_image"] == "https://cdn.example.com/a.jpg"
    #: 未提交的键保持原值。
    assert settings["userscript_enabled"] is True

    with app.app_context():
        assert UserSetting.select().count() == 4


def test_settings_are_per_user(app, client):
    csrf = register_and_login(client)
    put_settings(client, csrf, {"userscript_enabled": True})

    bobby = app.test_client()
    register_and_login(bobby, "bobby")
    assert read_settings(bobby)["userscript_enabled"] is False


def test_settings_reject_invalid_input(app, client):
    csrf = register_and_login(client)

    assert put_settings(client, csrf, {}).status_code == 400
    assert put_settings(client, csrf, {"nope": 1}).status_code == 400
    #: 背景只允许 http(s) 或站内绝对路径，挡掉可执行载荷与协议相对地址。
    assert put_settings(client, csrf, {"bg_image": "javascript:alert(1)"}).status_code == 400
    assert put_settings(client, csrf, {"bg_image": "//evil.example.com/x.jpg"}).status_code == 400
    assert put_settings(client, csrf, {"bg_opacity": 2}).status_code == 400
    assert put_settings(client, csrf, {"userscript_enabled": "maybe"}).status_code == 400
    #: 已删除的配置项不再接受，旧客户端写入会得到 400 而不是静默保存。
    assert put_settings(client, csrf, {"rss_enabled": True}).status_code == 400

    #: 校验失败不能留下半份数据。
    assert read_settings(client)["bg_image"] == ""
