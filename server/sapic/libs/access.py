# -*- coding: utf-8 -*-
"""sapic.libs.access

IP based access control for image delivery (``/raw/<sha>``).

The rule is site-wide and only has two shapes: an allow list (everything else is
refused) or a deny list. Both accept bare addresses and CIDR blocks, IPv4 and
IPv6. An empty list disables the rule instead of locking the site out — a typo in
the admin form must not black-hole every image.

``request.remote_addr`` is what gets classified, so behind a reverse proxy the
deployment needs ``sapic_proxyfix=1`` (``X-Forwarded-For``) for this to see the
real client instead of the proxy address.
"""

from __future__ import annotations

import ipaddress
import re

from flask import request

from ..basis.errors import ApiError, ErrorCode
from .settings import get_setting

#: ``off`` (no rule) / ``allow`` (only the listed addresses) / ``deny`` (all but).
MODES = ("off", "allow", "deny")
#: Hard cap on the list size: it is evaluated on every image request.
MAX_ENTRIES = 500

_SPLIT_RE = re.compile(r"[,\s]+")


def clean_mode(value) -> str:
    """Validate the admin supplied mode; unknown values are a client error."""
    text = str(value or "").strip().lower() or "off"
    if text not in MODES:
        raise ApiError("invalid ip mode: %s" % text, ErrorCode.PARAM_ERROR)
    return text


def validate_ip_list(value) -> str:
    """Normalize ``value`` into a comma separated list of networks.

    Raises ``ApiError`` for anything unparsable so a broken rule is rejected on
    save rather than silently dropping entries at request time.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    entries = [item for item in _SPLIT_RE.split(text) if item]
    if len(entries) > MAX_ENTRIES:
        raise ApiError(
            "too many ip entries (max %d)" % MAX_ENTRIES, ErrorCode.PARAM_ERROR
        )
    networks: list[str] = []
    for entry in entries:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError as exc:
            raise ApiError("invalid ip: %s" % entry, ErrorCode.PARAM_ERROR) from exc
        canonical = str(network)
        if canonical not in networks:
            networks.append(canonical)
    return ",".join(networks)


def parse_ip_list(value) -> tuple:
    """Lenient read of the stored list; unusable entries are skipped."""
    networks = []
    for entry in _SPLIT_RE.split(str(value or "")):
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
        if len(networks) >= MAX_ENTRIES:
            break
    return tuple(networks)


def _address(value):
    """``ip_address`` of a request address; ``None`` when it is not an address."""
    text = str(value or "").strip()
    if not text:
        return None
    #: 部分反代会在 IPv6 后带 ``%eth0`` 作用域，ipaddress 不接受。
    text = text.split("%", 1)[0]
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def ip_allowed(client_ip: str | None = None) -> bool:
    """Whether the current request may fetch ``/raw`` under the site rule.

    A missing/unparsable client address passes: refusing it would turn a proxy
    misconfiguration into a site outage, and the rule is a traffic guard, not an
    authentication mechanism.
    """
    mode = str(get_setting("raw_ip_mode") or "off").strip().lower()
    if mode not in ("allow", "deny"):
        return True
    networks = parse_ip_list(get_setting("raw_ip_list"))
    if not networks:
        return True

    address = _address(request.remote_addr if client_ip is None else client_ip)
    if address is None:
        return True
    inside = any(
        address.version == network.version and address in network
        for network in networks
    )
    return inside if mode == "allow" else not inside
