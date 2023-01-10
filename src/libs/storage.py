# -*- coding: utf-8 -*-
"""
    libs.storage
    ~~~~~~~~~~~~

    Not core data storage.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import json
from utils._compat import iteritems
from utils.tool import rsp, create_redis_engine
from redis import Redis

try:
    from synchronize import make_synchronized
except ImportError:

    def make_synchronized(func):
        import threading

        func.__lock__ = threading.Lock()

        def synced_func(*args, **kws):
            with func.__lock__:
                return func(*args, **kws)

        return synced_func


class RedisStorage(object):
    """Use redis stand-alone or cluster storage"""

    instance = None

    @make_synchronized
    def __new__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = object.__new__(cls, *args, **kwargs)
        return cls.instance

    def __init__(self):
        self.index = rsp("dat")
        self._db: Redis = create_redis_engine()

    @property
    def list(self) -> dict:
        """list redis hash data"""
        return {
            k: json.loads(v)
            for k, v in iteritems(self._db.hgetall(self.index))
        }

    def set(self, key, value):
        """set key data"""
        if isinstance(value, str):
            value = value.strip()
        return self._db.hset(self.index, key, json.dumps(value))

    def setmany(self, **mapping):
        if mapping and isinstance(mapping, dict):
            pipe = self._db.pipeline()
            for k, v in iteritems(mapping):
                if isinstance(v, str):
                    v = v.strip()
                pipe.hset(self.index, k, json.dumps(v))
            return pipe.execute()

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

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        return self.set(key, value)

    def __delitem__(self, key):
        return self.remove(key)

    def __str__(self):
        return "<%s object at %s, index is %s>" % (
            self.__class__.__name__,
            hex(id(self)),
            self.index,
        )

    __repr__ = __str__


def get_storage() -> RedisStorage:
    """Project global definition data store backend"""
    return RedisStorage()
