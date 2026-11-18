# -*- coding: utf-8 -*-
"""
    utils.netguard
    ~~~~~~~~~~~~~~

    Address checking and pinned fetching for user supplied URLs.

    The upload-by-URL feature lets a visitor make the server fetch an address
    they chose. Every rule that keeps that from reaching the intranet lives
    here, so the check and the connection cannot drift apart:

    - only domain names are accepted, address literals are refused outright;
    - the name is resolved exactly once, every answer is checked against the
      private/loopback/link-local/reserved ranges, and the connection is then
      dialed to those very addresses (the name stays in ``Host`` and in the TLS
      SNI, so virtual hosting and certificate checks keep working);
    - redirects are never followed: a 3xx is an error, not a second request.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import ipaddress
import socket
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from urllib.parse import urlparse

#: 抓取超时与字节上限：URL 上传的响应体不会无限读下去。
REMOTE_TIMEOUT = 30
REMOTE_MAX_BYTES = 32 * 1024 * 1024
REMOTE_CHUNK_SIZE = 64 * 1024
REMOTE_USER_AGENT = "sapic/url-fetch"

REDIRECT_CODES = (301, 302, 303, 307, 308)


class UrlNotAllowed(ValueError):
    """The URL itself is refused by policy, no transport may fetch it."""


class RemoteError(RuntimeError):
    """The remote side was unusable: transport error, 3xx, 4xx/5xx, oversize.

    ``fatal`` marks an answer no other transport may improve on (a redirect, an
    oversize body): the proxy fallback must not retry those.
    """

    def __init__(self, reason, fatal=False):
        RuntimeError.__init__(self, reason)
        self.reason = reason
        self.fatal = fatal


class RemoteResponse(object):
    """The slice of ``requests.Response`` this code base actually uses."""

    def __init__(self, url, status_code, headers, content):
        self.url = url
        self.status_code = status_code
        self.headers = headers
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RemoteError("http {}".format(self.status_code))


def is_ip_literal(hostname):
    """Whether the URL names a host by address instead of by name.

    A literal skips DNS entirely, so there is nothing to check and nothing to
    pin, and it turns the feature into a port scanner for any address the
    server can route to.
    """
    try:
        ipaddress.ip_address(str(hostname).strip("[]"))
    except ValueError:
        return False
    return True


def is_private_address(address):
    """Whether an address belongs to a range a user URL must never reach."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def checked_addresses(hostname):
    """Resolve ``hostname`` once and return the addresses a dial may use.

    Checking the name and then letting the transport resolve it again is a
    time-of-check/time-of-use gap: a domain that answers a public address first
    and an internal one second (DNS rebinding) passes the check and still
    reaches the internal host. Nothing below this function resolves again.
    """
    try:
        infos = socket.getaddrinfo(hostname, None, 0, socket.SOCK_STREAM)
    except OSError as exc:
        raise RemoteError("cannot resolve {}".format(hostname)) from exc
    addresses = []
    for info in infos:
        raw = info[4][0]
        if raw not in addresses:
            addresses.append(raw)
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            raise UrlNotAllowed("url host is not allowed")
        if is_private_address(address):
            raise UrlNotAllowed("url host is not allowed")
    if not addresses:
        raise RemoteError("cannot resolve {}".format(hostname))
    return addresses


def _pinned_dial(addresses):
    """``http.client`` connect hook that only dials pre-checked addresses."""

    def dial(pair, timeout=None, source_address=None):
        error = None
        for address in addresses:
            try:
                return socket.create_connection(
                    (address, pair[1]), timeout, source_address
                )
            except OSError as exc:
                error = exc
        raise error or OSError("no address to connect")

    return dial


class _PinnedHTTPConnection(HTTPConnection):
    """Plain HTTP connection dialing a checked address instead of the name."""

    def __init__(self, host, addresses, **kwargs):
        HTTPConnection.__init__(self, host, **kwargs)
        self._create_connection = _pinned_dial(addresses)


class _PinnedHTTPSConnection(HTTPSConnection):
    """Same pinning over TLS: SNI and certificate checks still use the name."""

    def __init__(self, host, addresses, **kwargs):
        HTTPSConnection.__init__(self, host, **kwargs)
        self._create_connection = _pinned_dial(addresses)


def _request_path(parsed):
    path = parsed.path or "/"
    if parsed.query:
        path = "{}?{}".format(path, parsed.query)
    return path


def _open(url, headers, timeout, addresses, max_bytes):
    """One request over one pinned connection; the body is read and capped."""
    parsed = urlparse(url)
    connection_class = (
        _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
    )
    connection = connection_class(
        parsed.hostname, addresses, port=parsed.port, timeout=timeout
    )
    try:
        connection.request("GET", _request_path(parsed), headers=headers)
        response = connection.getresponse()
        status = response.status
        if status in REDIRECT_CODES:
            raise RemoteError("url redirects are not followed", fatal=True)
        chunks, total = [], 0
        while True:
            chunk = response.read(REMOTE_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RemoteError("file exceeds the size limit", fatal=True)
            chunks.append(chunk)
    except (HTTPException, OSError, ValueError) as exc:
        raise RemoteError("network error: {}".format(exc)) from exc
    finally:
        connection.close()
    return RemoteResponse(url, status, response.headers, b"".join(chunks))


def safe_get(url, headers=None, timeout=REMOTE_TIMEOUT, max_bytes=REMOTE_MAX_BYTES):
    """Fetch a user supplied URL: domain only, no redirects, pinned address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UrlNotAllowed("only http(s) url is supported")
    if is_ip_literal(parsed.hostname):
        raise UrlNotAllowed("url host must be a domain name")
    addresses = checked_addresses(parsed.hostname)
    request_headers = {
        "User-Agent": REMOTE_USER_AGENT,
        "Accept": "image/*,video/*",
        "Connection": "close",
    }
    request_headers.update(headers or {})
    return _open(url, request_headers, timeout, addresses, max_bytes)
