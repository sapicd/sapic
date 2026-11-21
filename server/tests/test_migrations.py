# -*- coding: utf-8 -*-
from sapic import create_app
from sapic.basis.db import db
from sapic.migrations import MIGRATIONS, SchemaVersion, upgrade
from sapic.models import User


def test_upgrade_is_idempotent(app):
    with app.app_context():
        assert upgrade() == []
        assert SchemaVersion.select().count() >= 1


def test_tags_column_is_added_to_existing_databases(app):
    """v003 back-fills databases created before image tags existed."""
    with app.app_context():
        db.execute_sql("ALTER TABLE images DROP COLUMN tags")
        SchemaVersion.delete().where(SchemaVersion.version == 3).execute()

        assert upgrade() == [3]
        columns = {column.name for column in db.get_columns("images")}
        assert "tags" in columns
        #: Re-running is a no-op, so concurrent boots stay safe.
        SchemaVersion.delete().where(SchemaVersion.version == 3).execute()
        assert upgrade() == [3]


def _drop_review_columns() -> None:
    """Remove the moderation columns (and their index) to simulate an old DB."""
    for index in db.get_indexes("images"):
        columns = tuple(getattr(index, "columns", None) or index[1] or ())
        if columns == ("review_state",):
            name = getattr(index, "name", None) or index[0]
            db.execute_sql('DROP INDEX IF EXISTS "%s"' % name)
    for column in ("review_state", "reviewed_at", "review_note"):
        db.execute_sql("ALTER TABLE images DROP COLUMN %s" % column)


def test_review_columns_are_added_when_earlier_numbers_were_recorded(app):
    """Recorded versions 13/14 must not swallow the moderation columns.

    13 was briefly shipped by an ``origin_url`` experiment and 14 by a setting
    cleanup, so databases that ran either hold those rows without the review
    columns. The moderation migration is numbered 15 and must still run there.
    """
    with app.app_context():
        _drop_review_columns()
        SchemaVersion.delete().where(SchemaVersion.version == 15).execute()
        #: 13（占位）与 14（设置清理）都已记录，不能挡住 15。
        assert SchemaVersion.get_or_none(SchemaVersion.version == 13) is not None
        assert SchemaVersion.get_or_none(SchemaVersion.version == 14) is not None

        assert upgrade() == [15]
        columns = {column.name for column in db.get_columns("images")}
        assert {"review_state", "reviewed_at", "review_note"} <= columns


def test_reused_version_number_is_rerun_by_name(app):
    """A number recorded by another migration must not block its current owner.

    Databases that ran an earlier revision of this tree recorded 15 as
    ``drop_external_base_url_setting``; the review columns still have to be
    created, which is why the check compares the name as well as the number.
    """
    with app.app_context():
        _drop_review_columns()
        SchemaVersion.update(name="drop_external_base_url_setting").where(
            SchemaVersion.version == 15
        ).execute()

        assert upgrade() == [15]
        columns = {column.name for column in db.get_columns("images")}
        assert {"review_state", "reviewed_at", "review_note"} <= columns
        #: 名字被改回当前定义，下次启动按同名跳过（见上面的幂等用例）。
        assert SchemaVersion.get(SchemaVersion.version == 15).name == "image_review"


def test_oidc_usernames_are_lowercased(app):
    """v018 把历史上 OIDC 建号留下的大写用户名改成小写，冲突时加数字后缀。"""
    with app.app_context():
        User.create(username="MixedCase", password_hash="x")
        User.create(username="mixedcase", password_hash="x")
        SchemaVersion.delete().where(SchemaVersion.version == 18).execute()

        assert upgrade() == [18]

        names = {user.username for user in User.select()}
        assert names == {"mixedcase", "mixedcase2"}


def test_create_app_migrates_on_boot(tmp_path):
    """A fresh database must be usable without running ``flask sa upgrade``."""
    app = create_app(
        {
            "DATABASE_URL": "sqlite:///%s" % (tmp_path / "boot.db"),
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "LOG_DIR": str(tmp_path / "log"),
        }
    )
    with app.app_context():
        assert SchemaVersion.select().count() == len(MIGRATIONS)
        assert app.test_client().get("/api/v2/site").status_code == 200
    if not db.is_closed():
        db.close()
