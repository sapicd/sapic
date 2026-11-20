# -*- coding: utf-8 -*-
"""Mail transport selection: a configured ``mail`` hook beats SMTP."""

from types import SimpleNamespace

import pytest

from sapic.basis.errors import ApiError
from sapic.libs import mail
from sapic.libs.hook import get_hook_manager
from sapic.libs.settings import set_setting

SENDCLOUD_CONFIG = {
    "api_user": "sapic",
    "api_key": "key",
    "from": "noreply@example.com",
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _fake_post(calls, payload=None):
    def post(url, data=None, timeout=None):
        calls.append({"url": url, "data": dict(data or {}), "timeout": timeout})
        return FakeResponse(
            payload or {"result": True, "statusCode": 200, "info": {"id": "1"}}
        )

    return post


class FakeSMTP:
    """Stand-in for ``smtplib.SMTP`` that records what was handed to it."""

    def __init__(self, used):
        self.used = used

    def __call__(self, host, port, timeout=None):
        self.used.append((host, port))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.used.append(("login", user))

    def starttls(self):
        self.used.append(("starttls",))

    def send_message(self, message):
        self.used.append(("sent", message["To"]))


@pytest.fixture()
def sendcloud(app, monkeypatch):
    """The built-in hook with its HTTP call captured."""
    calls = []
    with app.app_context():
        module = get_hook_manager().get("sendcloud").module
    monkeypatch.setattr(module, "requests", SimpleNamespace(post=_fake_post(calls)))
    return SimpleNamespace(calls=calls, module=module)


def test_configured_mail_hook_takes_over_from_smtp(app, client, sendcloud):
    with app.app_context():
        set_setting("hooks_config", {"sendcloud": SENDCLOUD_CONFIG})
        assert mail.mail_ready() is True
        assert mail.send_mail("user@example.com", "验证邮箱", "token-123") is True

    #: 站点接口把「邮件可用」透给前端；钩子配置与 SMTP 同等看待。
    assert client.get("/api/v2/site").get_json()["data"]["mail_enabled"] is True

    assert len(sendcloud.calls) == 1
    call = sendcloud.calls[0]
    assert call["url"].startswith("https://api.sendcloud.net/")
    assert call["data"]["apiUser"] == "sapic"
    assert call["data"]["from"] == "noreply@example.com"
    assert call["data"]["to"] == "user@example.com"
    #: 纯文本正文走 plain 字段（html 是富文本通道）。
    assert call["data"]["plain"] == "token-123"
    assert "html" not in call["data"]


def test_unconfigured_hook_leaves_smtp_in_charge(app, monkeypatch):
    used = []
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP(used))

    with app.app_context():
        set_setting(
            "smtp",
            {
                "host": "smtp.example.com",
                "port": 25,
                "user": "sapic",
                "password": "s3cret",
                "from": "sapic@example.com",
                "tls": False,
            },
        )
        #: 钩子已启用但没填必填项，不能抢走 SMTP 的发信职责。
        assert mail._mail_hook() is None
        assert mail.mail_ready() is True
        assert mail.send_mail("user@example.com", "subject", "body") is True

    assert used[0] == ("smtp.example.com", 25)
    assert used[-1] == ("sent", "user@example.com")


def test_disabled_hook_is_ignored(app, sendcloud):
    with app.app_context():
        set_setting("hooks_config", {"sendcloud": SENDCLOUD_CONFIG})
        set_setting("hooks_state", {"sendcloud": False})
        get_hook_manager().reload()
        assert mail._mail_hook() is None
        assert mail.mail_ready() is False


def test_hook_failure_is_logged_not_raised(app, sendcloud, monkeypatch):
    monkeypatch.setattr(
        sendcloud.module,
        "requests",
        SimpleNamespace(
            post=lambda *args, **kwargs: FakeResponse(
                {"result": False, "statusCode": 400, "message": "invalid from"}
            )
        ),
    )

    with app.app_context():
        set_setting("hooks_config", {"sendcloud": SENDCLOUD_CONFIG})
        #: 验证码邮件不能因为投递失败拖垮请求，只记日志。
        assert mail.send_mail("user@example.com", "subject", "body") is False
        with pytest.raises(ApiError) as caught:
            #: 后台测试邮件需要看到原因。
            mail.send_test_mail("user@example.com")

    assert "invalid from" in str(caught.value)
