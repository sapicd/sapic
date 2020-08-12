# -*- coding: utf-8 -*-

import unittest
from config import REDIS as redis_url
from libs.storage import RedisStorage


class StorageTest(unittest.TestCase):

    def test_redisstorage(self):
        """Run this test when it detects that the environment variable
        picbed_redis_url is valid
        """
        if redis_url:
            storage = RedisStorage()
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


if __name__ == '__main__':
    unittest.main()
