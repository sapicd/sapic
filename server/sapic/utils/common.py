# -*- coding: utf-8 -*-
"""Pure utility functions (no Flask request context).

Anything that needs ``request`` / ``g`` / ``jsonify`` belongs in
:mod:`sapic.utils.web` instead.
"""

from __future__ import annotations

import base64
import binascii
import re
from urllib.parse import urlsplit

from ..basis.errors import ApiError, ErrorCode

#: ``v2.1.0`` / ``2.1.0-rc1`` / ``2.1`` 的数字段与剩余后缀。
_VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)(.*)$")

#: 防盗链白名单条目上限，够用又不至于让一条设置长到没法看。
MAX_ALLOW_HOSTS = 32
#: 单个 host 标签：字母数字开头结尾，中间允许连字符。
_HOST_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def encode_cursor(*values) -> str:
    """Encode pagination cursor values into an opaque string."""
    raw = ":".join(str(v) for v in values)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[int, int]:
    """Decode a ``created_at:id`` cursor."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_at, row_id = raw.split(":", 1)
        return int(created_at), int(row_id)
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError) as exc:
        raise ApiError(
            "invalid cursor", ErrorCode.PARAM_ERROR, 400
        ) from exc


def slice_page(items, page: int = 1, page_size: int = 20) -> dict:
    """One page of an in-memory list.

    Used where the whole collection is already at hand (a cached remote listing,
    for example) and only the window has to be returned. The page number is
    clamped to the last page so a shrinking list never answers ``[]`` for the
    page the caller is on.
    """
    rows = list(items or [])
    total = len(rows)
    page_size = max(int(page_size or 1), 1)
    pages = max((total + page_size - 1) // page_size, 1)
    page = min(max(int(page or 1), 1), pages)
    start = (page - 1) * page_size
    return {
        "items": rows[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


def _version_parts(value: str):
    """``(numeric parts, is_final)`` or ``None`` for an unparsable version."""
    match = _VERSION_RE.match(str(value or "").strip())
    if match is None:
        return None
    numbers = tuple(int(part) for part in match.group(1).split("."))
    suffix = match.group(2).strip(" .-_")
    #: 同号时正式版比预发布新：2.0.0 > 2.0.0-rc1 / 2.0.0.dev0。
    return numbers, 0 if suffix else 1


def is_newer_version(latest: str, current: str) -> bool:
    """Whether ``latest`` is a newer release than ``current``.

    A small semver subset is enough here: numeric segments compare left to
    right (``2.1`` equals ``2.1.0``) and a plain release beats the same number
    with any suffix. Unparsable input never claims an update exists.
    """
    left = _version_parts(latest)
    right = _version_parts(current)
    if left is None or right is None:
        return False
    width = max(len(left[0]), len(right[0]))
    left_numbers = left[0] + (0,) * (width - len(left[0]))
    right_numbers = right[0] + (0,) * (width - len(right[0]))
    if left_numbers != right_numbers:
        return left_numbers > right_numbers
    return left[1] > right[1]


def normalize_host(value: str) -> str:
    """Lowercase a host, dropping scheme, userinfo, port and the trailing dot.

    Used on both sides of the hotlink check (``Referer`` and allow list) so the
    comparison never depends on how the caller spelled the URL.
    """
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "//" in text:
        text = urlsplit(text).netloc or ""
    text = text.rsplit("@", 1)[-1]
    if text.startswith("["):
        #: IPv6 字面量自带冒号，不能按端口截断。
        end = text.find("]")
        return text[: end + 1] if end > 0 else text
    return text.split(":", 1)[0].rstrip(".")


def is_valid_host(host: str) -> bool:
    """Whether ``host`` is a bare host (or IPv6 literal) we can compare with."""
    text = str(host or "")
    if not text:
        return False
    if text.startswith("["):
        return text.endswith("]")
    return all(_HOST_LABEL_RE.match(part) for part in text.split("."))


def _wildcard(entry: str) -> tuple[str, bool]:
    text = normalize_host(entry)
    if text.startswith("*."):
        return text[2:], True
    return text, False


def validate_allow_hosts(value) -> str:
    """Normalize a user supplied allow list, rejecting unusable entries.

    Accepts comma (or whitespace) separated hosts, ``*.example.com`` for
    subdomains and full URLs (their host is extracted). Stored form is always
    the canonical ``host,*.host`` string so reads never need to re-validate.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    entries = [item for item in re.split(r"[,\s]+", text) if item]
    if len(entries) > MAX_ALLOW_HOSTS:
        raise ApiError(
            "too many hosts (max %d)" % MAX_ALLOW_HOSTS, ErrorCode.PARAM_ERROR
        )
    hosts: list[str] = []
    for entry in entries:
        host, wildcard = _wildcard(entry)
        if not is_valid_host(host):
            raise ApiError("invalid host: %s" % entry, ErrorCode.PARAM_ERROR)
        host = "*." + host if wildcard else host
        if host not in hosts:
            hosts.append(host)
    return ",".join(hosts)


def parse_allow_hosts(value) -> tuple[str, ...]:
    """Lenient read of a stored allow list; unusable entries are skipped."""
    hosts: list[str] = []
    for entry in re.split(r"[,\s]+", str(value or "")):
        host, wildcard = _wildcard(entry)
        if not host or not is_valid_host(host):
            continue
        host = "*." + host if wildcard else host
        if host not in hosts:
            hosts.append(host)
    return tuple(hosts[:MAX_ALLOW_HOSTS])


def host_allowed(host: str, patterns) -> bool:
    """Whether ``host`` is covered by a normalized allow list.

    A ``*.example.com`` entry matches subdomains only; the apex has to be listed
    explicitly, which keeps ``*.evil.com`` from silently allowing ``evil.com``.
    """
    target = normalize_host(host)
    if not target:
        return False
    for pattern in patterns:
        if pattern == target:
            return True
        if pattern.startswith("*.") and target.endswith(pattern[1:]):
            return True
    return False


#: 对外请求代理：``urllib`` 只支持 http/https 代理，socks 会被忽略。
PROXY_SCHEMES = ("http", "https")


def parse_proxy_url(value) -> str:
    """Validate a single proxy url (``http(s)://[user:pass@]host:port``).

    Returns the trimmed value; raises ``ValueError`` when it is not an http(s)
    proxy with a usable host and port, so the settings form can reject it while
    the fetcher can log-and-ignore a value edited straight into the table.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme not in PROXY_SCHEMES or not parsed.hostname:
        raise ValueError("proxy must be an http(s) url")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("proxy has an invalid port") from exc
    return raw
