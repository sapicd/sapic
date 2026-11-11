# -*- coding: utf-8 -*-
"""``upimg_url``: drivers sign a temporary read address for private buckets."""

from hashlib import md5

import pytest

from sapic.libs import ext
from sapic.libs.hook import get_hook_manager


def module_of(app, name):
    with app.app_context():
        return get_hook_manager().get(name).module


def test_builtin_drivers_declare_their_read_capability(app):
    #: 有读契约的驱动才能被设成 private 后端。
    for name in ("up2local", "up2qiniu", "up2upyun", "up2github"):
        module = module_of(app, name)
        if name == "up2local":
            continue  # 本地副本由 /raw 直接读盘，不需要 upimg_url
        assert ext.supports_private_read(module) is True, name
    assert ext.supports_private_read(module_of(app, "up2gitee")) is False


def test_upyun_signature_matches_the_sdk(app):
    pytest.importorskip("upyun")
    from upyun.modules.sign import make_signature

    module = module_of(app, "up2upyun")
    date = "Sat, 07 Nov 2026 12:00:00 GMT"
    #: SDK 的 HMAC key 是密码的 md5，不是明文密码。
    expected = make_signature(
        username="op",
        password=md5(b"secret").hexdigest(),
        method="GET",
        uri="/demo/pics/a.png",
        date=date,
    )
    assert module._signature("op", "secret", "/demo/pics/a.png", date) == expected


def test_upyun_read_url_carries_rest_auth(app, monkeypatch):
    module = module_of(app, "up2upyun")
    if module.UpYun is None:
        monkeypatch.setattr(module, "UpYun", object)

    result = module.upimg_url(
        {"path": "/pics/a b.png"},
        backend={
            "config": {
                "bucket": "demo",
                "username": "op",
                "password": "secret",
            }
        },
    )

    assert result["code"] == 0
    #: 私有读走 REST 源站，域名（CDN）不认 Authorization 头。
    assert result["url"].startswith("https://v0.api.upyun.com/demo/")
    assert "%20" in result["url"]
    assert result["headers"]["Authorization"].startswith("UPYUN op:")
    assert result["headers"]["Date"].endswith("GMT")


def test_qiniu_read_url_is_signed_with_the_domain(app, monkeypatch):
    module = module_of(app, "up2qiniu")

    class FakeAuth:
        def __init__(self, access_key, secret_key):
            self.keys = (access_key, secret_key)

        def private_download_url(self, url, expires=3600):
            return "%s?e=%d&token=sig" % (url, expires)

    monkeypatch.setattr(module, "Auth", FakeAuth)

    result = module.upimg_url(
        {"path": "a.png"},
        backend={
            "config": {
                "bucket": "demo",
                "access_key": "ak",
                "secret_key": "sk",
                "domain": "https://cdn.example.com/",
            }
        },
    )

    assert result["code"] == 0
    assert result["url"] == "https://cdn.example.com/a.png?e=300&token=sig"

    #: 私有桶仍需域名来拼签名地址，缺了就明确报错。
    missing = module.upimg_url(
        {"path": "a.png"},
        backend={"config": {"bucket": "demo", "access_key": "ak", "secret_key": "sk"}},
    )
    assert missing["code"] == 1


def test_github_read_url_uses_the_contents_api(app):
    pytest.importorskip("requests")
    module = module_of(app, "up2github")

    result = module.upimg_url(
        {"path": "pics/a.png"},
        backend={"config": {"token": "tk", "repo": "u/r", "branch": "main"}},
    )

    assert result["code"] == 0
    assert result["url"] == (
        "https://api.github.com/repos/u/r/contents/pics/a.png?ref=main"
    )
    assert result["headers"]["Authorization"] == "token tk"
    #: raw.githubusercontent 不认 token，私有仓库必须用 contents API 的 raw 媒体类型。
    assert result["headers"]["Accept"] == "application/vnd.github.raw"
