# -*- coding: utf-8 -*-

import unittest
from utils._compat import PY2
from utils.tool import Attribution, md5, sha1, rsp, get_current_timestamp, \
    allowed_file, parse_valid_comma, parse_valid_verticaline, is_true, 
    hmac_sha256


class UtilsTest(unittest.TestCase):

    def test_attrclass(self):
        d = Attribution(dict(a=1, b=2, c=3))
        with self.assertRaises(AttributeError):
            d.d
        self.assertEqual(d.a, 1)
        self.assertIsInstance(d, dict)

    def test_utils(self):
        self.assertEqual("900150983cd24fb0d6963f7d28e17f72", md5("abc"))
        self.assertEqual(
            "a9993e364706816aba3e25717850c26c9cd0d89d", sha1("abc")
        )
        self.assertEqual("picbed:a:b", rsp("a", "b"))
        self.assertEqual(parse_valid_comma("a,b, c,"), ["a", "b", "c"])
        self.assertEqual(parse_valid_verticaline("a|b| c"), ["a", "b", "c"])
        self.assertTrue(is_true(1))
        self.assertTrue(is_true("on"))
        self.assertTrue(is_true("true"))
        self.assertFalse(is_true(0))
        self.assertIsInstance(get_current_timestamp(), int)
        self.assertTrue(allowed_file("test.PNG"))
        self.assertTrue(allowed_file(".jpeg"))
        self.assertFalse(allowed_file("my.psd"))
        self.assertFalse(allowed_file("ha.gif", ["jpg"]))
        self.assertFalse(allowed_file("ha.jpeg", ["jpg"]))
        self.assertFalse(allowed_file("ha.png", ["jpg"]))
        self.assertTrue(allowed_file("ha.jpg", ["jpg"]))
        v = "6afa9046a9579cad143a384c1b564b9a250d27d6f6a63f9f20bf3a7594c9e2c6"
        self.assertEqual(v, hmac_sha256('key', 'text'))
        self.assertEqual(v, hmac_sha256(b'key', b'text'))
        self.assertEqual(v, hmac_sha256(u'key', u'text'))


if __name__ == '__main__':
    unittest.main()
