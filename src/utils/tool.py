# -*- coding: utf-8 -*-
"""
    utils.tool
    ~~~~~~~~~~

    Some tool classes and functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import hmac
import hashlib
from re import compile
from time import time
from datetime import datetime
from random import randrange
from redis import from_url
from .log import Logger
from ._compat import string_types, text_type, PY2

logger = Logger("sys").getLogger
err_logger = Logger("error").getLogger
comma_pat = compile(r"\s*,\s*")
verticaline_pat = compile(r"\s*\|\s*")
username_pat = compile(r'^[a-zA-Z][0-9a-zA-Z\_]{0,31}$')


def rsp(*args):
    return "picbed:" + ":".join(map(str, args))


def md5(text):
    if not PY2 and isinstance(text, text_type):
        text = text.encode("utf-8")
    return hashlib.md5(text).hexdigest()


def sha1(text):
    if not PY2 and isinstance(text, text_type):
        text = text.encode("utf-8")
    return hashlib.sha1(text).hexdigest()


def sha256(text):
    if PY2 and isinstance(text, text_type):
        text = text.encode("utf-8")
    if not PY2 and isinstance(text, text_type):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


def hmac_sha256(key, text):
    if PY2 and isinstance(key, text_type):
        key = key.encode("utf-8")
    if not PY2 and isinstance(key, text_type):
        key = key.encode("utf-8")
    if not PY2 and isinstance(text, text_type):
        text = text.encode("utf-8")
    return hmac.new(key=key, msg=text, digestmod=hashlib.sha256).hexdigest()


def get_current_timestamp(is_float=False):
    return time() if is_float else int(time())


def create_redis_engine(redis_url=None):
    from config import REDIS
    return from_url(redis_url or REDIS, charset="utf-8", decode_responses=True)


def gen_rnd_filename(fmt):
    if fmt == "time1":
        return int(round(time() * 1000))
    elif fmt == "time2":
        return "%s%s" % (
            int(round(time() * 1000)), str(randrange(1000, 10000))
        )
    elif fmt == "time3":
        return "%s%s" % (
            datetime.now().strftime('%Y%m%d%H%M%S'),
            str(randrange(1000, 10000))
        )


def get_today(fmt="%Y/%m/%d"):
    return datetime.now().strftime(fmt)


def allowed_file(filename, suffix=None):
    suffix = set(suffix or ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'])
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in suffix


def parse_valid_comma(s):
    if isinstance(s, string_types):
        return [i for i in comma_pat.split(s) if i]


def parse_valid_verticaline(s):
    if isinstance(s, string_types):
        return [i for i in verticaline_pat.split(s) if i]


def is_true(value):
    if value and value in (True, "True", "true", "on", 1, "1", "yes"):
        return True
    return False


def ListEqualSplit(l, n=5):
    return [l[i:i+n] for i in range(0, len(l), n)]


class Attribution(dict):
    """A dict that allows for object-like property access syntax."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


class Attribute(dict):
    """A dict that allows for object-like property access syntax."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return ''
