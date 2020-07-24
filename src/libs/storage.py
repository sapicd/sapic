# -*- coding: utf-8 -*-
"""
    libs.storage
    ~~~~~~~~~~~~

    Not core data storage.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import json
import shelve
from tempfile import gettempdir
from os.path import join, abspath
from utils._compat import PY2, text_type, iteritems
from utils.tool import rsp, create_redis_engine


def get_storage(local_path=None, redis_index=None):
    """Project global definition data store backend"""
    from config import STORAGE
    if STORAGE["Method"] == "local":
        return LocalStorage(path=local_path or STORAGE.get("LocalPath"))
    elif STORAGE["Method"] == "redis":
        return RedisStorage(
            index=redis_index or STORAGE.get("RedisIndex"),
            redis_url=STORAGE.get("RedisURL")
        )
    else:
        raise ValueError("Invalid storage method")


class BaseStorage(object):
    """This is the base class for storage.
    The available storage classes need to inherit from :class:`~BaseStorage`
    and override the `get` and `set` methods, it's best to implement
    the remote method as well.

    This base class customizes the `__getitem__`, `__setitem__`
    and `__delitem__` methods so that the user can call it like a dict.
    """

    #: The default index, as the only key, you can override it.
    DEFAULT_INDEX = "picbed_dat"

    @property
    def index(self):
        return getattr(self, "COVERED_INDEX", None) or self.DEFAULT_INDEX

    def __getitem__(self, key):
        if hasattr(self, "get"):
            return self.get(key)
        else:
            raise AttributeError("Please override the get method")

    def __setitem__(self, key, value):
        if hasattr(self, "set"):
            return self.set(key, value)
        else:
            raise AttributeError("Please override the set method")

    def __delitem__(self, key):
        if hasattr(self, "remove"):
            return self.remove(key)
        else:
            return False

    def __str__(self):
        return "<%s object at %s, index is %s>" % (
            self.__class__.__name__, hex(id(self)), self.index
        )

    __repr__ = __str__


class LocalStorage(BaseStorage):
    """Local file system storage based on the shelve module."""

    DEFAULT_INDEX = "picbed.dat"

    def __init__(self, path=None):
        self.COVERED_INDEX = path or join(gettempdir(), self.DEFAULT_INDEX)

    def _open(self, flag="c"):
        return shelve.open(
            filename=abspath(self.COVERED_INDEX),
            flag=flag,
            protocol=2,
            writeback=False
        )

    @property
    def list(self):
        """list all data

        :returns: dict
        """
        db = None
        try:
            db = self._open("r")
        except:
            return {}
        else:
            return dict(db)
        finally:
            if db:
                db.close()

    def __ck(self, key):
        if PY2 and isinstance(key, text_type):
            key = key.encode("utf-8")
        if not PY2 and not isinstance(key, text_type):
            key = key.decode("utf-8")
        return key

    def set(self, key, value):
        """Set persistent data with shelve.

        :param key: Index key

        :param value: All supported data types in python
        """
        db = self._open()
        try:
            db[self.__ck(key)] = value
        finally:
            db.close()

    def setmany(self, **mapping):
        if mapping and isinstance(mapping, dict):
            db = self._open()
            for k, v in iteritems(mapping):
                db[self.__ck(k)] = v
            db.close()

    def get(self, key, default=None):
        """Get persistent data from shelve.

        :returns: data
        """
        try:
            value = self.list[key]
        except KeyError:
            return default
        else:
            return value

    def remove(self, key):
        db = self._open()
        del db[key]

    def __len__(self):
        return len(self.list)


class RedisStorage(BaseStorage):
    """Use redis stand-alone storage"""

    DEFAULT_INDEX = rsp("dat")

    def __init__(self, index=None, redis_url=None, redis_connection=None):
        self.COVERED_INDEX = index
        self._db = self._open(redis_url) if redis_url else redis_connection

    def _open(self, redis_url):
        try:
            return create_redis_engine(redis_url)
        except ImportError:
            raise ImportError(
                "Please install the redis module, eg: pip install redis"
            )

    @property
    def list(self):
        """list redis hash data"""
        return {
            k: json.loads(v)
            for k, v in iteritems(self._db.hgetall(self.index))
        }

    def set(self, key, value):
        """set key data"""
        return self._db.hset(self.index, key, json.dumps(value))

    def setmany(self, **mapping):
        if mapping and isinstance(mapping, dict):
            mapping = {k: json.dumps(v) for k, v in iteritems(mapping)}
            return self._db.hmset(self.index, mapping)

    def get(self, key, default=None):
        """get key data from redis"""
        v = self._db.hget(self.index, key)
        if v:
            return json.loads(v)
        return default

    def remove(self, key):
        """delete key from redis"""
        return self._db.hdel(self.index, key)

    def __len__(self):
        return self._db.hlen(self.index)

    def __del__(self):
        if self._db:
            self._db.connection_pool.disconnect()
