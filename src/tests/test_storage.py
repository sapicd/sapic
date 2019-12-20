# -*- coding: utf-8 -*-

import unittest
from os import getenv
from libs.storage import LocalStorage, RedisStorage, BaseStorage, get_storage


class StorageTest(unittest.TestCase):

    def test_localstorage(self):
        storage = LocalStorage()
        self.assertIsInstance(storage, BaseStorage)
        data = dict(a=1, b=2)
        storage.set('test', data)
        newData = storage.get('test')
        self.assertIsInstance(newData, dict)
        self.assertEqual(newData, data)
        self.assertEqual(len(storage), len(storage.list))
        # test setmanry and value type
        storage.setmany(c=None, d=[], e={})
        self.assertIsNone(storage['c'])
        self.assertEqual(storage['d'], [])
        self.assertEqual(storage['e'], {})
        # test setitem getitem
        storage["test"] = "hello"
        self.assertEqual("hello", storage["test"])
        del storage["test"]
        self.assertIsNone(storage.get("test"))
        self.assertIsNone(storage['_non_existent_key_'])
        self.assertEqual(1, storage.get('_non_existent_key_', 1))

    def test_redisstorage(self):
        """Run this test when it detects that the environment variable
        picbed_redis_url is valid
        """
        redis_url = getenv("picbed_redis_url")
        if redis_url:
            storage = RedisStorage(redis_url=redis_url)
            self.assertIsInstance(storage, BaseStorage)
            storage['test'] = 1
            self.assertEqual(storage['test'], 1)
            self.assertEqual(len(storage), len(storage.list))
            self.assertEqual(len(storage), storage._db.hlen(storage.index))
            self.assertIsNone(storage['_non_existent_key_'])
            self.assertEqual(1, storage.get('_non_existent_key_', 1))
            # test setmanry and value type
            storage.setmany(c=None, d=[], e={})
            self.assertIsNone(storage['c'])
            self.assertEqual(storage['d'], [])
            self.assertEqual(storage['e'], {})
            # RedisStorage allow remove
            del storage['test']
            self.assertIsNone(storage['test'])
            # test other index
            storage2 = RedisStorage(index='_non_exist_i_', redis_url=redis_url)
            self.assertEqual(0, len(storage2))

    def test_basestorage(self):
        class MyStorage(BaseStorage):
            pass
        ms = MyStorage()
        with self.assertRaises(AttributeError):
            ms.get('test')
        self.assertIsInstance(get_storage(), BaseStorage)


if __name__ == '__main__':
    unittest.main()
