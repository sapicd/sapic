# -*- coding: utf-8 -*-
"""Extension point contracts: provider, storage driver and identity payloads."""

import pytest

from sapic.libs import ext
from sapic.libs.hook import HookManager

PROVIDER = '''
__version__ = "1.0.0"
__author__ = "tester"
__catalog__ = "auth"


def oidc_authorize_url(config=None, redirect_uri="", state=""):
    return "https://provider/authorize"


def oidc_exchange(config=None, code="", redirect_uri=""):
    return {"subject": "u-1"}


def identity_issuer(config=None):
    return "demo"
'''

DRIVER_WITHOUT_DELETE = '''
__version__ = "1.0.0"
__author__ = "tester"
__catalog__ = "upload"


def upimg_save(**kwargs):
    return {"code": 0}
'''

INCOMPLETE_PROVIDER = '''
__version__ = "1.0.0"
__author__ = "tester"
__catalog__ = "auth"


def oidc_authorize_url(config=None, redirect_uri="", state=""):
    return "https://provider/authorize"
'''

PLAIN_UI_HOOK = '''
__version__ = "1.0.0"
__author__ = "tester"


def hook_manifest():
    return {"title": "Plain", "slots": [{"name": "nav"}]}
'''


def load(tmp_path, name, source):
    (tmp_path / ("%s.py" % name)).write_text(source, encoding="utf-8")
    return HookManager([tmp_path])


def test_provider_contract_needs_catalog_and_both_functions(tmp_path):
    manager = load(tmp_path, "demo", PROVIDER)
    module = manager.get("demo").module

    assert ext.is_provider(module) is True
    assert ext.kind_of(module) == ext.KIND_PROVIDER
    assert ext.warnings_of(module) == []

    manager = load(tmp_path, "half", INCOMPLETE_PROVIDER)
    module = manager.get("half").module
    assert ext.is_provider(module) is False
    #: 声明了 auth 却缺函数：kind 仍按声明上报，warnings 说明缺什么。
    assert ext.kind_of(module) == ext.KIND_PROVIDER
    assert ext.warnings_of(module) == [
        "auth provider is missing required function: oidc_exchange"
    ]


def test_driver_contract_only_requires_upimg_save(tmp_path):
    manager = load(tmp_path, "driver", DRIVER_WITHOUT_DELETE)
    module = manager.get("driver").module

    assert ext.is_driver(module) is True
    assert ext.kind_of(module) == ext.KIND_DRIVER
    #: 没有 upimg_delete 只是降级（副本删不掉），不算不可用。
    assert ext.warnings_of(module) == [
        "storage driver is missing upimg_delete: stored objects cannot be removed"
    ]


def test_plain_hook_has_no_extension_contract(tmp_path):
    manager = load(tmp_path, "plain", PLAIN_UI_HOOK)
    module = manager.get("plain").module

    assert ext.kind_of(module) == ext.KIND_UI
    assert ext.is_provider(module) is False
    assert ext.is_driver(module) is False
    assert ext.is_processor(module) is False
    assert ext.warnings_of(module) == []


def test_manifest_carries_kind_and_warnings(tmp_path):
    manager = load(tmp_path, "demo", PROVIDER)
    manifest = manager.manifest("demo")

    assert manifest["kind"] == ext.KIND_PROVIDER
    assert manifest["warnings"] == []

    manager = load(tmp_path, "half", INCOMPLETE_PROVIDER)
    assert manager.manifest("half")["warnings"]


def test_normalize_identity_accepts_the_oidc_spelling():
    identity = ext.normalize_identity(
        {
            "iss": "ignored",
            "sub": " u-1 ",
            "nickname": "Alice",
            "email": " Alice@Example.com ",
            "email_verified": "true",
        }
    )

    assert identity == {
        "issuer": "",
        "subject": "u-1",
        #: 没给 username 时回落到 subject，避免第三方 Provider 漏字段。
        "username": "u-1",
        "nickname": "Alice",
        "email": "Alice@Example.com",
        "email_verified": True,
    }


def test_normalize_identity_requires_a_subject():
    with pytest.raises(ValueError):
        ext.normalize_identity({"email": "a@example.com"})
    with pytest.raises(ValueError):
        ext.normalize_identity(None)


def test_identity_issuer_overrides_the_config_field(tmp_path):
    manager = load(tmp_path, "demo", PROVIDER)
    module = manager.get("demo").module

    assert ext.provider_issuer(module, {"issuer": "https://config"}) == "demo"

    #: 未实现 identity_issuer 时回落到配置里的 issuer 字段。
    manager = load(tmp_path, "half", INCOMPLETE_PROVIDER)
    module = manager.get("half").module
    assert ext.provider_issuer(module, {"issuer": "https://config/"}) == (
        "https://config/"
    )
    assert ext.provider_issuer(module, {}) == ""
