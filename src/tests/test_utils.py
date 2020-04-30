# -*- coding: utf-8 -*-

import unittest
from utils.tool import Attribution, md5, sha1, rsp, get_current_timestamp, \
    allowed_file, parse_valid_comma, parse_valid_verticaline, is_true, \
    hmac_sha256, sha256, check_origin, get_origin


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
        self.assertEqual(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            sha256("abc")
        )

    def test_checkorigin(self):
        self.assertTrue(check_origin('http://127.0.0.1'))
        self.assertTrue(check_origin('http://localhost:5000'))
        self.assertTrue(check_origin('https://abc.com'))
        self.assertTrue(check_origin('https://abc.com:8443'))
        self.assertFalse(check_origin('ftp://192.168.1.2'))
        self.assertFalse(check_origin('rsync://192.168.1.2'))
        self.assertFalse(check_origin('192.168.1.2'))
        self.assertFalse(check_origin('example.com'))
        self.assertFalse(check_origin('localhost'))
        self.assertFalse(check_origin('127.0.0.1:8000'))
        self.assertFalse(check_origin('://127.0.0.1/hello-world'))
        self.assertEqual(get_origin("http://abc.com/hello"), "http://abc.com")
        self.assertEqual(get_origin("https://abc.com/"), "https://abc.com")


if __name__ == '__main__':
    unittest.main()
