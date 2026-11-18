# -*- coding: utf-8 -*-

import ipaddress
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils import netguard

#: 打补丁前的真实实现，供假解析器与假拨号复用。
_real_getaddrinfo = socket.getaddrinfo
_real_create_connection = socket.create_connection


class _MarkerServer(object):
    """Local HTTP server: a tiny image, or a redirect when the path says so."""

    def __init__(self):
        self.paths = []
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def _handler(self):
        paths = self.paths

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(self.path)
                if self.path.startswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", "/secret.png")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = b"internal-marker"
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        return Handler

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _is_literal(host):
    try:
        ipaddress.ip_address(str(host).strip("[]"))
    except ValueError:
        return False
    return True


class NetGuardTestCase(unittest.TestCase):
    def setUp(self):
        self.server = _MarkerServer()
        self._real_getaddrinfo = socket.getaddrinfo
        self._real_create_connection = socket.create_connection

    def tearDown(self):
        socket.getaddrinfo = self._real_getaddrinfo
        socket.create_connection = self._real_create_connection
        self.server.close()

    def _fake_dns(self, address="93.184.216.34"):
        """名字一律答公网地址，字面量走真实解析（本机拨号要用）。"""

        def resolve(host, port=None, *args, **kwargs):
            if _is_literal(host):
                return self._real_getaddrinfo(host, port, *args, **kwargs)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 0))]

        socket.getaddrinfo = resolve

    def _dial_local(self):
        def create_connection(pair, timeout=None, source_address=None):
            return self._real_create_connection(
                ("127.0.0.1", self.server.port), timeout, source_address
            )

        socket.create_connection = create_connection

    def test_address_literal_is_refused(self):
        """用户 URL 只收域名：IPv4 / IPv6 字面量在解析前就拒绝。"""
        for url in (
            "http://127.0.0.1/a.png",
            "http://10.0.0.1/a.png",
            "http://93.184.216.34/a.png",
            "https://[2001:db8::1]/a.png",
        ):
            with self.assertRaises(netguard.UrlNotAllowed):
                netguard.safe_get(url)

    def test_private_answer_is_refused(self):
        """解析结果落在私网/环回范围就拒绝，一个字节都不发出去。"""

        def resolve(host, port=None, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.200.21.30", 80))]

        socket.getaddrinfo = resolve
        with self.assertRaises(netguard.UrlNotAllowed):
            netguard.safe_get("http://internal.example.com/a.png")

    def test_mixed_answer_is_refused(self):
        """公网私网混答同样拒绝。"""

        def resolve(host, port=None, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.200.21.30", 80)),
            ]

        socket.getaddrinfo = resolve
        with self.assertRaises(netguard.UrlNotAllowed):
            netguard.safe_get("http://mixed.example.com/a.png")

    def test_name_is_resolved_once_and_pinned(self):
        """名字只解析一次：第二次应答（内网）永远不会被采纳。"""
        calls = []

        def rebinding(host, port=None, *args, **kwargs):
            if _is_literal(host):
                return self._real_getaddrinfo(host, port, *args, **kwargs)
            calls.append(host)
            address = "93.184.216.34" if len(calls) == 1 else "10.200.21.30"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 0))]

        dialled = []

        def create_connection(pair, timeout=None, source_address=None):
            dialled.append(pair)
            return self._real_create_connection(
                ("127.0.0.1", self.server.port), timeout, source_address
            )

        socket.getaddrinfo = rebinding
        socket.create_connection = create_connection

        response = netguard.safe_get("http://rebind.example.com/secret.png")

        self.assertEqual(response.content, b"internal-marker")
        self.assertEqual(response.headers.get_content_type(), "image/png")
        self.assertEqual(calls, ["rebind.example.com"])
        self.assertEqual(dialled, [("93.184.216.34", 80)])

    def test_redirect_is_not_followed(self):
        """3xx 直接失败：不会对着 Location 再发一次请求。"""
        self._fake_dns()
        self._dial_local()

        with self.assertRaises(netguard.RemoteError) as ctx:
            netguard.safe_get("http://rebind.example.com/redirect.png")

        self.assertTrue(ctx.exception.fatal)
        self.assertIn("redirect", ctx.exception.reason)
        self.assertEqual(self.server.paths, ["/redirect.png"])


if __name__ == "__main__":
    unittest.main()
