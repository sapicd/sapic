# -*- coding: utf-8 -*-
import os

import pytest

#: 测试按开发环境跑：生产配置会拒绝内置 SECRET_KEY，测试不依赖这一点。
os.environ.setdefault("sapic_env", "dev")

from sapic import create_app
from sapic.basis.db import db
from sapic.libs.settings import set_setting
from sapic.libs.storage import flush_replicas
from sapic.migrations import upgrade


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "DATABASE_URL": "sqlite:///%s" % (tmp_path / "test.db"),
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "REDIS_URL": "",
            "MAX_UPLOAD": 20,
            "STORAGE_DIR": str(tmp_path / "upload"),
        }
    )
    with app.app_context():
        upgrade()
        #: 多副本是后台异步写的，默认关掉以免无关用例出现竞态；
        #: tests/test_replicas.py 会自己打开。
        set_setting("storage_replica", False)
    yield app
    flush_replicas()
    if not db.is_closed():
        db.close()


@pytest.fixture()
def client(app):
    return app.test_client()
