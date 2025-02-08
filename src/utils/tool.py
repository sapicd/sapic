# -*- coding: utf-8 -*-
"""
    utils.tool
    ~~~~~~~~~~

    Some tool classes and functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import re
import os
import sys
import hmac
import hashlib
import requests
import smtplib
import semver
from uuid import uuid4
import unicodedata
from time import time, localtime, strftime
from datetime import datetime
from random import randrange, sample, randint, choice
from redis import from_url, Redis
from email.header import Header
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
from user_agents import parse as user_agents_parse
from bleach import clean as bleach_clean
from bleach.sanitizer import ALLOWED_TAGS, ALLOWED_ATTRIBUTES
from bleach.css_sanitizer import CSSSanitizer
from typing import Optional, Dict, List
from version import __version__ as PICBED_VERSION
from .log import Logger
from ._compat import string_types, text_type, urlparse, is_true


logger = Logger("sys").getLogger
err_logger = Logger("error").getLogger
comma_pat = re.compile(r"\s*,\s*")
colon_pat = re.compile(r"\s*:\s*")
verticaline_pat = re.compile(r"\s*\|\s*")
username_pat = re.compile(r"^[a-zA-Z][0-9a-zA-Z\_]{3,31}$")
point_pat = re.compile(r"^\w{1,9}\.?\w{1,9}$")
mail_pat = re.compile(
    r"([0-9a-zA-Z\_*\.*\-*]+)@([a-zA-Z0-9\-*\_*\.*]+)\.([a-zA-Z]+$)"
)
author_mail_re = re.compile(r"(.*)\s<(.*)>")
url_pat = re.compile(
    r"^(?:http)s?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"
    r"(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"
    r"localhost|"
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)
data_uri_pat = re.compile(
    r"^{}$".format(
        (
            r"data:"
            + r"(?P<mimetype>[\w]+\/[\w\-\+\.]+)?"
            + r"(?:\;charset\=(?P<charset>[\w\-\+\.]+))?"
            + r"(?P<base64>\;base64)?"
            + r",(?P<data>.*)"
        )
    ),
    re.DOTALL,
)
er_pat = re.compile(r"^(and|or|not|\s|ip|ep|origin|method|\(|\))+$")
ir_pat = re.compile(r"^(in|not in|\s|ip|ep|origin|method|,|:)+$")
ALLOWED_RULES = ("ip", "ep", "method", "origin")
ALLOWED_EXTS = ("png", "jpg", "jpeg", "gif", "bmp", "webp")
ALLOWED_HTTP_METHOD = ("GET", "POST", "PUT", "DELETE", "HEAD")
ALLOWED_VIDEO = ("mp4", "ogg", "ogv", "webm", "3gp", "mov")
# \u4E00-\u9FBF 为中文UTF-8编码
_filename_ascii_strip_re = re.compile(r"[^A-Za-z0-9_\u4E00-\u9FBF.-]")
_windows_device_files = (
    "CON",
    "AUX",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "LPT1",
    "LPT2",
    "LPT3",
    "PRN",
    "NUL",
)


def secure_filename(filename: str) -> str:
    r"""Pass it a filename and it will return a secure version of it.  This
    filename can then safely be stored on a regular file system and passed
    to :func:`os.path.join`.  The filename returned is an ASCII only string
    for maximum portability.

    On windows systems the function also makes sure that the file is not
    named after one of the special device files.

    >>> secure_filename("My cool movie.mov")
    'My_cool_movie.mov'
    >>> secure_filename("../../../etc/passwd")
    'etc_passwd'
    >>> secure_filename('i contain cool \xfcml\xe4uts.txt')
    'i_contain_cool_umlauts.txt'

    The function might return an empty filename.  It's your responsibility
    to ensure that the filename is unique and that you abort or
    generate a random filename if the function returned an empty one.

    .. versionadded:: 0.5

    :param filename: the filename to secure
    """
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("utf-8", "ignore").decode("utf-8")

    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")
    filename = str(
        _filename_ascii_strip_re.sub("", "_".join(filename.split()))
    ).strip("._")

    # on nt a couple of special files are present in each folder.  We
    # have to ensure that the target file is not such a filename.  In
    # this case we prepend an underline
    if (
        os.name == "nt"
        and filename
        and filename.split(".")[0].upper() in _windows_device_files
    ):
        filename = f"_{filename}"

    return filename


def rsp(*args):
    """使用 `picbed:` 前缀生成redis key"""
    return "picbed:" + ":".join(map(str, args))


def md5(text):
    if isinstance(text, text_type):
        text = text.encode("utf-8")
    return hashlib.md5(text).hexdigest()


def sha1(text):
    if isinstance(text, text_type):
        text = text.encode("utf-8")
    return hashlib.sha1(text).hexdigest()


def sha256(text):
    if isinstance(text, text_type):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


def hmac_sha256(key, text):
    if isinstance(key, text_type):
        key = key.encode("utf-8")
    if isinstance(text, text_type):
        text = text.encode("utf-8")
    return hmac.new(key=key, msg=text, digestmod=hashlib.sha256).hexdigest()


def get_current_timestamp(is_float=False):
    """获取当前时间戳

    :param bool is_float: True则获取10位秒级时间戳，否则原样返回
    """
    return time() if is_float else int(time())


def timestamp_to_timestring(timestamp, fmt="%Y-%m-%d %H:%M:%S"):
    """将时间戳(10位)转换为可读性的时间"""
    if not isinstance(timestamp, (int, float)):
        try:
            timestamp = int(timestamp)
        except (ValueError, TypeError):
            raise
    timestamp = localtime(timestamp)
    return strftime(fmt, timestamp)


def create_redis_engine(redis_url=None) -> Redis:
    """创建redis连接的入口"""
    from config import REDIS

    url = redis_url or REDIS
    if not url:
        return
    return from_url(url, decode_responses=True)


def gen_rnd_filename(fmt):
    if fmt == "time1":
        return int(round(time() * 1000))
    elif fmt == "time2":
        return "%s%s" % (
            int(round(time() * 1000)),
            str(randrange(1000, 10000)),
        )
    elif fmt == "time3":
        return "%s%s" % (
            datetime.now().strftime("%Y%m%d%H%M%S"),
            str(randrange(1000, 10000)),
        )


def get_today(fmt="%Y/%m/%d"):
    return datetime.now().strftime(fmt)


def allowed_file(filename, suffix=None):
    if not filename:
        return False
    suffix = set(suffix or ALLOWED_EXTS)
    return "." in filename and filename.rsplit(".", 1)[1].lower() in suffix


def parse_valid_comma(s):
    if isinstance(s, string_types):
        return [i for i in comma_pat.split(s) if i]


def parse_valid_verticaline(s):
    if isinstance(s, string_types):
        return [i for i in verticaline_pat.split(s) if i]


def parse_valid_colon(s):
    """解析形如 a:b,x:y 字符串为 dict(a=b, x=y)"""
    if s:
        return dict(
            [
                i.split(":")
                for i in comma_pat.split(s)
                if i
                and ":" in i
                and len(i.split(":")) == 2
                and i.split(":")[0]
                and i.split(":")[1]
            ]
        )


def list_equal_split(alist, n=5):
    return [alist[i : i + n] for i in range(0, len(alist), n)]


def generate_random(length=6):
    code_list = []
    for i in range(10):  # 0-9数字
        code_list.append(str(i))
    for i in range(65, 91):  # A-Z
        code_list.append(chr(i))
    for i in range(97, 123):  # a-z
        code_list.append(chr(i))
    myslice = sample(code_list, length)
    return "".join(myslice)


def format_upload_src(fmt, value):
    """转换upload路由中返回的src格式"""
    if fmt and isinstance(fmt, string_types):
        if point_pat.match(fmt):
            if "." in fmt:
                fmts = fmt.split(".")
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
            return ""


def get_origin(url):
    """从url提取出符合CORS格式的origin地址"""
    parsed_uri = urlparse(url)
    return "{uri.scheme}://{uri.netloc}".format(uri=parsed_uri)


def check_origin(addr):
    """Check whether UrlAddr is in a valid host origin, for example:

    .. code-block::

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


def check_url(addr):
    """Check whether UrlAddr is in a valid format"""
    if addr and isinstance(addr, string_types):
        if url_pat.match(addr):
            return True
    return False


def check_ip(ip_str):
    sep = ip_str.split(".")
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
    if not isinstance(datauri, text_type):
        datauri = datauri.decode("utf-8")
    match = data_uri_pat.match(datauri)
    if match:
        mimetype = match.group("mimetype") or None
        charset = match.group("charset") or None
        is_base64 = bool(match.group("base64"))
        data = match.group("data")
    else:
        mimetype = charset = data = None
        is_base64 = False

    return Attribution(
        dict(
            mimetype=mimetype,
            charset=charset,
            is_base64=is_base64,
            data=data,
        )
    )


def gen_ua():
    """随机生成用户代理"""
    first_num = randint(55, 62)
    third_num = randint(0, 3200)
    fourth_num = randint(0, 140)
    os_type = [
        "(Windows NT 6.1; WOW64)",
        "(Windows NT 10.0; WOW64)",
        "(X11; Linux x86_64)",
        "(Macintosh; Intel Mac OS X 10_12_6)",
    ]
    chrome_version = "Chrome/{}.0.{}.{}".format(
        first_num, third_num, fourth_num
    )
    ua = " ".join(
        [
            "Mozilla/5.0",
            choice(os_type),
            "AppleWebKit/537.36",
            "(KHTML, like Gecko)",
            chrome_version,
            "Safari/537.36",
        ]
    )
    return ua


def parse_ua(user_agent):
    """解析用户代理，获取其操作系统、设备、版本"""
    uap = user_agents_parse(user_agent)
    device, ua_os, family = str(uap).split(" / ")
    if uap.is_mobile:
        platform = "mobile"
    elif uap.is_pc:
        platform = "pc"
    elif uap.is_tablet:
        platform = "tablet"
    elif uap.is_bot:
        platform = "bot"
    else:
        platform = "other"
    if (
        user_agent.startswith("picbed-cli") or user_agent.startswith("sapicli")
    ) and user_agent.endswith("amd64"):
        _, _, ua_os, device = user_agent.split(" ")
        family = "sapicli"
    return dict(platform=platform, device=device, os=ua_os, family=family)


def slash_join(*args):
    """用 / 连接参数"""
    stripped_strings = []
    for a in args:
        if a[0] == "/":
            start = 1
        else:
            start = 0
        if a[-1] == "/":
            stripped_strings.append(a[start:-1])
        else:
            stripped_strings.append(a[start:])
    return "/".join(stripped_strings)


def try_request(
    url,
    params=None,
    data=None,
    headers=None,
    timeout=5,
    method="post",
    proxy=None,
    num_retries=1,
    _is_retry=False,
) -> requests.Response:
    """
    :param dict params: 请求查询参数
    :param dict data: 提交表单数据
    :param int timeout: 超时时间，单位秒
    :param str method: 请求方法，get、post、put、delete
    :param str proxy: 设置代理服务器
    :param int num_retries: 超时重试次数
    :param bool _is_retry: 判定为重试请求，这不应该由用户发出
    """
    headers = headers or {}
    if "User-Agent" not in headers:
        headers["User-Agent"] = "sapic/v%s" % PICBED_VERSION
    method = method.lower()
    if method == "get":
        method_func = requests.get
    elif method == "post":
        method_func = requests.post
    elif method == "put":
        method_func = requests.put
    elif method == "delete":
        method_func = requests.delete
    else:
        method_func = requests.post
    try:
        resp = method_func(
            url,
            params=params,
            headers=headers,
            data=data,
            timeout=timeout,
            proxies=proxy if _is_retry is True and proxy else None,
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        if num_retries > 0:
            return try_request(
                url,
                params=params,
                data=data,
                headers=headers,
                timeout=timeout,
                method=method,
                proxy=proxy,
                num_retries=num_retries - 1,
                _is_retry=True,
            )
        else:
            raise
    except (requests.exceptions.RequestException, Exception):
        raise
    else:
        return resp


def is_venv():
    """判断当前环境是否在virtualenv、venv下"""
    return hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )


def is_all_fail(alist):
    """从list下的dict拿出code!=0的(执行失败)数量"""
    return len(alist) == len(list(filter(lambda x: x.get("code") != 0, alist)))


def check_to_addr(to):
    """检测收件人格式"""
    to_addrs = parse_valid_comma(to)
    if to_addrs:
        for to in to_addrs:
            if not mail_pat.match(to):
                return False
        return True


class Mailbox(object):
    def __init__(self, user, passwd, smtp_server, smtp_port=25):
        """初始化邮箱客户端配置。

        :param user: 邮箱地址
        :param passwd: 邮箱密码或可登录的授权码
        :param smtp_server: 邮箱的SMTP服务器地址
        """
        self._user = user
        self._passwd = passwd
        self._server = smtp_server
        self._port = smtp_port
        self._ssl = False if self._port == 25 else True
        self._debug = False

    @property
    def ssl(self):
        """是否使用加密连接，支持setter"""
        return self._ssl

    @ssl.setter
    def ssl(self, smtp_ssl):
        self._ssl = is_true(smtp_ssl)

    @property
    def debug(self):
        """是否开启debug模式，支持setter"""
        return self._debug

    @debug.setter
    def debug(self, level):
        if isinstance(level, int) or level is False:
            self._debug = level

    def _format_addr(self, s):
        name, addr = parseaddr(s)
        return formataddr((Header(name, "utf-8").encode(), addr))

    def send(self, subject, message, to_addrs, from_name=None):
        """Sendmail

        :param subject: 邮件主题
        :param message: 内容，支持HTML
        :param to_addrs: 收件人，支持多个
        :returns: send result
        :rtype: dict
        """
        res = dict(code=1)
        if subject and message and to_addrs:
            if not isinstance(to_addrs, (list, tuple)):
                to_addrs = (to_addrs,)
            msg = MIMEText(message, "html", "utf-8")
            msg["from"] = self._format_addr(
                "{0} <{1}>".format(
                    from_name or self._user.split("@")[0], self._user
                )
            )
            msg["to"] = ";".join(to_addrs)
            msg["subject"] = Header(subject, "utf-8").encode()
            try:
                if self._ssl is True:
                    server = smtplib.SMTP_SSL(self._server, self._port)
                else:
                    server = smtplib.SMTP(self._server, self._port)
                if self._debug:  # not False, > 0
                    server.set_debuglevel(self._debug)
                if self._user and self._passwd:
                    server.login(self._user, self._passwd)
                server.sendmail(self._user, to_addrs, msg.as_string())
                server.quit()
            except (smtplib.SMTPException, ConnectionRefusedError) as e:
                res.update(msg=str(e))
            else:
                res.update(code=0)
        else:
            res.update(msg="Bad mailbox params")
        return res


def bleach_html(
    html,
    tags: Optional[List[str]] = None,
    attrs: Optional[Dict[str, List[str]]] = None,
    css: Optional[CSSSanitizer] = None,
):
    """清洗HTML，设置中仅允许部分标签、属性和样式。"""
    from config import GLOBAL

    _tags = tags or list(ALLOWED_TAGS)
    _ext_tags = parse_valid_comma(GLOBAL["AllowTags"])
    _ext_styles = parse_valid_comma(GLOBAL["AllowStyles"])
    _tags.extend(_ext_tags)
    if isinstance(css, CSSSanitizer) and _ext_styles:
        css.allowed_css_properties.extend(_ext_styles)
    return bleach_clean(
        html,
        tags=_tags,
        attributes=attrs or ALLOWED_ATTRIBUTES,
        css_sanitizer=css,
    )


def is_valid_verion(version):
    """Semantic version number - determines whether the version is qualified.
    The format is MAJOR.Minor.PATCH, more with https://semver.org

    :param str version: 版本号
    """
    if not version:
        return False
    if not isinstance(version, string_types):
        version = version.decode("utf-8")

    if hasattr(semver.VersionInfo, "isvalid"):
        return semver.VersionInfo.isvalid(version or "")

    try:
        semver.parse(version)
    except (TypeError, ValueError):
        return False
    else:
        return True


def is_match_appversion(appversion=None):
    """确认当前应用版本是否符合appversion要求

    :param str appversion: 使用操作符和分组符匹配程序版本
    """
    #: 没有要求appversion则默认认为兼容所有版本
    if not appversion:
        return True
    if not isinstance(appversion, string_types):
        appversion = appversion.decode("utf-8")

    sysver = semver.VersionInfo.parse(PICBED_VERSION)

    def vermatch(check_ver):
        try:
            return sysver.match(check_ver)
        except ValueError:
            return sysver.match(">={}".format(check_ver))

    avs = comma_pat.split(appversion)
    for v in avs:
        if not vermatch(v):
            return False
    else:
        return True


def less_latest_tag(latest_tag):
    """当前应用是否小于GitHub最新版本比较"""
    if latest_tag and is_valid_verion(latest_tag):
        return semver.compare(latest_tag, PICBED_VERSION) == 1


def parse_author_mail(author):
    """从形如 ``author <author-mail>`` 中分离author与mail"""
    pat = author_mail_re.search(author)
    return (pat.group(1), pat.group(2)) if pat else (author, None)


def parse_label(label):
    if label:
        label = parse_valid_comma(label)
    else:
        label = []
    if isinstance(label, (list, tuple)):
        return label
    return []


def b64size(b64string):
    """获取base64内容大小，单位bytes"""
    return (len(b64string) * 3) / 4 - b64string.count("=", -2)


def raise_version():
    vs = sys.version_info
    if (vs[0], vs[1]) < (3, 9):
        raise RuntimeError("The system requires python version 3.9+")
