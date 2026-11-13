# -*- coding: utf-8 -*-
import pytest

from sapic.basis import conf
from sapic.basis.vars import DEFAULT_SECRET_KEY


def _isolate(monkeypatch, tmp_path):
    """只读环境变量与默认值，避免开发机上的 server/.cfg 影响断言。"""
    monkeypatch.setattr(conf, "CFG_FILE", str(tmp_path / "absent.cfg"))
    for name in ("sapic_db_url", "sapic_storagedir", "sapic_secretkey"):
        monkeypatch.delenv(name, raising=False)


def test_production_accepts_the_builtin_secret_key(monkeypatch, tmp_path):
    """生产不再强制配置 SECRET_KEY：默认值够长，单机开箱即用。"""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("sapic_env", "production")

    config = conf.load_config()

    assert config["ENV"] == "production"
    assert config["DEBUG"] is False
    assert config["SECRET_KEY"] == DEFAULT_SECRET_KEY


def test_empty_secret_key_falls_back_to_the_default(monkeypatch, tmp_path):
    """显式写成空值（.cfg 或环境变量）按默认处理，而不是启动失败。"""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("sapic_env", "production")
    monkeypatch.setenv("sapic_secretkey", "")

    assert conf.load_config()["SECRET_KEY"] == DEFAULT_SECRET_KEY


def test_short_secret_key_is_still_rejected(monkeypatch, tmp_path):
    """太短的密钥仍然拒绝：随便填个 'abc' 比默认值更不安全。"""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("sapic_env", "production")
    monkeypatch.setenv("sapic_secretkey", "abc")

    with pytest.raises(AssertionError):
        conf.load_config()


def test_configured_secret_key_is_kept(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("sapic_env", "production")
    monkeypatch.setenv("sapic_secretkey", "x" * 32)

    assert conf.load_config()["SECRET_KEY"] == "x" * 32
