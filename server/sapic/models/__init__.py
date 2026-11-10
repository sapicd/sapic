# -*- coding: utf-8 -*-
"""Peewee models.

Import order matters only for readability; Peewee resolves foreign keys by
class reference, and ``db.create_tables`` sorts dependencies.
"""

from .album import Album
from .base import BaseModel, JSONTextField, now
from .image import Image
from .setting import Setting
from .share import AlbumShare
from .storage import ImageBackend, StorageBackend, UserBackend
from .token import ApiToken, UploadTicket
from .user import User, UserSetting

ALL_MODELS = [
    User,
    UserSetting,
    Album,
    Image,
    StorageBackend,
    UserBackend,
    ImageBackend,
    UploadTicket,
    ApiToken,
    AlbumShare,
    Setting,
]

__all__ = [
    "ALL_MODELS",
    "Album",
    "AlbumShare",
    "ApiToken",
    "BaseModel",
    "Image",
    "ImageBackend",
    "JSONTextField",
    "Setting",
    "StorageBackend",
    "UploadTicket",
    "User",
    "UserBackend",
    "UserSetting",
    "now",
]
