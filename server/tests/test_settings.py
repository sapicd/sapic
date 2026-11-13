# -*- coding: utf-8 -*-
import io

import pytest

from sapic.basis.conf import _check_config_value
from sapic.basis.vars import DEFAULT_SECRET_KEY
from sapic.libs import mail
from sapic.libs.settings import get_setting, set_setting
from sapic.models import User
from sapic.utils.common import parse_proxy_url


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


def promote_admin(app, username="alice"):
    with app.app_context():
        user = User.get(User.username == username)
        user.is_admin = True
        user.save(only=[User.is_admin])


def test_production_accepts_builtin_secret_key(monkeypatch):
    """生产不再强制配置 SECRET_KEY；过短的仍然拒绝（见 tests/test_conf.py）。"""
    monkeypatch.delenv("sapic_env", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    config = {
        "LOG_LEVEL": "INFO",
        "MAX_UPLOAD": 20,
        "SESSION_TTL": 3600,
        "SECRET_KEY": DEFAULT_SECRET_KEY,
        "STORAGE_DIR": "/tmp",
    }
    _check_config_value(config)

    config["SECRET_KEY"] = "abc"
    with pytest.raises(AssertionError):
        _check_config_value(config)


def test_settings_requires_admin(client):
    register_and_login(client)
    assert client.get("/api/v2/settings").status_code == 403


def test_admin_reads_and_writes_settings(app, client):
    csrf = register_and_login(client)
    promote_admin(app)

    data = client.get("/api/v2/settings").get_json()["data"]["items"]
    assert data["site_name"] == "sapic"
    #: 图片与视频有各自的默认上限（10M / 20M）。
    assert data["upload_image_max_size"] == 10
    assert data["upload_video_max_size"] == 20

    response = client.put(
        "/api/v2/settings",
        json={
            "site_name": "我的图床",
            "upload_image_max_size": 5,
            "upload_video_max_size": 8,
            "allow_video": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    items = response.get_json()["data"]["items"]
    assert items["site_name"] == "我的图床"
    assert items["upload_image_max_size"] == 5
    assert items["upload_video_max_size"] == 8
    assert items["allow_video"] is False

    site = client.get("/api/v2/site").get_json()["data"]
    assert site["name"] == "我的图床"
    assert site["allow_video"] is False


def test_login_notice_is_editable_and_public(app, client):
    """登录页提示由后台维护：改了走公开站点接口，清空就整句不显示。"""
    csrf = register_and_login(client)
    promote_admin(app)

    payload = client.get("/api/v2/settings").get_json()["data"]
    assert payload["items"]["login_notice"] == "登录后可上传与管理图片"
    assert "login_notice" in payload["editable"]

    updated = client.put(
        "/api/v2/settings",
        json={"login_notice": "欢迎回到私有图床"},
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.status_code == 200, updated.get_json()

    site = client.get("/api/v2/site").get_json()["data"]
    assert site["login_notice"] == "欢迎回到私有图床"

    client.put(
        "/api/v2/settings",
        json={"login_notice": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert client.get("/api/v2/site").get_json()["data"]["login_notice"] == ""


def test_settings_reject_invalid_value(app, client):
    csrf = register_and_login(client)
    promote_admin(app)

    response = client.put(
        "/api/v2/settings",
        json={"upload_image_max_size": "abc"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "PARAM_ERROR"

    response = client.put(
        "/api/v2/settings",
        json={"not_a_setting": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400


def test_upload_respects_site_limits(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    client.put(
        "/api/v2/settings",
        json={"upload_allowed_ext": "png", "upload_image_max_size": 1},
        headers={"X-CSRF-Token": csrf},
    )

    rejected = client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"GIF89a"), "photo.gif")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["code"] == "PARAM_ERROR"

    too_big = client.post(
        "/api/v2/upload",
        data={"file": (io.BytesIO(b"x" * (1024 * 1024 + 1)), "photo.png")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf},
    )
    assert too_big.status_code == 413


def test_upload_limits_are_per_media_type(app, client):
    """图片与视频各有上限：视频可以比图片大，但同样会被阈值拦住。"""
    mb = 1024 * 1024
    csrf = register_and_login(client)
    promote_admin(app)
    client.put(
        "/api/v2/settings",
        json={"upload_image_max_size": 1, "upload_video_max_size": 3},
        headers={"X-CSRF-Token": csrf},
    )

    def post(name, size):
        return client.post(
            "/api/v2/upload",
            data={"file": (io.BytesIO(b"x" * size), name)},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": csrf},
        )

    #: 2MB 图片超过 1MB 的图片上限。
    assert post("photo.png", 2 * mb).status_code == 413
    #: 同一个 2MB 的视频仍在 3MB 的视频上限内。
    assert post("clip.mp4", 2 * mb).status_code == 201
    assert post("clip2.mp4", 4 * mb).status_code == 413


def test_register_review_and_reserved_username(app, client):
    csrf = register_and_login(client)
    promote_admin(app)
    client.put(
        "/api/v2/settings",
        json={"register_review": True, "forbidden_username": "root,system"},
        headers={"X-CSRF-Token": csrf},
    )

    guest = app.test_client()
    reserved = guest.post(
        "/api/v2/auth/register",
        json={"username": "root", "password": "secret123"},
    )
    assert reserved.status_code == 400

    response = guest.post(
        "/api/v2/auth/register",
        json={"username": "bobby", "password": "secret123"},
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["user"]["status"] == -1

    #: 待审核账号不能登录，否则「审核」形同虚设。
    denied = guest.post(
        "/api/v2/auth/login",
        json={"username": "bobby", "password": "secret123"},
    )
    assert denied.status_code == 403


def smtp_block(**overrides):
    config = {
        "host": "smtp.example.com",
        "port": 587,
        "user": "operator",
        "password": "s3cret",
        "from": "sapic@example.com",
        "tls": True,
    }
    config.update(overrides)
    return config


def test_smtp_settings_are_masked_and_kept(app, client):
    """密钥只回掩码；回传掩码表示不改密码，否则每次保存都会清空它。"""
    csrf = register_and_login(client)
    promote_admin(app)

    response = client.put(
        "/api/v2/settings",
        json={"smtp": smtp_block()},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    smtp = response.get_json()["data"]["items"]["smtp"]
    assert smtp["host"] == "smtp.example.com"
    assert smtp["port"] == 587
    assert smtp["password"] == "********"
    assert "s3cret" not in response.get_data(as_text=True)

    with app.app_context():
        assert get_setting("smtp")["password"] == "s3cret"

    echoed = client.put(
        "/api/v2/settings",
        json={"smtp": {**smtp, "port": 25}},
        headers={"X-CSRF-Token": csrf},
    )
    assert echoed.status_code == 200, echoed.get_json()
    with app.app_context():
        config = get_setting("smtp")
    assert config["password"] == "s3cret"
    assert config["port"] == 25

    #: 公开信息只说「邮件可用」，不泄露服务器与账号。
    site = client.get("/api/v2/site").get_json()["data"]
    assert site["mail_enabled"] is True
    assert "smtp.example.com" not in str(site)

    #: 清空 host 即停用邮件，前端据此隐藏验证入口。
    client.put(
        "/api/v2/settings",
        json={"smtp": {**smtp, "host": ""}},
        headers={"X-CSRF-Token": csrf},
    )
    assert client.get("/api/v2/site").get_json()["data"]["mail_enabled"] is False


def test_smtp_settings_reject_bad_values(app, client):
    csrf = register_and_login(client)
    promote_admin(app)

    for payload in (
        {"smtp": "smtp.example.com"},
        {"smtp": smtp_block(port=0)},
        {"smtp": smtp_block(port="abc")},
        {"smtp": smtp_block(tls="yes")},
        {"smtp": {**smtp_block(), "unexpected": 1}},
    ):
        response = client.put(
            "/api/v2/settings",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 400, payload
        assert response.get_json()["code"] == "PARAM_ERROR"


def test_smtp_test_mail_requires_configuration(app, client):
    csrf = register_and_login(client)
    promote_admin(app)

    response = client.post(
        "/api/v2/settings/smtp/test",
        json={"to": "ops@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 503
    assert response.get_json()["code"] == "SERVICE_UNAVAILABLE"

    #: 非管理员不能借测试接口探测服务器配置。
    other = app.test_client()
    assert other.post("/api/v2/settings/smtp/test", json={}).status_code in (401, 403)


#: Transport calls recorded by the fake SMTP clients below.
used: list = []


class FakeSMTP:
    """Stand-in for ``smtplib.SMTP`` that records how it was opened."""

    def __init__(self, host, port, timeout=None):
        used.append((type(self).__name__, host, port, timeout))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        used.append("starttls")

    def login(self, user, password):
        used.append("login")

    def send_message(self, message):
        used.append("send")


class FakeSMTPSSL(FakeSMTP):
    pass


def test_smtp_port_465_uses_implicit_ssl(app, monkeypatch):
    """465 是隐式 SSL：用明文 SMTP 连会双向等待握手，只表现为连接超时。"""
    used.clear()
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTPSSL)

    with app.app_context():
        set_setting(
            "smtp",
            {
                "host": "smtp.qiye.aliyun.com",
                "port": 465,
                "user": "noreply@saintic.com",
                "password": "s3cret",
                "from": "noreply@saintic.com",
                "tls": False,
            },
        )
        mail._deliver("me@example.com", "subject", "body")

    assert used[0] == ("FakeSMTPSSL", "smtp.qiye.aliyun.com", 465, 10)
    assert "starttls" not in used
    assert used[-1] == "send"


def test_smtp_port_587_upgrades_with_starttls(app, monkeypatch):
    used.clear()
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTPSSL)

    with app.app_context():
        set_setting(
            "smtp",
            {
                "host": "smtp.example.com",
                "port": 587,
                "user": "",
                "password": "",
                "from": "sapic@example.com",
                "tls": True,
            },
        )
        mail._deliver("me@example.com", "subject", "body")

    assert used[0] == ("FakeSMTP", "smtp.example.com", 587, 10)
    assert used[1] == "starttls"
    assert "login" not in used


def test_upload_fetch_proxy_requires_an_http_url(app, client):
    """代理只接受 http(s)：urllib 不支持 socks，写错在保存时就拒掉。"""
    csrf = register_and_login(client)
    promote_admin(app)

    for value in (
        "127.0.0.1:7890",  # 缺 scheme
        "socks5://127.0.0.1:1080",  # socks 不支持
        "http://",  # 缺 host
        "http://1.1.1.1:99999",  # 端口越界
    ):
        response = client.put(
            "/api/v2/settings",
            json={"upload_fetch_proxy": value},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 400, value
        assert response.get_json()["code"] == "PARAM_ERROR"

    #: basic auth 的代理照收，尾部斜杠原样保存。
    proxy = "http://user:pass@127.0.0.1:7890/"
    response = client.put(
        "/api/v2/settings",
        json={"upload_fetch_proxy": proxy},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["items"]["upload_fetch_proxy"] == proxy
    assert "upload_fetch_proxy" in data["editable"]

    #: 留空是合法值，表示回到直连。
    response = client.put(
        "/api/v2/settings",
        json={"upload_fetch_proxy": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.get_json()


def test_parse_proxy_url_accepts_and_rejects():
    assert parse_proxy_url("  http://user:pass@127.0.0.1:7890/ ") == (
        "http://user:pass@127.0.0.1:7890/"
    )
    assert parse_proxy_url("https://proxy.example.com:8080") == (
        "https://proxy.example.com:8080"
    )
    #: 空值表示不配置代理，不是错误。
    assert parse_proxy_url("") == ""

    for raw in ("127.0.0.1:7890", "socks5://127.0.0.1:1080", "http://"):
        with pytest.raises(ValueError):
            parse_proxy_url(raw)
