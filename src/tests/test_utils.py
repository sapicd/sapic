# -*- coding: utf-8 -*-

import unittest
from utils.tool import Attribution, md5, sha1, rsp, get_current_timestamp, \
    allowed_file, parse_valid_comma, parse_valid_verticaline, is_true, \
    hmac_sha256, sha256, check_origin, get_origin, parse_data_uri, \
    format_upload_src, format_apires, generate_random, check_ip, gen_ua, \
    is_valid_verion, is_match_appversion, bleach_html, parse_author_mail
from version import __version__ as VER

class UtilsTest(unittest.TestCase):

    def test_attrclass(self):
        d = Attribution(dict(a=1, b=2, c=3))
        with self.assertRaises(AttributeError):
            d.d
        self.assertEqual(d.a, 1)
        self.assertIsInstance(d, dict)

    def test_semver(self):
        self.assertTrue(is_valid_verion("0.0.1"))
        self.assertTrue(is_valid_verion("1.1.1-beta"))
        self.assertTrue(is_valid_verion("1.1.1-beta+compile10"))
        self.assertFalse(is_valid_verion("1.0.1.0"))
        self.assertFalse(is_valid_verion("v2.19.10"))
        self.assertTrue(is_match_appversion())
        self.assertTrue(is_match_appversion(VER))
        self.assertFalse(is_match_appversion("<{}".format(VER)))
        self.assertFalse(is_match_appversion(">{}".format(VER)))
        self.assertTrue(is_match_appversion(">={}".format(VER)))
        self.assertTrue(is_match_appversion("<={}".format(VER)))
        self.assertTrue(is_match_appversion("=={}".format(VER)))
        self.assertFalse(is_match_appversion("!={}".format(VER)))

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
        #: test format_upload_src
        baseimg = 'img-url'
        basefmt = {'src': baseimg}
        self.assertEqual(format_upload_src(123, baseimg), basefmt)
        self.assertEqual(format_upload_src(None, baseimg), basefmt)
        self.assertEqual(format_upload_src([0], baseimg), basefmt)
        self.assertEqual(format_upload_src('', baseimg), basefmt)
        self.assertEqual(format_upload_src('.', baseimg), basefmt)
        self.assertEqual(format_upload_src('.1', baseimg), basefmt)
        self.assertEqual(format_upload_src('1.', baseimg), basefmt)
        self.assertEqual(format_upload_src(1.1, baseimg), basefmt)
        self.assertEqual(
            format_upload_src('1.1', baseimg), {'1': {'1': baseimg}}
        )
        self.assertEqual(format_upload_src('u', baseimg), basefmt)
        self.assertEqual(format_upload_src('im', baseimg), {'im': baseimg})
        self.assertEqual(format_upload_src('url', baseimg), {'url': baseimg})
        self.assertEqual(format_upload_src('i.am.src', baseimg), basefmt)
        self.assertEqual(
            format_upload_src('src.url', baseimg), {'src': {'url': baseimg}}
        )
        #: test format_apires
        self.assertEqual(
            format_apires({'code': 0}, "success", "bool"), {'success': True}
        )
        self.assertEqual(
            format_apires({'code': 0}, oc="200"), {'code': 200}
        )
        self.assertEqual(
            format_apires({'code': -1}, "status", "bool"), {'status': False}
        )
        self.assertEqual(
            format_apires(dict(code=-1, msg='xxx'), 'errno', '200'),
            {'errno': -1, 'msg': 'xxx'}
        )
        self.assertEqual(
            format_apires(dict(code=-1, msg='xxx'), 'errno', '200', 'errmsg'),
            {'errno': -1, 'errmsg': 'xxx'}
        )
        self.assertEqual(
            format_apires(dict(code=0, msg='xxx'), '', '200', 'errmsg'),
            {'code': 200, 'errmsg': 'xxx'}
        )
        self.assertEqual(len(generate_random()), 6)
        self.assertIn("Mozilla/5.0", gen_ua())
        # bleach
        self.assertEqual(bleach_html("<i>abc</i>"), '<i>abc</i>')
        self.assertEqual(bleach_html('<script>var abc</script>'), '&lt;script&gt;var abc&lt;/script&gt;')
        # re
        self.assertEqual(parse_author_mail("staugur"), ('staugur', None))
        self.assertEqual(
            parse_author_mail("staugur <mail>"), ('staugur', 'mail')
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
        self.assertTrue(check_ip("127.0.0.1"))
        self.assertTrue(check_ip("1.2.3.4"))
        self.assertTrue(check_ip("255.255.255.0"))
        self.assertFalse(check_ip("1.2.3"))
        self.assertFalse(check_ip("a.1.2.3"))
        self.assertFalse(check_ip("999.1.2.3"))

    def test_datauri(self):
        uri1 = 'data:,Hello%2C%20World!'
        uri2 = 'data:text/plain;base64,SGVsbG8sIFdvcmxkIQ%3D%3D'
        uri3 = 'data:text/html,%3Ch1%3EHello%2C%20World!%3C%2Fh1%3E'
        uri4 = 'data:image/png;base64,isimagebase64=='
        uri5 = 'data:text/plain;charset=utf-8;base64,VGhlIHF1'
        rst1 = parse_data_uri(uri1)
        self.assertIsNone(rst1.mimetype)
        self.assertIsNone(rst1.charset)
        self.assertFalse(rst1.is_base64)

        rst2 = parse_data_uri(uri2)
        self.assertEqual(rst2.mimetype, "text/plain")
        self.assertIsNone(rst2.charset)
        self.assertTrue(rst2.is_base64)

        rst3 = parse_data_uri(uri3)
        self.assertEqual(rst3.mimetype, "text/html")
        self.assertIsNone(rst3.charset)
        self.assertFalse(rst3.is_base64)

        rst4 = parse_data_uri(uri4)
        self.assertEqual(rst4.mimetype, "image/png")
        self.assertIsNone(rst4.charset)
        self.assertTrue(rst4.is_base64)

        rst5 = parse_data_uri(uri5)
        self.assertEqual(rst5.mimetype, "text/plain")
        self.assertEqual(rst5.charset, "utf-8")
        self.assertTrue(rst5.is_base64)


if __name__ == '__main__':
    unittest.main()
