# -*- coding: utf-8 -*-
"""
    utils.web
    ~~~~~~~~~

    Some web app tool classes and functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from functools import wraps
from base64 import urlsafe_b64decode as b64decode
from redis.exceptions import RedisError
from flask import g, redirect, request, url_for, abort, Response, jsonify,\
    current_app
from libs.storage import get_storage
from .tool import logger, get_current_timestamp, create_redis_engine, rsp, \
    sha256, username_pat, parse_valid_comma
from ._compat import PY2, text_type

rc = create_redis_engine()


def default_login_auth():
    """默认登录解密，返回: (signin:boolean, userinfo:dict)"""
    sid = request.cookies.get("dSid") or ""
    signin = False
    userinfo = {}
    print('web', sid, type(sid))
    try:
        if PY2 and isinstance(sid, text_type):
            sid = sid.encode("utf-8")
        sid = b64decode(sid)
        if not PY2 and not isinstance(sid, text_type):
            sid = sid.decode("utf-8")
        usr, expire, sha = sid.split(".")
        expire = int(expire)
    except (TypeError, ValueError, AttributeError, Exception) as e:
        current_app.logger.info(e, exc_info=True)
    else:
        print('web', usr, expire, sha)
        if expire > get_current_timestamp():
            ak = rsp("account")
            pipe = rc.pipeline()
            pipe.sismember(ak, usr)
            pipe.hgetall(rsp("user", usr))
            try:
                result = pipe.execute()
            except RedisError:
                pass
            else:
                print('web', result)
                if isinstance(result, (tuple, list)) and len(result) == 2:
                    has_usr, userinfo = result
                    if has_usr and userinfo and isinstance(userinfo, dict):
                        pwd = userinfo.pop("password", None)
                        print('web', pwd, current_app.config["SECRET_KEY"])
                        if sha256("%s:%s:%s:%s" % (
                            usr, pwd, expire, current_app.config["SECRET_KEY"]
                        )) == sha:
                            signin = True
                            print('web', signin)
    if not signin:
        userinfo = {}
    return (signin, userinfo)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.signin:
            return redirect(url_for('front.login'))
        return f(*args, **kwargs)
    return decorated_function


def apilogin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.signin:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function


def admin_apilogin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.signin:
            if g.is_admin:
                return f(*args, **kwargs)
            else:
                return abort(403)
        else:
            return abort(404)
    return decorated_function


def parseAcceptLanguage(acceptLanguage, defaultLanguage="zh-CN"):
    if not acceptLanguage:
        return defaultLanguage
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
    )[0][0] or defaultLanguage


def dfr(res, default='en-US'):
    """定义前端返回，将res中msg字段转换语言
    @param res dict: like {"msg": None, "success": False}, 英文格式
    @param default str: 默认语言
    """
    try:
        language = parseAcceptLanguage(
            request.cookies.get(
                "locale",
                request.headers.get('Accept-Language', default)
            ),
            default
        )
        if language == "zh-Hans-CN":
            language = "zh-CN"
    except:
        language = default
    # 翻译转换字典库
    trans = {
        # 简体中文
        "zh-CN": {
            "Hello World": "你好，世界",
            "Parameter error": "参数错误",
            "The upload_path type error": "upload_path类型错误",
            "The upyun parameter error": "又拍云相关参数错误",
            "Please install upyun module": "请安装upyun模块",
            "An unknown error occurred in the program": "程序发生未知错误",
            "Anonymous user is not sign in": "匿名用户未登录",
            "No valid username found": "未发现有效用户名",
            "No data": "没有数据",
            "No file or image format allowed": "未获取到文件或不允许的图片格式",
            "Program data storage service error": "程序数据存储服务异常",
            "All backend storage services failed to save pictures": "后端存储服务图片保存全部失败",
            "No valid backend storage service": "无有效后端存储服务",
            "The third module not found": "第三方模块未发现",
            "Password verification failed": "密码验证失败",
        },
    }
    if isinstance(res, dict) and "en" not in language:
        if res.get("msg"):
            msg = res["msg"]
            try:
                new = trans[language][msg]
            except KeyError:
                logger.warn("Miss translation: %s" % msg)
            else:
                res["msg"] = new
    return res


def get_site_config():
    s = get_storage()
    cfg = s.get("siteconfig") or {}
    return cfg


def set_site_config(mapping):
    if mapping and isinstance(mapping, dict):
        print(mapping)
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


class JsonResponse(Response):

    @classmethod
    def force_type(cls, rv, environ=None):
        if isinstance(rv, dict):
            rv = jsonify(rv)
        return super(JsonResponse, cls).force_type(rv, environ)
