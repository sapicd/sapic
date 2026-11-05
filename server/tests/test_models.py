# -*- coding: utf-8 -*-
import pytest
from peewee import IntegrityError

from sapic.models import Album, Image, StorageBackend, User, UserSetting


def test_user_album_image(app):
    with app.app_context():
        user = User.create(username="alice", password_hash="x", labels=[])
        album = Album.create(owner=user, name="默认")
        image = Image.create(
            sha="sha1.1.abc",
            owner=user,
            album=album,
            filename="a.png",
            size=10,
        )

        assert image.album.id == album.id
        assert User.get(User.username == "alice").id == user.id
        assert image.sha == "sha1.1.abc"


def test_unique_username(app):
    with app.app_context():
        User.create(username="alice", password_hash="x")
        with pytest.raises(IntegrityError):
            User.create(username="alice", password_hash="y")


def test_json_setting_roundtrip(app):
    with app.app_context():
        user = User.create(username="bob", password_hash="x")
        UserSetting.create(user=user, key="ucfg_mypic_limit", value={"n": 20})
        setting = UserSetting.get(UserSetting.key == "ucfg_mypic_limit")
        assert setting.value == {"n": 20}


def test_storage_priority_order(app):
    with app.app_context():
        StorageBackend.create(name="s3-a", hook_name="up2s3", priority=10)
        StorageBackend.create(name="s3-b", hook_name="up2s3", priority=20)

        #: 启动时会为启用的存储钩子自动建行（up2local），这里只比较本用例的行。
        names = [
            backend.name
            for backend in StorageBackend.select()
            .where(StorageBackend.hook_name == "up2s3")
            .order_by(StorageBackend.priority)
        ]
        assert names == ["s3-a", "s3-b"]
