# -*- coding: utf-8 -*-
from sapic import create_app
from sapic.basis.db import db
from sapic.migrations import MIGRATIONS, SchemaVersion, upgrade


def test_upgrade_is_idempotent(app):
    with app.app_context():
        assert upgrade() == []
        assert SchemaVersion.select().count() >= 1


def test_create_app_migrates_on_boot(tmp_path):
    """A fresh database must be usable without running ``flask sa upgrade``."""
    app = create_app(
        {
            "DATABASE_URL": "sqlite:///%s" % (tmp_path / "boot.db"),
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "REDIS_URL": "",
        }
    )
    with app.app_context():
        assert SchemaVersion.select().count() == len(MIGRATIONS)
        assert app.test_client().get("/api/v1/images").status_code == 200
    if not db.is_closed():
        db.close()
