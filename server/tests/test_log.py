# -*- coding: utf-8 -*-
"""File logging: the application log only; requests are not recorded."""

import logging
from pathlib import Path

from sapic import create_app
from sapic.basis import log as log_module
from sapic.basis.db import db


def _build(tmp_path, **overrides):
    config = {
        "DATABASE_URL": "sqlite:///%s" % (tmp_path / "test.db"),
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "STORAGE_DIR": str(tmp_path / "upload"),
        "HOOK_PKG_STORAGE_DIR": str(tmp_path / "hooks"),
        "LOG_DIR": str(tmp_path / "log"),
    }
    config.update(overrides)
    return create_app(config)


def _logs(tmp_path) -> Path:
    return Path(tmp_path) / "log"


def test_application_log_is_written(tmp_path):
    """应用到文件的日志落地，且不掺访问记录。"""
    app = _build(tmp_path)
    try:
        assert app.test_client().get("/api/v2/site").status_code == 200
        logging.getLogger("sapic.test").info("hello from the tests")
        for handler in logging.getLogger().handlers:
            handler.flush()

        content = (_logs(tmp_path) / "sys.log").read_text(encoding="utf-8")
        assert "hello from the tests" in content
        #: 没有访问日志：请求本身不会出现在 sys.log 里。
        assert "/api/v2/site" not in content
    finally:
        db.close()


def test_unwritable_log_dir_keeps_the_app_booting(tmp_path, monkeypatch):
    """日志目录写不了只降级为标准错误，不能因此起不来。"""

    def broken(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(log_module, "_handler", broken)
    app = _build(tmp_path)
    try:
        assert app.test_client().get("/api/v2/site").status_code == 200
        assert not _logs(tmp_path).exists()
    finally:
        db.close()


def test_empty_log_dir_keeps_file_logging_off(tmp_path):
    """``LOG_DIR`` 置空只保留标准错误输出，不创建目录。"""
    app = _build(tmp_path, LOG_DIR="")
    try:
        assert app.test_client().get("/api/v2/site").status_code == 200
        assert not _logs(tmp_path).exists()
    finally:
        db.close()
