# -*- coding: utf-8 -*-
import pytest

from sapic import create_app
from sapic.extensions import db
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
    yield app
    if not db.is_closed():
        db.close()


@pytest.fixture()
def client(app):
    return app.test_client()
