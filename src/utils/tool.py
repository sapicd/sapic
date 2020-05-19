# -*- coding: utf-8 -*-
"""
    utils.tool
    ~~~~~~~~~~

    Some tool classes and functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import re
import hmac
import hashlib
from uuid import uuid4
from time import time
from datetime import datetime
from random import randrange, sample, randint, choice
from redis import from_url
from .log import Logger
from ._compat import string_types, text_type, PY2, urlparse

logger = Logger("sys").getLogger
err_logger = Logger("error").getLogger
comma_pat = re.compile(r"\s*,\s*")
verticaline_pat = re.compile(r"\s*\|\s*")
username_pat = re.compile(r'^[a-zA-Z][0-9a-zA-Z\_]{0,31}$')
point_pat = re.compile(r'^\w{1,9}\.?\w{1,9}$')
url_pat = re.compile(
    r'^(?:http)s?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+'
    r'(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)
data_uri_pat = re.compile(r'^{}$'.format((
    r'data:' +
    r'(?P<mimetype>[\w]+\/[\w\-\+\.]+)?' +
    r'(?:\;charset\=(?P<charset>[\w\-\+\.]+))?' +
    r'(?P<base64>\;base64)?' +
    r',(?P<data>.*)')),
    re.DOTALL
)
er_pat = re.compile(r'^(and|or|not|\s|ip|ep|origin|method|\(|\))+$')
ir_pat = re.compile(r'^(in|not in|\s|ip|ep|origin|method|,|:)+$')
ALLOWED_RULES = ("ip", "ep", "method", "origin")
ALLOWED_EXTS = ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp')


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
    if isinstance(text, text_type):
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
    return from_url(redis_url or REDIS, decode_responses=True)


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
    suffix = set(suffix or ALLOWED_EXTS)
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in suffix


def parse_valid_comma(s):
    if isinstance(s, string_types):
        return [i for i in comma_pat.split(s) if i]


def parse_valid_verticaline(s):
    if isinstance(s, string_types):
        return [i for i in verticaline_pat.split(s) if i]


def parse_valid_colon(s):
    if s:
        return dict([i.split(":") for i in comma_pat.split(s) if i])


def is_true(value):
    if value and value in (True, "True", "true", "on", 1, "1", "yes"):
        return True
    return False


def ListEqualSplit(l, n=5):
    return [l[i:i+n] for i in range(0, len(l), n)]


def generate_random(length=6):
    code_list = []
    for i in range(10):  # 0-9数字
        code_list.append(str(i))
    for i in range(65, 91):  # A-Z
        code_list.append(chr(i))
    for i in range(97, 123):  # a-z
        code_list.append(chr(i))

    myslice = sample(code_list, length)
    return ''.join(myslice)


def format_upload_src(fmt, value):
    """转换upload路由中返回的src格式"""
    if fmt and isinstance(fmt, string_types):
        if point_pat.match(fmt):
            if "." in fmt:
                fmts = fmt.split('.')
                return {fmts[0]: {fmts[1]: value}}
            else:
                return {fmt: value}
    return dict(src=value)


def format_apires(res, sn="code", oc=None, mn=None):
    """转换API响应JSON的格式

    可以用下面三个参数修改返回的res基本格式：
    - sn: status_name规定数据状态的字段名称，默认code
    - oc: ok_code规定成功的状态码，默认0，用字符串bool则会返回布尔类型
    - mn: msg_name规定状态信息的字段名称，默认msg
    """
    if isinstance(res, dict) and "code" in res:
        if not sn:
            sn = "code"
        code = res.pop("code")
        if oc:
            if oc == "bool":
                #: ok_code要求bool时，成功返回True，否则False
                code = True if code == 0 else False
            else:
                #: 不是bool就是int，成功返回oc，否则是code本身
                try:
                    code = int(oc) if code == 0 else code
                except (ValueError, TypeError):
                    pass
        res[sn] = code
        if mn and res.get("msg"):
            msg = res.pop("msg")
            res[mn] = msg
    return res


class Attribution(dict):

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


class Attribute(dict):

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return ''


def get_origin(url):
    """从url提取出符合CORS格式的origin地址"""
    parsed_uri = urlparse(url)
    return '{uri.scheme}://{uri.netloc}'.format(uri=parsed_uri)


def check_origin(addr):
    """Check whether UrlAddr is in a valid host origin, for example::

        http://ip:port
        https://abc.com
    """
    if addr and isinstance(addr, string_types):
        try:
            origin = get_origin(addr)
        except (ValueError, TypeError, Exception):
            return False
        else:
            return url_pat.match(origin)
    return False


def check_ip(ip_str):
    sep = ip_str.split('.')
    if len(sep) != 4:
        return False
    for x in sep:
        try:
            int_x = int(x)
            if int_x < 0 or int_x > 255:
                return False
        except ValueError:
            return False
    return True


def gen_uuid():
    return uuid4().hex


def check_ir(ir):
    """解析ir规则，其格式是: in:opt1, not in:opt2"""
    if ir:
        for i in parse_valid_comma(ir):
            opr, opt = i.split(":")
            if opt not in ALLOWED_RULES or opr not in ("in", "not in"):
                raise ValueError


def parse_data_uri(datauri):
    """Parse Data URLs: data:[<media type>][;base64],<data>"""
    if not PY2 and not isinstance(datauri, text_type):
        datauri = datauri.decode("utf-8")
    match = data_uri_pat.match(datauri)
    if match:
        mimetype = match.group('mimetype') or None
        charset = match.group('charset') or None
        is_base64 = bool(match.group('base64'))
        data = match.group('data')
    else:
        mimetype = charset = data = None
        is_base64 = False

    return Attribution(dict(
        mimetype=mimetype,
        charset=charset,
        is_base64=is_base64,
        data=data,
    ))


def gen_ua():
    first_num = randint(55, 62)
    third_num = randint(0, 3200)
    fourth_num = randint(0, 140)
    os_type = [
        '(Windows NT 6.1; WOW64)',
        '(Windows NT 10.0; WOW64)',
        '(X11; Linux x86_64)',
        '(Macintosh; Intel Mac OS X 10_12_6)'
    ]
    chrome_version = 'Chrome/{}.0.{}.{}'.format(
        first_num, third_num, fourth_num
    )
    ua = ' '.join(
        [
            'Mozilla/5.0',
            choice(os_type),
            'AppleWebKit/537.36',
            '(KHTML, like Gecko)',
            chrome_version,
            'Safari/537.36'
        ]
    )
    return ua
