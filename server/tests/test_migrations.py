# -*- coding: utf-8 -*-
from sapic.migrations import SchemaVersion, upgrade


def test_upgrade_is_idempotent(app):
    with app.app_context():
        assert upgrade() == []
        assert SchemaVersion.select().count() >= 1
