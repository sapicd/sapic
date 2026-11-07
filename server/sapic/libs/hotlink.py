# -*- coding: utf-8 -*-
"""sapic.libs.hotlink

Referer based hotlink protection for public images.

Every user decides for their own images, through ``user_settings``: whether
external sites may embed them (``hotlink_enabled``), which hosts are still
allowed (``hotlink_allow_hosts``) and whether a request without ``Referer``
passes (``hotlink_allow_empty``). The check runs in ``views.public`` only, and
only for public images: private ones are already authorised, and images served
from a storage url never reach sapic (the CDN/nginx needs its own referer rule).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import current_app, request

from ..models import Image
from ..utils.common import (
    host_allowed,
    is_valid_host,
    normalize_host,
    parse_allow_hosts,
)
from .user_settings import get_user_settings

#: ``/raw/<sha>`` verdicts. ``PASS`` still means the decision depends on the
#: request, so the response must not be stored by a shared cache.
HOTLINK_OFF = "off"
HOTLINK_PASS = "pass"
HOTLINK_BLOCK = "block"


def site_hosts() -> tuple[str, ...]:
    """Hosts that never count as hotlinking: the site itself and the image host."""
    hosts: list[str] = []
    for value in (
        current_app.config.get("EXTERNAL_BASE_URL") or "",
        request.host or "",
    ):
        host = normalize_host(value)
        if host and host not in hosts:
            hosts.append(host)
    return tuple(hosts)


def referer_host() -> str:
    """Normalized host of the ``Referer`` header, empty when absent or unusable."""
    raw = (request.headers.get("Referer") or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    #: 只认 http(s)：``about:client`` 之类的 scheme 不是「有来源」。
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return ""
    host = normalize_host(parsed.netloc or raw)
    return host if is_valid_host(host) else ""


def hotlink_verdict(image: Image, public: bool) -> str:
    """Classify the running ``/raw/<sha>`` request against the owner's rules."""
    if not public:
        return HOTLINK_OFF
    owner = image.owner
    if owner is None:
        #: 匿名上传（系统相册）没有可表态的主体，不做拦截。
        return HOTLINK_OFF
    prefs = get_user_settings(owner)
    if not prefs.get("hotlink_enabled"):
        return HOTLINK_OFF

    host = referer_host()
    if not host:
        if prefs.get("hotlink_allow_empty", True):
            return HOTLINK_PASS
        return HOTLINK_BLOCK
    allowed = site_hosts() + parse_allow_hosts(prefs.get("hotlink_allow_hosts"))
    return HOTLINK_PASS if host_allowed(host, allowed) else HOTLINK_BLOCK
