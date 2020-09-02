# -*- coding: utf-8 -*-
"""
    utils.web
    ~~~~~~~~~

    Some web app tool classes and functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import json
import imghdr
from posixpath import basename, splitext
from os.path import join as pathjoin
from io import BytesIO
from functools import wraps
from base64 import urlsafe_b64decode as b64decode, b64decode as pic64decode
from binascii import Error as BaseDecodeError
from redis.exceptions import RedisError
from requests.exceptions import RequestException
from flask import g, redirect, request, url_for, abort, Response, jsonify,\
    current_app, make_response, Markup
from jinja2 import Environment, FileSystemLoader
from sys import executable
from functools import partial
from subprocess import call, check_output
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, \
    SignatureExpired, BadSignature
from libs.storage import get_storage
from .tool import logger, get_current_timestamp, rsp, sha256, username_pat, \
    parse_valid_comma, parse_data_uri, format_apires, url_pat, ALLOWED_EXTS, \
    parse_valid_verticaline, parse_valid_colon, is_true, is_venv, gen_ua, \
    check_to_addr, is_all_fail, bleach_html, try_request, comma_pat, \
    create_redis_engine, allowed_file
from ._compat import PY2, text_type, urlsplit, parse_qs
if not PY2:
    from functools import reduce

rc = create_redis_engine()

no_jump_ep = ("front.login", "front.logout", "front.register")


def get_referrer_url():
    """获取上一页地址"""
    if request.method == "GET" and request.referrer and \
            request.referrer.startswith(request.host_url) and \
            request.endpoint and "api." not in request.endpoint and \
            request.endpoint not in no_jump_ep:
        url = request.referrer
    else:
        url = None
    return url


def get_redirect_url(endpoint="front.index"):
    """获取重定向地址"""
    url = request.args.get('next')
    if not url:
        if endpoint != "front.index":
            url = url_for(endpoint)
        else:
            url = get_referrer_url() or (
                request.full_path if request.endpoint not in no_jump_ep
                else None
            ) or url_for(endpoint)
    return url


def default_login_auth(dSid=None):
    """默认登录解密

    :returns: (signin:boolean, userinfo:dict)
    """
    sid = request.cookies.get("dSid") or dSid or ""
    signin = False
    userinfo = {}
    try:
        if not sid:
            raise ValueError
        if PY2 and isinstance(sid, text_type):
            sid = sid.encode("utf-8")
        sid = b64decode(sid)
        if not PY2 and not isinstance(sid, text_type):
            sid = sid.decode("utf-8")
        usr, expire, sha = sid.split(".")
        expire = int(expire)
    except (TypeError, ValueError, AttributeError, Exception):
        pass
    else:
        if expire > get_current_timestamp():
            ak = rsp("accounts")
            pipe = g.rc.pipeline()
            pipe.sismember(ak, usr)
            pipe.hgetall(rsp("account", usr))
            try:
                result = pipe.execute()
            except RedisError:
                pass
            else:
                if isinstance(result, (tuple, list)) and len(result) == 2:
                    has_usr, userinfo = result
                    if has_usr and userinfo and isinstance(userinfo, dict):
                        pwd = userinfo.pop("password", None)
                        if sha256("%s:%s:%s:%s" % (
                            usr, pwd, expire, current_app.config["SECRET_KEY"]
                        )) == sha:
                            signin = True
    if not signin:
        userinfo = {}
    return (signin, userinfo)


def login_required(f):
    """页面要求登录装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.signin:
            nu = get_redirect_url()
            if nu and (
                nu.startswith("/") or nu.startswith(request.url_root)
            ):
                return redirect(url_for('front.login', next=nu))
            else:
                return redirect(url_for('front.login'))
        return f(*args, **kwargs)
    return decorated_function


def anonymous_required(f):
    """页面要求匿名装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.signin:
            return redirect(url_for('front.index'))
        return f(*args, **kwargs)
    return decorated_function


def apilogin_required(f):
    """接口要求登录装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.signin:
            return abort(403)
        if g.signin and g.userinfo.status == 0:
            return abort(make_response(jsonify(
                msg="The user is disabled, no operation",
                code=403
            ), 403))
        return f(*args, **kwargs)
    return decorated_function


def admin_apilogin_required(f):
    """接口要求管理员级别登录装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.signin:
            if g.is_admin and g.userinfo.status == 1:
                return f(*args, **kwargs)
            else:
                return abort(403)
        else:
            return abort(404)
    return decorated_function


def parse_accept_language(acceptLanguage, default_language="zh-CN"):
    if not acceptLanguage:
        return default_language
    languages = acceptLanguage.split(",")
    locale_q_pairs = []
    for language in languages:
        if language.split(";")[0] == language:
            # no q => q = 1
            locale_q_pairs.append((language.strip(), "1"))
        else:
            locale = language.split(";")[0].strip()
            q = language.split(";")[1].split("=")[1]
            locale_q_pairs.append((locale, q))
    return sorted(
        locale_q_pairs,
        key=lambda x: x[-1],
        reverse=True
    )[0][0] or default_language


def dfr(res, default='en-US'):
    """定义前端返回，将res中msg字段转换语言

    :param dict res: 例如 {"msg": "翻译内容(英文)", "other": "xx"}
    :param str default: 默认语言
    """
    try:
        language = parse_accept_language(
            request.cookies.get(
                "locale",
                request.headers.get('Accept-Language', default)
            ),
            default
        )
        if language == "zh-Hans-CN":
            language = "zh-CN"
    except (ValueError, TypeError, KeyError, Exception):
        language = default
    # 翻译转换字典库 TODO 翻译文本文件，按英文索引
    trans = {
        # 简体中文
        "zh-CN": {
            "Hello World": "你好，世界",
            "Parameter error": "参数错误",
            "The upload_path type error": "upload_path类型错误",
            "The upyun parameter error": "又拍云相关参数错误",
            "Please install upyun module": "请安装upyun模块",
            "Please install qiniu module": "请安装qiniu模块",
            "The qiniu parameter error": "七牛云相关参数错误",
            "The aliyun parameter error": "阿里云oss相关参数错误",
            "The tencent parameter error": "腾讯云cos相关参数错误",
            "The sm.ms parameter error": "sm.ms相关参数错误",
            "The github parameter error": "GitHub相关参数错误",
            "The gitee parameter error": "Gitee相关参数错误",
            "An unknown error occurred in the program": "程序发生未知错误",
            "Program data storage service error": "程序数据存储服务异常",
            "Anonymous user is not sign in": "匿名用户未登录",
            "No valid username found": "未发现有效用户名",
            "The username or password parameter error": "用户名或密码参数错误",
            "No data": "没有数据",
            "No file or image format error": "未获取到文件或不允许的图片格式",
            "All backend storage services failed to save pictures": "后端存储服务图片保存全部失败",
            "No valid backend storage service": "无有效后端存储服务",
            "No valid backend hook": "无有效后端钩子",
            "The third module not found": "第三方模块未发现",
            "Password verification failed": "密码验证失败",
            "Password must be at least 6 characters": "密码最少6位",
            "Confirm passwords do not match": "确认密码不匹配",
            "Existing token": "已有token",
            "No token yet": "还未有token",
            "The username is invalid or registration is not allowed": "用户名不合法或不允许注册",
            "The username already exists": "用户名已存在",
            "Normal user login has been disabled": "已禁止普通用户登录",
            "Illegal users are not allowed to modify": "不合法的用户禁止修改",
            "The user setting must start with `ucfg_`": "用户设置必须以`ucfg_`开头",
            "Invalid IP address": "无效的IP地址",
            "Invalid url address": "无效的url",
            "Not found the LinkId": "没有此LinkId",
            "Not found the endpoint": "无此endpoint路由端点",
            "Invalid HTTP method": "无效http方法",
            "Invalid exterior_relation": "无效的exterior_relation平行规则",
            "Invalid interior_relation": "无效的interior_relation内联规则",
            "Wrong query range parameter": "查询范围错误",
            "accepted": "已接受",
            "Pending review, cannot upload pictures": "审核中，不能上传图片",
            "The user is disabled, no operation": "用户被禁用，无权操作",
            "Email send failed": "邮件发送失败",
            "expired token": "token过期",
            "useless": "无用token",
            "Current state prohibits use of this method": "当前状态禁止使用此方法",
            "The user has no authenticated mailbox": "用户没有验证过的邮箱",
            "Interceptor processing rejection, upload aborted": "拦截器处理拒绝，上传中止",
            "Request fail": "请求失败",
            "Invalid expire param": "无效的expire参数",
            "Users also have pictures that cannot be deleted": "用户还有图片，不能删除",
        },
    }
    if isinstance(res, dict) and "en" not in language:
        if res.get("msg"):
            msg = res["msg"]
            try:
                new = trans[language][msg]
            except KeyError:
                logger.debug("Miss translation: %s" % msg)
            else:
                res["msg"] = new
    return res


def change_res_format(res):
    if isinstance(res, dict) and "code" in res:
        sn = request.form.get(
            "status_name", request.args.get("status_name")
        ) or "code"
        oc = request.form.get("ok_code", request.args.get("ok_code"))
        mn = request.form.get("msg_name", request.args.get("msg_name"))
        return format_apires(res, sn, oc, mn)
    return res


def change_userinfo(userinfo):
    """解析用户信息userinfo部分字段数据"""
    if userinfo and isinstance(userinfo, dict):
        userinfo.update(
            parsed_ucfg_url_rule=parse_valid_colon(
                userinfo.get("ucfg_url_rule")
            ) or {},
            parsed_ucfg_url_rule_switch=dict(
                loadmypic=is_true(g.userinfo.get("ucfg_urlrule_inloadmypic")),
                url=is_true(g.userinfo.get("ucfg_urlrule_incopyurl")),
                html=is_true(g.userinfo.get("ucfg_urlrule_incopyhtml")),
                rst=is_true(g.userinfo.get("ucfg_urlrule_incopyrst")),
                markdown=is_true(g.userinfo.get("ucfg_urlrule_incopymd")),
            ),
            #: ..versionadded:: 1.7.0
            #: 用户状态默认是1启用，-2、-1待审核仅无法上传，0禁用无任何权限
            status=int(userinfo.get("status", 1)),
        )
    return userinfo


def get_site_config():
    """获取站点配置"""
    s = get_storage()
    cfg = s.get("siteconfig") or {}
    return cfg


def set_site_config(mapping):
    """设置站点信息"""
    if mapping and isinstance(mapping, dict):
        ALLOWED_TAGS = ['a', 'abbr', 'b', 'i', 'code', 'p', 'br', 'h3', 'h4']
        ALLOWED_ATTRIBUTES = {
            'a': ['href', 'title', 'target'],
            'abbr': ['title'],
            '*': ['style'],
        }
        ALLOWED_STYLES = ['color']
        upload_beforehtml = mapping.get("upload_beforehtml") or ""
        bulletin = mapping.get("bulletin") or ""
        if upload_beforehtml:
            mapping["upload_beforehtml"] = bleach_html(
                upload_beforehtml,
                ALLOWED_TAGS, ALLOWED_ATTRIBUTES, ALLOWED_STYLES
            )
        if bulletin:
            ALLOWED_TAGS.append("img")
            ALLOWED_ATTRIBUTES["img"] = [
                'title', 'alt', 'src', 'width', 'height'
            ]
            mapping["bulletin"] = bleach_html(
                bulletin,
                ALLOWED_TAGS, ALLOWED_ATTRIBUTES, ALLOWED_STYLES
            )
        s = get_storage()
        cfg = s.get("siteconfig") or {}
        cfg.update(mapping)
        s.set("siteconfig", cfg)


def check_username(usr):
    """检测用户名是否合法、是否可以注册"""
    if usr and username_pat.match(usr):
        cfg = get_site_config()
        fus = set(parse_valid_comma(cfg.get("forbidden_username") or ''))
        fus.add("anonymous")
        if usr not in fus:
            return True
    return False


def guess_filename_from_url(url, allowed_exts=None):
    """从url中猜测图片文件名，其后缀符合控制台设定或默认予以返回。

    首先尝试从url path猜测，比如http://example.com/upload/abc.png，这合法。

    如果猜测失败，则从url query查找filename查询参数。

    :param str url: 图片地址
    :param list allowed_exts: 允许的图片后缀，比如['png', 'jpg']，
                              如未设置，则使用控制台设定或默认
    :returns: 当图片合法时返回filename，否则None

    .. versionadded:: 1.10.0
    """
    _allowed_exts = [
        ".{}".format(e)
        for e in (
            allowed_exts or parse_valid_verticaline(
                g.cfg.upload_exts
            ) or ALLOWED_EXTS
        )
    ]
    ufn = basename(urlsplit(url).path)
    if splitext(ufn)[-1] in _allowed_exts:
        return ufn
    else:
        fns = parse_qs(urlsplit(url).query).get("filename")
        if fns and isinstance(fns, (list, tuple)):
            filename = fns[0]
            if splitext(filename)[-1] in _allowed_exts:
                return filename


class JsonResponse(Response):

    @classmethod
    def force_type(cls, rv, environ=None):
        if isinstance(rv, dict):
            rv = jsonify(rv)
        return super(JsonResponse, cls).force_type(rv, environ)


class Base64FileStorage(object):
    """上传接口中接受base64编码的图片。

    允许来自前端的Data URI形式:
        https://developer.mozilla.org/docs/Web/HTTP/data_URIs
    """

    def __init__(self, b64str, filename=None):
        self._filename = filename
        #: data uri scheme
        self._b64str = self.__set_data_uri(b64str)
        self._parse = parse_data_uri(self._b64str)
        if self.is_base64:
            try:
                self._parse["data"] = pic64decode(self._parse.data)
            except (BaseDecodeError, TypeError, ValueError):
                raise ValueError("The attempt to decode the image failed")
        else:
            raise ValueError("Not found base64")

    def __set_data_uri(self, b64str):
        if not PY2 and not isinstance(b64str, text_type):
            b64str = b64str.decode("utf-8")
        if not b64str.startswith("data:"):
            b64str = "data:;base64,%s" % b64str
        return b64str

    @property
    def mimetype(self):
        return self._parse.mimetype

    @property
    def filename(self):
        if not self._filename:
            ext = imghdr.what(None, self._parse.data)
            if not ext and self.mimetype:
                mType, sType = self.mimetype.split("/")
                if mType == "image":
                    ext = sType
            self._filename = "{}.{}".format(get_current_timestamp(), ext)
        return self._filename

    @property
    def is_base64(self):
        return self._parse.is_base64

    @property
    def stream(self):
        if self.is_base64:
            return BytesIO(self._parse.data)


class ImgUrlFileStorage(object):
    """上传接口中接受远程图片地址，会自动调用代理下载图片。"""

    def __init__(self, imgurl, filename=None, allowed_exts=None):
        self._imgurl = imgurl
        self._filename = filename
        self._allowed_exts = [
            ".{}".format(e)
            for e in (
                allowed_exts or [] or parse_valid_verticaline(
                    g.cfg.upload_exts
                ) or ALLOWED_EXTS
            )
        ]
        self._imgobj = self.__download()

    @property
    def Headers(self):
        return {"User-Agent": gen_ua()}

    def __download(self):
        if self._imgurl and url_pat.match(self._imgurl):
            try:
                resp = try_proxy_request(
                    self._imgurl,
                    method='get',
                    headers=self.Headers,
                    timeout=15,
                )
                resp.raise_for_status()
            except (RequestException, Exception) as e:
                logger.debug(e, exc_info=True)
            else:
                if resp.headers["Content-Type"].split("/")[0] == "image":
                    return resp

    @property
    def filename(self):
        """定义url图片文件名：
        如果给定文件名，则用，否则从url path猜测。
        猜测失败，从url query查找filename参数。
        未果，则读取图片二进制猜测格式。
        未果，从返回标头Content-Type解析image类型。
        未果，文件名后缀可能是None，将不合要求。
        """
        if not self._filename and self._imgobj:
            ufn = guess_filename_from_url(self._imgobj.url, self._allowed_exts)
            if ufn and splitext(ufn)[-1] in self._allowed_exts:
                self._filename = ufn
                return ufn
            ext = imghdr.what(None, self._imgobj.content)
            if not ext:
                mType, sType = self._imgobj.headers["Content-Type"].split("/")
                if mType == "image":
                    ext = sType
            self._filename = "{}.{}".format(get_current_timestamp(), ext)
        return self._filename

    @property
    def stream(self):
        if self._imgobj:
            return BytesIO(self._imgobj.content)

    @property
    def getObj(self):
        f = self.filename
        if f and splitext(f)[-1] in self._allowed_exts:
            return self if self._imgobj else None


def get_upload_method(class_name):
    if class_name == "FileStorage":
        return "file"
    elif class_name == "ImgUrlFileStorage":
        return "url"
    elif class_name == "Base64FileStorage":
        return "base64"
    else:
        return "unknown"


def _pip_install(pkg, index=None, upgrade=None):
    """使用pip安装模块到用户目录$HOME/.local"""
    cmd = [executable, "-m", "pip", "install", "-q"]
    if not is_venv():
        cmd.append("--user")
    if upgrade:
        cmd.append("-U")
    if index:
        cmd.extend(["-i", index])
    cmd.append(pkg)
    retcode = call(cmd)
    if retcode == 0:
        set_page_msg(pkg + " 安装成功", "success")
        _pip_list(no_fresh=False)
    else:
        set_page_msg(pkg + " 安装失败", "warn")
    logger.info("{}, retcode: {}".format(" ".join(cmd), retcode))


def _pip_list(fmt=None, no_fresh=True):
    """获取pip list的JSON结果"""
    key = rsp("cache", "piplist")
    data = rc.get(key)
    if is_true(no_fresh) and data:
        data = json.loads(data)
    else:
        cmd = [executable, "-m", "pip", "list", "--format", "json"]
        data = json.loads(check_output(cmd))
        pipe = rc.pipeline()
        pipe.set(key, json.dumps(data))
        pipe.expire(key, 3600)
        pipe.execute()
    if fmt == "dict":
        return {n["name"]: n for n in data}
    else:
        return data


def generate_activate_token(dump_data, max_age=600):
    if dump_data and isinstance(dump_data, dict):
        s = Serializer(current_app.config['SECRET_KEY'], expires_in=max_age)
        data = s.dumps(dump_data)
        return data.decode()


def check_activate_token(token):
    res = dict(code=400)
    if token:
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            res.update(code=403, msg='expired token')
        except BadSignature:
            res.update(code=404, msg='useless token')
        else:
            res.update(code=0, data=data)
    else:
        res.update(msg='Parameter error')
    return res


def sendmail(subject, message, to):
    """调用钩子中发送邮件函数（任意钩子发送成功即停止）

    :param str subject: 主题
    :param str message: 正文（支持HTML）
    :param str to: 收件人，可用逗号添加多个
    """
    res = dict(code=1)
    if subject and message and to and check_to_addr(to):
        to = ",".join(parse_valid_comma(to))
        data = current_app.extensions["hookmanager"].call(
            _funcname="sendmail",
            _mode="any_true",
            _args=(subject, message, to),
        )
        logger.debug(data)
        if is_all_fail(data):
            res.update(msg="Email send failed", errors=data)
            return res
        else:
            res.update(code=0)
    else:
        res.update(msg="Parameter error")
    return res


def make_email_tpl(tpl, **data):
    """制作邮件模板

    :param tpl: 模板文件（位于templates/email/下）
    :keyword data: 模板所用变量
    :returns: jinja2渲染好的html内容
    """
    je = Environment(
        loader=FileSystemLoader(pathjoin(
            current_app.root_path, current_app.template_folder, "email"
        ))
    )
    if "site_name" not in data:
        data["site_name"] = g.site_name
    if "url_root" not in data:
        data["url_root"] = request.url_root
    if "username" not in data:
        data["username"] = g.userinfo.nickname or g.userinfo.username
    return je.get_template(tpl).render(data)


def try_proxy_request(url, **kwargs):
    """自动调用代理服务的try_request

    :param str url: 请求地址
    :keyword kwars: :func:`utils.tool.try_request` 要求的其他参数

    .. versionadded:: 1.9.0
    """
    kwargs["proxy"] = dict([
        ps.split("=")
        for ps in comma_pat.split(g.cfg.proxies)
        if ps and "=" in ps
    ]) if g.cfg.proxies else None
    return try_request(url, **kwargs)


def set_page_msg(text, level='info'):
    """给管理员的控制台消息（任意环境均可）

    :param str text: 消息内容
    :param str level: 级别，info(默认)、success、error、warn

    .. versionadded:: 1.9.0
    """
    levels = dict(info=-1, warn=0, success=1, error=2)
    if text and level in levels.keys():
        return rc.rpush(rsp("msg", "admin", "control"), json.dumps(dict(
            text=text, icon=levels[level]
        )))


def get_page_msg():
    """生成消息Js，仅在管理员控制台页面闪现消息（仅Web环境调用）"""
    key = rsp("msg", "admin", "control")
    msgs = rc.lrange(key, 0, -1)
    if msgs:
        def tpl_plus(total, new):
            return total % new

        def make_layer(msg):
            return (
                'layer.alert("@1",{icon:@2,offset:"rt",shade:0,'
                'title:false,btn:"我知道了",btnAlign:"c",closeBtn:0},'
                'function(index){layer.close(index);%s});'
            ).replace('@1', msg["text"]).replace('@2', str(msg["icon"]))

        html = (
            '<script>',
            reduce(
                tpl_plus,
                map(make_layer, [json.loads(i) for i in msgs])
            ) % '',
            '</script>',
        )
        rc.delete(key)
        return Markup("".join(html))
    else:
        return ""


def push_user_msg(to, text, level='info', time=3, align='right'):
    """给用户推送消息（任意环境均可）

    :param str to: 用户名
    :param str text: 消息内容
    :param str level: 级别，info(默认)、success、error、warn
    :param int time: 超时时间，单位秒
    :param str align: 消息显示位置，right右上角、center顶部中间、left左上角

    .. versionadded:: 1.10.0
    """
    if to and text and level in ('info', 'warn', 'success', 'error') and \
            isinstance(time, int) and align in ('left', 'center', 'right'):
        if rc.exists(rsp("account", to)):
            return rc.rpush(rsp("msg", to), json.dumps(dict(
                text=text, level=level, time=time * 1000, align=align
            )))


def get_push_msg():
    """生成消息Js，仅在个人中心页面闪现消息（仅Web环境调用）"""
    key = rsp("msg", g.userinfo.username)
    msgs = rc.lrange(key, 0, -1)
    if msgs:
        def make_layer(data):
            return (
                'message.push("{text}","{level}","{align}",{time});'
            ).format(
                text=data["text"],
                level=data["level"],
                align=data["align"],
                time=int(data["time"]),
            )

        html = (
            '<script>'
            'layui.use("message",function(){var message = layui.message;%s});'
            '</script>'
        ) % ''.join(map(make_layer, [json.loads(i) for i in msgs]))
        rc.delete(key)
        return Markup(html)
    else:
        return ""


def get_user_ip():
    """首先从HTTP标头的X-Forwarded-For获取代理IP，其次获取X-Real-IP，最后是客户端IP"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For']
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr


def has_image(sha):
    """是否存在图片"""
    gk = rsp("index", "global")
    ik = rsp("image", sha)
    pipe = rc.pipeline()
    pipe.sismember(gk, sha)
    pipe.exists(ik)
    result = pipe.execute()
    return result == [True, 1]


def allowed_suffix(filename):
    """判断filename是否匹配控制台配置的上传后缀（及默认）

    :param str filename: 图片文件名
    :rtype: boolean

    .. versionadded:: 1.10.0
    """
    return partial(
        allowed_file,
        suffix=parse_valid_verticaline(g.cfg.upload_exts)
    )(filename)
