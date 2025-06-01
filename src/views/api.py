# -*- coding: utf-8 -*-
"""
    views.api
    ~~~~~~~~~

    Api view functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import json
from random import choice, randint
from posixpath import join, splitext
from base64 import urlsafe_b64encode as b64encode
from werkzeug.security import check_password_hash, generate_password_hash
from flask import (
    Blueprint,
    request,
    g,
    url_for,
    current_app,
    abort,
    make_response,
    jsonify,
    Response,
)
from redis.client import Pipeline
from redis.exceptions import RedisError
from collections import Counter
from itertools import chain
from utils.tool import (
    parse_valid_comma,
    is_true,
    logger,
    sha1,
    get_today,
    gen_rnd_filename,
    hmac_sha256,
    rsp,
    sha256,
    get_current_timestamp,
    list_equal_split,
    generate_random,
    er_pat,
    format_upload_src,
    check_origin,
    get_origin,
    check_ip,
    gen_uuid,
    ir_pat,
    username_pat,
    ALLOWED_HTTP_METHOD,
    is_all_fail,
    parse_valid_colon,
    check_ir,
    less_latest_tag,
    check_url,
    parse_label,
    allowed_file,
    ALLOWED_VIDEO,
    secure_filename
)
from utils.web import (
    dfr,
    admin_apilogin_required,
    apilogin_required,
    set_site_config,
    check_username,
    Base64FileStorage,
    FormFileStorage,
    ImgUrlFileStorage,
    get_upload_method,
    _pip_install,
    make_email_tpl,
    generate_activate_token,
    check_activate_token,
    try_proxy_request,
    sendmail,
    _pip_list,
    get_user_ip,
    has_image,
    guess_filename_from_url,
    allowed_suffix,
    async_sendmail,
    change_res_format,
    up_size_limit,
)
from utils._compat import iteritems, thread
from utils.exceptions import ApiError
from config import GLOBAL

bp = Blueprint("api", "api")


def get_url_with_suffix(d, _type):
    """根据type返回src
    :param dict d: image data
    :param str _type: url, html, md, rst
    """
    if (
        g.userinfo
        and "parsed_ucfg_url_rule_switch" in g.userinfo
        and is_true(g.userinfo.parsed_ucfg_url_rule_switch.get(_type))
    ):
        return "%s%s" % (
            d["src"],
            g.userinfo.parsed_ucfg_url_rule.get(d["sender"], ""),
        )
    return d["src"]


def gen_url_tpl(data):
    """根据图片数据返回src各种模板
    :param dict data: image data
    """

    def get_video(src):
        return (
            "<figure>"
            "<iframe src='%s' frameborder=0 allow='allowfullscreen'></iframe>"
            "</figure>"
        ) % src

    n = data["filename"]
    tpl = dict(
        URL="%s" % get_url_with_suffix(data, "url"),
    )
    if is_true(data.get("is_video")):
        tpl.update(
            HTML="<video src='%s' title='%s' controls></video>"
            % (get_url_with_suffix(data, "html"), data.get("title", "")),
            rST=".. raw:: html\n\n\t%s"
            % get_video(get_url_with_suffix(data, "rst")),
            Markdown=get_video(get_url_with_suffix(data, "rst")),
        )
    else:
        tpl.update(
            HTML="<img src='%s' title='%s' alt='%s'>"
            % (get_url_with_suffix(data, "html"), data.get("title", ""), n),
            rST=".. image:: %s" % get_url_with_suffix(data, "rst"),
            Markdown="![%s](%s)" % (n, get_url_with_suffix(data, "markdown")),
        )
    return tpl


@bp.after_request
def api_after_handler(res):
    if res.is_json:
        data = res.get_json()
        if isinstance(data, dict):
            #: go type system
            if data.get("msg") is None:
                data["msg"] = ""
            res.set_data(json.dumps(change_res_format(dfr(data))))
    return res


@bp.route("/", methods=["GET", "POST"])
@bp.route("/index", methods=["GET", "POST"])
def index():
    return jsonify(
        "Hello %s"
        % (g.userinfo.username if g.signin else GLOBAL["ProcessName"])
    )


@bp.route("/login", methods=["POST"])
def login():
    res = dict(code=1, msg=None)
    usr = request.form.get("username")
    pwd = request.form.get("password")
    #: 定义是否设置cookie状态
    set_state = is_true(request.form.get("set_state"))
    is_secure = False if request.url_root.split("://")[0] == "http" else True
    max_age = 7200
    if is_true(request.form.get("remember")):
        #: Remember me 7d
        max_age = 604800
    #: 登录接口钩子
    try:
        if g.cfg.site_auth:
            so = g.hm.proxy(g.cfg.site_auth)
            if so and hasattr(so, "login_api"):
                result = so.login_api(usr, pwd, set_state, max_age, is_secure)
                if result and isinstance(result, Response):
                    return result
    except (ValueError, TypeError, Exception) as e:
        logger.warning(e, exc_info=True)
    if usr and username_pat.match(usr) and pwd and len(pwd) >= 6:
        ak = rsp("accounts")
        usr = usr.lower()
        if g.rc.sismember(ak, usr):
            field = ("status", "password", "is_admin")
            userinfo = g.rc.hmget(rsp("account", usr), *field)
            userinfo = dict(zip(field, userinfo))
            userstatus = int(userinfo.get("status", 1))
            #: 已禁用用户不允许登录
            if userstatus == 0:
                res.update(code=403, msg="The user is disabled, no operation")
                return res
            #: 不允许普通用户登录
            if is_true(g.cfg.disable_login) and not is_true(
                userinfo.get("is_admin")
            ):
                res.update(msg="Normal user login has been disabled")
                return res
            password = userinfo.get("password")
            if password and check_password_hash(password, pwd):
                #: 登录成功
                pipe: Pipeline = g.rc.pipeline()
                pipe.hset(
                    rsp("account", usr), "login_at", get_current_timestamp()
                ).hset(rsp("account", usr), "login_ip", get_user_ip())
                pipe.execute()
                expire = get_current_timestamp() + max_age
                sid = "%s.%s.%s" % (
                    usr,
                    expire,
                    sha256(
                        "%s:%s:%s:%s"
                        % (
                            usr,
                            password,
                            expire,
                            current_app.config["SECRET_KEY"],
                        )
                    ),
                )
                sid = b64encode(sid.encode("utf-8")).decode("utf-8")
                res.update(
                    code=0,
                    sid=sid,
                    expire=expire,
                    # is_admin=is_true(userinfo.get("is_admin"))
                )
                if set_state:
                    res = make_response(jsonify(res))
                    res.set_cookie(
                        key="dSid",
                        value=sid,
                        max_age=max_age,
                        httponly=True,
                        secure=is_secure,
                        samesite="Lax",
                    )
            else:
                res.update(msg="Password verification failed")
        else:
            res.update(msg="No valid username found")
    else:
        res.update(msg="The username or password parameter error")
    return res


@bp.route("/register", methods=["POST"])
def register():
    if is_true(g.cfg.register) is False:
        return abort(404)
    res = dict(code=1, msg=None)
    #: Required fields
    username = request.form.get("username")
    password = request.form.get("password")
    if username and password:
        username = username.lower()
        if check_username(username):
            if len(password) < 6:
                res.update(msg="Password must be at least 6 characters")
            else:
                ak = rsp("accounts")
                if g.rc.sismember(ak, username):
                    res.update(msg="The username already exists")
                else:
                    #: 用户状态 -1待审核 0禁用 1启用 -2审核拒绝
                    #: 后台开启审核时默认是-1，否则是1
                    #: 禁用时无认证权限（无法登陆，无API权限）
                    #: 待审核仅无法上传，允许登录和API调用
                    review = is_true(g.cfg.review)
                    status = -1 if review else 1
                    #: 参数校验通过，执行注册
                    options = dict(
                        username=username,
                        password=generate_password_hash(password),
                        is_admin=0,
                        avatar=request.form.get("avatar") or "",
                        nickname=request.form.get("nickname") or "",
                        ctime=get_current_timestamp(),
                        status=status,
                        label=g.cfg.default_userlabel,
                    )
                    uk = rsp("account", username)
                    pipe: Pipeline = g.rc.pipeline()
                    pipe.sadd(ak, username)
                    for k, v in iteritems(options):
                        pipe.hset(uk, k, v)
                    try:
                        pipe.execute()
                    except RedisError:
                        res.update(msg="Program data storage service error")
                    else:
                        res.update(code=0)
                        #: send review email
                        viewmail = g.cfg.review_email
                        if review and viewmail:
                            msg = (
                                "新用户&nbsp;<b>{}</b>&nbsp;已经注册，请您尽快登录"
                                "&nbsp;<a href='{}'>图床后台</a>&nbsp;审核！"
                            ).format(
                                username,
                                url_for("front.admin", _external=True),
                            )
                            html = make_email_tpl(
                                "notify.html",
                                username="管理员",
                                foreword="您好",
                                content=msg,
                            )
                            async_sendmail("叮咚，新用户审核通知", html, viewmail)
        else:
            res.update(
                msg="The username is invalid or registration is not allowed"
            )
    else:
        res.update(msg="Parameter error")
    return res


@bp.route("/forgot", methods=["POST"])
def forgot():
    res = dict(code=1)
    Action = request.args.get("Action")
    username = request.form.get("username")
    if not username:
        res.update(msg="Parameter error")
        return res
    username = username.lower()
    ak = rsp("accounts")
    uk = rsp("account", username)

    #: 发送邮件
    if Action == "sending":
        if g.rc.sismember(ak, username):
            if is_true(int(g.rc.hget(uk, "email_verified") or 0)):
                html = make_email_tpl(
                    "activate_forgot.html",
                    activate_url=url_for(
                        "front.activate",
                        token=generate_activate_token(
                            dict(
                                Action="resetPassword",
                                username=username,
                            )
                        ),
                        _external=True,
                    ),
                    username=username,
                )
                res = sendmail(
                    subject="{}忘记密码".format(g.site_name),
                    message=html,
                    to=g.rc.hget(uk, "email"),
                )
            else:
                res.update(msg="The user has no authenticated mailbox")
        else:
            res.update(msg="No valid username found")

    #: 邮件验证通过，重置密码
    elif Action == "reset":
        token = request.form.get("token")
        password = request.form.get("password")
        if token and password:
            if len(password) < 6:
                res.update(msg="Password must be at least 6 characters")
            else:
                res = check_activate_token(token)
                if res["code"] == 0:
                    try:
                        g.rc.hset(
                            uk, "password", generate_password_hash(password)
                        )
                    except RedisError:
                        res.update(
                            code=1, msg="Program data storage service error"
                        )
                    else:
                        res.update(code=0)
        else:
            res.update(msg="Parameter error")

    return res


@bp.route("/config", methods=["POST"])
@admin_apilogin_required
def config():
    try:
        set_site_config(request.form.to_dict())
    except Exception as e:
        logger.error(e, exc_info=True)
        return dict(code=1, msg="An unknown error occurred in the program")
    else:
        return dict(code=0)


@bp.route("/hook", methods=["POST"])
@admin_apilogin_required
def hook():
    res = dict(code=1, msg=None)
    Action = request.args.get("Action")
    if Action == "query":
        data = g.hm.get_all_hooks_for_api
        res.update(code=0, data=data, count=len(data))
    elif Action == "disable":
        name = request.form.get("name")
        try:
            g.hm.disable(name)
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    elif Action == "enable":
        name = request.form.get("name")
        try:
            g.hm.enable(name)
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    elif Action == "reload":
        try:
            g.hm.reload()
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    elif Action == "add_third_hook":
        #: hook module name
        name = request.form.get("name","").strip()
        try:
            __import__(name)
            g.hm.add_third_hook(name)
        except ImportError as e:
            logger.debug(e, exc_info=True)
            res.update(msg="The third module not found")
        except Exception as e:
            logger.debug(e, exc_info=True)
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    elif Action == "remove_third_hook":
        name = request.form.get("name")
        try:
            g.hm.remove_third_hook(name)
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    return res


@bp.route("/user", methods=["GET", "DELETE", "PUT", "POST"])
@admin_apilogin_required
def user():
    """Manage users.

    .. versionadded:: 1.6.0
    """
    res = dict(code=1, msg=None)
    ak = rsp("accounts")
    Action = request.args.get("Action")
    if request.method == "GET":
        #: 查询用户
        sort = request.args.get("sort") or "desc"
        page = request.args.get("page") or 1
        limit = request.args.get("limit") or 10
        try:
            page = int(page) - 1
            limit = int(limit)
            if page < 0:
                raise ValueError
        except (ValueError, TypeError):
            res.update(code=2, msg="Parameter error")
        else:
            fds = (
                "username",
                "nickname",
                "avatar",
                "ctime",
                "mtime",
                "is_admin",
                "status",
                "message",
                "email",
                "email_verified",
                "status_reason",
                "label",
                "login_at",
                "login_ip",
            )
            pipe = g.rc.pipeline()
            for u in g.rc.smembers(ak):
                pipe.hmget(rsp("account", u), *fds)
                pipe.scard(rsp("index", "user", u))
            try:
                data = pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:

                def fmt(d):
                    d, user_pics = d
                    d = dict(zip(fds, d))
                    if d.get("status") is None:
                        d["status"] = 1
                    if d.get("email_verified") is None:
                        d["email_verified"] = 0
                    #: .. versionchanged:: 1.12.0
                    #:
                    #: 用户允许多label，以逗号分隔
                    label = parse_label(d.get("label"))
                    d.update(
                        is_admin=is_true(d["is_admin"]),
                        ctime=int(d["ctime"]),
                        status=int(d.get("status", 1)),
                        email_verified=int(d.get("email_verified", 1)),
                        login_at=int(d.get("login_at") or 0),
                        label=label,
                    )
                    if d.get("mtime"):
                        d["mtime"] = int(d["mtime"])
                    d["pics"] = user_pics
                    return d

                data = [fmt(d) for d in list_equal_split(data, 2)]
                data = sorted(
                    data,
                    key=lambda k: k.get("ctime", 0),
                    reverse=False if sort == "asc" else True,
                )
                count = len(data)
                data = list_equal_split(data, limit)
                pageCount = len(data)
                if page < pageCount:
                    res.update(
                        code=0,
                        count=count,
                        data=data[page],
                        pageCount=pageCount,
                    )
                else:
                    res.update(code=3, msg="No data")
    elif request.method == "DELETE":
        #: 删除用户
        username = request.form.get("username")
        if username:
            #: 不能自己删除自己
            if username == g.userinfo.username:
                res.update(code=4, msg="No valid username found")
                return res
            if g.rc.sismember(ak, username):
                pipe = g.rc.pipeline()
                pipe.srem(ak, username)
                pipe.delete(rsp("account", username))
                #: 删除用户相关数据
                # 删除图片
                uk = rsp("index", "user", username)
                for sha in g.rc.smembers(uk):
                    pipe.delete(rsp("image", sha))
                pipe.delete(uk)
                # 删除linktoken
                lk = rsp("linktokens")
                for ltid, usr in iteritems(g.rc.hgetall(lk)):
                    if usr == username:
                        pipe.hdel(lk, ltid)
                        pipe.delete(rsp("linktoken", ltid))
                # 删除统计
                pipe.delete(rsp("report", "linktokens", username))
                try:
                    pipe.execute()
                except RedisError:
                    res.update(msg="Program data storage service error")
                else:
                    res.update(code=0)
            else:
                res.update(code=3, msg="No valid username found")
        else:
            res.update(code=2, msg="No valid username found")
    elif request.method == "PUT":
        username = request.form.get("username")
        if Action in ("reviewOK", "reviewFail", "disable", "enable"):
            if username:
                if g.rc.sismember(ak, username):
                    #: 目前reviewFail时有用，拒绝理由
                    reason = ""
                    if Action == "reviewOK":
                        s = 1
                    elif Action == "reviewFail":
                        s = -2
                        reason = request.form.get("reason")
                    elif Action == "disable":
                        s = 0
                    else:
                        s = 1
                    uk = rsp("account", username)
                    pipe = g.rc.pipeline()
                    pipe.hset(uk, "status", s)
                    if reason:
                        pipe.hset(uk, "status_reason", reason)
                    try:
                        pipe.execute()
                    except RedisError:
                        res.update(msg="Program data storage service error")
                    else:
                        res.update(code=0)
                        mret = g.rc.hmget(uk, "email_verified", "email")
                        if is_true(mret[0]):
                            if Action == "reviewOK":
                                msg = (
                                    "您的注册申请已审核通过，请点击下方链接登录：<br>"
                                    "<a href='{link}'>{link}</a>"
                                ).format(
                                    link=url_for("front.index", _external=True)
                                )
                                html = make_email_tpl(
                                    "notify.html",
                                    username=username,
                                    foreword="欢迎使用 %s 图床" % g.site_name,
                                    content=msg,
                                )
                                async_sendmail("图床账号审核通过", html, mret[1])
                            elif Action == "reviewFail":
                                msg = (
                                    "很遗憾，您的注册申请经审核未通过！<br>"
                                    "原因是：{reason}<br>"
                                    "您可以登录留言再次审核：<br>"
                                    "<a href='{link}'>{link}</a>"
                                ).format(
                                    reason=reason,
                                    link=url_for(
                                        "front.index", _external=True
                                    ),
                                )
                                html = make_email_tpl(
                                    "notify.html",
                                    username=username,
                                    foreword="感谢注册 %s 图床" % g.site_name,
                                    content=msg,
                                )
                                async_sendmail("图床账号审核拒绝", html, mret[1])
                            elif Action == "disable":
                                html = make_email_tpl(
                                    "notify.html",
                                    username=username,
                                    foreword="感谢使用 %s 图床" % g.site_name,
                                    content="很抱歉地通知您，您的账号已被禁用！",
                                )
                                async_sendmail("图床账号禁用通知", html, mret[1])
                else:
                    res.update(code=3, msg="No valid username found")
            else:
                res.update(code=2, msg="No valid username found")
        elif Action == "admin":
            #: 设置/取消用户为管理员
            adm = 1 if is_true(request.form.get("is_admin")) else 0
            if username:
                if username != g.userinfo.username and g.rc.sismember(
                    ak, username
                ):
                    try:
                        g.rc.hset(rsp("account", username), "is_admin", adm)
                    except RedisError:
                        res.update(msg="Program data storage service error")
                    else:
                        res.update(code=0)
                else:
                    res.update(code=3, msg="No valid username found")
            else:
                res.update(code=2, msg="No valid username found")
        elif Action == "label":
            #: 给用户贴上标签，允许置空
            if username and g.rc.sismember(ak, username):
                label = request.form.get("label") or ""
                try:
                    g.rc.hset(rsp("account", username), "label", label)
                except RedisError:
                    res.update(msg="Program data storage service error")
                else:
                    res.update(code=0)
            else:
                res.update(code=3, msg="No valid username found")
    elif request.method == "POST":
        if Action == "labels":
            #: 综合获取用户标签
            pipe = g.rc.pipeline()
            for u in g.rc.smembers(ak):
                pipe.hget(rsp("account", u), "label")
            try:
                data = pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                labels = [parse_label(lb) for lb in data]
                labels = list(chain.from_iterable(labels))
                res.update(code=0, data=list(set(labels)))
    return res


@bp.route("/pip/install", methods=["POST"])
@admin_apilogin_required
def pip_install():
    """Use the pip command to install third-party modules.

    .. versionadded:: 1.6.0
    """
    res = dict(code=1, msg=None)
    pkg = request.form.get("package")
    index = request.form.get("index")
    upgrade = is_true(request.form.get("upgrade"))
    if pkg and not pkg.startswith(".") and not pkg.startswith("-"):
        thread.start_new_thread(_pip_install, (pkg, index, upgrade))
        res.update(code=0, msg="accepted")
        return jsonify(res), 201
    else:
        res.update(msg="Parameter error")
        return res


@bp.route("/test", methods=["POST"])
@admin_apilogin_required
def test():
    res = dict(code=1, msg=None)
    Action = request.args.get("Action")
    if Action == "sendmail":
        to = request.form.get("to")
        if to:
            res = sendmail(
                subject="邮件功能测试",
                message="恭喜！邮件发送成功！",
                to=to,
            )
        else:
            res.update(msg="Parameter error")
    return res


@bp.route("/github")
@admin_apilogin_required
def github():
    res = dict(code=1, msg=None)
    Action = request.args.get("Action")
    no_fresh = is_true(request.args.get("no_fresh", True))

    if Action == "thirdHooks":
        page = request.args.get("page") or 1
        limit = request.args.get("limit") or 5
        try:
            page = int(page) - 1
            limit = int(limit)
            if page < 0:
                raise ValueError
        except (ValueError, TypeError):
            raise ApiError("Parameter error")
        key = rsp("cache", "thirdhooks")
        data = g.rc.get(key)
        if no_fresh and data:
            res.update(code=0, data=json.loads(data))
        else:
            url = "https://api.github.com/repos/{}/contents/{}".format(
                "sapicd/awesome",
                "list.json",
            )
            headers = dict(Accept="application/vnd.github.v3.raw")
            try:
                r = try_proxy_request(url, headers=headers, method="GET")
                if not r.ok:
                    raise ValueError("Not Found")
            except (ValueError, Exception) as e:
                raise ApiError(str(e))
            else:
                data = r.json()
                res.update(code=0, data=data)
                pipe = g.rc.pipeline()
                pipe.set(key, json.dumps(data))
                pipe.expire(key, 3600 * 6)
                pipe.execute()
        if res["code"] == 0:

            def fmt(i, pkgs):
                pkg = i.get("pypi", "").replace("$name", i["name"])
                status = i.get("status")
                if status == "beta":
                    status_text = "公测版"
                elif status == "rc":
                    status_text = "预发布"
                elif status in ("stable", "production", "ga"):
                    status_text = "正式版"
                elif status == "archive":
                    status_text = "已封存"
                else:
                    status_text = "未知"
                if pkg:
                    pypi = "https://pypi.org/project/{}".format(pkg)
                else:
                    pypi = None
                user = i["github"].split("/")[0]
                i.update(
                    author=i.get("author", user),
                    home=i.get("home", "https://github.com/{}".format(user)),
                    github="https://github.com/{}".format(i["github"]),
                    pypi=pypi,
                    status_text=status_text,
                    pkg=dict(
                        name=pkg,
                        installed=pkg in pkgs,
                        local=pkgs.get(pkg),
                    ),
                )
                return i

            pkgs = _pip_list(fmt="dict", no_fresh=no_fresh)
            data = [
                fmt(i, pkgs)
                for i in res["data"]
                if isinstance(i, dict)
                and "name" in i
                and "module" in i
                and "desc" in i
                and "github" in i
            ]
            data.reverse()
            count = len(data)
            data = list_equal_split(data, limit)
            pageCount = len(data)
            if page < pageCount:
                res.update(
                    code=0,
                    count=count,
                    data=data[page],
                    pageCount=pageCount,
                )
            else:
                res.update(code=3, msg="No data")

    elif Action == "latestRelease":
        key = rsp("cache", "latestrelease")
        data = g.rc.get(key)
        if no_fresh and data:
            res.update(code=0, data=json.loads(data))
        else:
            url = "https://api.github.com/repos/sapicd/sapic/releases/latest"
            try:
                r = try_proxy_request(url, method="GET")
                if not r.ok:
                    raise ValueError("Not Found")
            except (ValueError, Exception) as e:
                logger.error(e, exc_info=True)
                res.update(msg=str(e))
            else:
                fields = ["tag_name", "published_at", "html_url"]
                data = {k: v for k, v in iteritems(r.json()) if k in fields}
                res.update(code=0, data=data)
                pipe = g.rc.pipeline()
                pipe.set(key, json.dumps(data))
                pipe.expire(key, 3600 * 24)
                pipe.execute()
        if res["code"] == 0:
            res["show_upgrade"] = less_latest_tag(res["data"]["tag_name"])

    return res


@bp.route("/token", methods=["POST"])
@apilogin_required
def token():
    res = dict(code=1, msg=None)
    usr = g.userinfo.username
    tk = rsp("tokens")
    ak = rsp("account", usr)

    def gen_token(key):
        """生成可以用key校验的token"""
        return b64encode(
            (
                "%s.%s.%s.%s"
                % (
                    generate_random(),
                    usr,
                    get_current_timestamp(),
                    hmac_sha256(key, usr),
                )
            ).encode("utf-8")
        ).decode("utf-8")

    Action = request.args.get("Action")
    if Action == "create":
        if g.rc.hget(ak, "token"):
            res.update(msg="Existing token")
        else:
            tkey = generate_random(randint(6, 12))
            token = gen_token(tkey)
            try:
                pipe: Pipeline = g.rc.pipeline()
                pipe.hset(tk, token, usr).hset(ak, "token", token).hset(
                    ak, "token_key", tkey
                )
                pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0, token=token)
    elif Action == "revoke":
        token = g.rc.hget(ak, "token")
        if token:
            try:
                pipe = g.rc.pipeline()
                pipe.hdel(tk, token)
                pipe.hdel(ak, "token")
                pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0)
        else:
            res.update(msg="No token yet")
    elif Action == "reset":
        oldToken = g.rc.hget(ak, "token")
        tkey = generate_random(randint(6, 12))
        token = gen_token(tkey)
        try:
            pipe: Pipeline = g.rc.pipeline()
            if oldToken:
                pipe.hdel(tk, oldToken)
            pipe.hset(tk, token, usr).hset(ak, "token", token).hset(
                ak, "token_key", tkey
            )
            pipe.execute()
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            res.update(code=0, token=token)
    return res


@bp.route("/myself", methods=["PUT", "POST"])
@apilogin_required
def my():
    res = dict(code=1, msg=None)
    username = g.userinfo.username
    ak = rsp("account", username)
    Action = request.args.get("Action")
    if Action == "updateProfile":
        #: 基于资料本身进行的统一更新
        allowed_fields = ["nickname", "avatar", "email"]
        data = {
            k: v.strip()
            for k, v in iteritems(request.form.to_dict())
            if k in allowed_fields
        }
        data.update(mtime=get_current_timestamp())
        if (
            is_true(g.userinfo.email_verified)
            and data.get("email") != g.userinfo.email
        ):
            data["email_verified"] = 0
        try:
            pipe: Pipeline = g.rc.pipeline()
            for k, v in iteritems(data):
                pipe.hset(ak, k, v)
            pipe.execute()
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            res.update(code=0)
            #: 更新资料触发一次钩子
            g.hm.call("profile_update", _kwargs=data)
    elif Action == "updatePassword":
        passwd = request.form.get("passwd")
        repasswd = request.form.get("repasswd")
        if passwd and repasswd:
            if len(passwd) < 6:
                res.update(msg="Password must be at least 6 characters")
            else:
                if passwd != repasswd:
                    res.update(msg="Confirm passwords do not match")
                else:
                    try:
                        g.rc.hset(
                            ak,
                            "password",
                            generate_password_hash(passwd),
                        )
                    except RedisError:
                        res.update(msg="Program data storage service error")
                    else:
                        res.update(code=0)
        else:
            res.update(msg="Parameter error")
    elif Action == "updateUserCfg":
        #: 更新用户设置，为避免覆盖ak字段，所有更新的key必须`ucfg_`开头
        cfgs = request.form.to_dict()
        if cfgs:
            for k in cfgs:
                if not k.startswith("ucfg_"):
                    res.update(msg="The user setting must start with `ucfg_`")
                    return res
            try:
                pipe: Pipeline = g.rc.pipeline()
                for k, v in iteritems(cfgs):
                    if isinstance(v, str):
                        v = v.strip()
                    pipe.hset(ak, k, v)
                pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0)
    elif Action in ("leaveMessage", "againMessage"):
        message = request.form.get("message")
        if message:
            pipe = g.rc.pipeline()
            if Action == "againMessage":
                if g.userinfo.status != -2:
                    res.update(
                        msg="Current state prohibits use of this method"
                    )
                    return res
                pipe.hset(ak, "status", -1)
            pipe.hset(ak, "message", message)
            try:
                pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0)
    elif Action == "verifyEmail":
        html = make_email_tpl(
            "activate_email.html",
            activate_url=url_for(
                "front.activate",
                token=generate_activate_token(
                    dict(
                        Action=Action,
                        username=username,
                        email=g.userinfo.email,
                    )
                ),
                _external=True,
            ),
        )
        res = sendmail(
            subject="{}邮箱验证".format(g.site_name),
            message=html,
            to=g.userinfo.email,
        )
    elif Action == "deleteAccount":
        #: 检测用户是否存在图片数据
        uk = rsp("index", "user", username)
        pics = g.rc.scard(uk)
        if pics > 0:
            raise ApiError("Users also have pictures that cannot be deleted")
        #: 删除用户相关数据
        pipe = g.rc.pipeline()
        pipe.srem(rsp("accounts"), username)
        pipe.delete(ak)
        # 删除linktoken
        lk = rsp("linktokens")
        for ltid, usr in iteritems(g.rc.hgetall(lk)):
            if usr == username:
                pipe.hdel(lk, ltid)
                pipe.delete(rsp("linktoken", ltid))
        # 删除统计
        pipe.delete(rsp("report", "linktokens", username))
        try:
            pipe.execute()
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            res.update(code=0)
    return res


@bp.route("/waterfall", methods=["GET", "POST"])
@apilogin_required
def waterfall():
    res = dict(code=1, msg=None)
    #: 依次根据ctime、filename排序
    sort = request.args.get("sort") or "desc"
    #: 符合人类习惯的page，第一页是1（程序计算需要减1）
    page = request.args.get("page") or 1
    #: 返回数据条数
    limit = request.args.get("limit") or 10
    #: 管理员账号读取所有图片数据
    is_mgr = is_true(request.args.get("is_mgr"))
    #: 相册，当album不为空时，近返回此相册数据，允许逗号分隔多个
    album = request.args.get("album", request.form.get("album"))
    try:
        page = int(page) - 1
        limit = int(limit)
        if page < 0:
            raise ValueError
    except (ValueError, TypeError):
        res.update(code=2, msg="Parameter error")
    else:
        if g.userinfo.username:
            if is_mgr and g.is_admin:
                uk = rsp("index", "global")
            else:
                uk = rsp("index", "user", g.userinfo.username)
            pipe = g.rc.pipeline()
            for sha in g.rc.smembers(uk):
                pipe.hgetall(rsp("image", sha))
            try:
                result = pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                #: 最终返回的经过过滤、排序等处理后的数据
                data = []
                #: 该用户或管理员级别所能查看的所有相册
                albums = []
                ask_albums = parse_valid_comma(album)
                if result and isinstance(result, (tuple, list)):
                    for i in result:
                        if not i or not isinstance(i, dict):
                            continue
                        albums.append(i.get("album"))
                        i.update(
                            senders=json.loads(i["senders"]),
                            ctime=int(i["ctime"]),
                            is_video=is_true(i.get("is_video")),
                            tpl=gen_url_tpl(i),
                        )
                        if ask_albums:
                            if i.get("album") in ask_albums:
                                data.append(i)
                        else:
                            data.append(i)
                data = sorted(
                    data,
                    key=lambda k: (k.get("ctime", 0), k.get("filename", "")),
                    reverse=False if sort == "asc" else True,
                )
                count = len(data)
                data = list_equal_split(data, limit)
                pageCount = len(data)
                if page < pageCount:
                    res.update(
                        code=0,
                        count=count,
                        data=data[page],
                        pageCount=pageCount,
                        albums=list(set([i for i in albums if i])),
                    )
                else:
                    res.update(code=3, msg="No data")
        else:
            res.update(msg="No valid username found")
    return res


@bp.route("/sha/<sha>", methods=["GET", "DELETE", "PUT", "POST"])
def shamgr(sha):
    """图片查询、删除接口"""
    res = dict(code=1, msg=None)
    gk = rsp("index", "global")
    ik = rsp("image", sha)
    if request.method == "GET":
        if has_image(sha):
            data = g.rc.hgetall(ik)
            data.update(
                senders=json.loads(data["senders"]) if g.is_admin else None,
                ctime=int(data["ctime"]),
                tpl=gen_url_tpl(data),
                is_video=is_true(data.get("is_video")),
            )
            res.update(code=0, data=data)
        else:
            return abort(404)
    elif request.method == "DELETE":
        if not g.signin:
            return abort(403)
        if has_image(sha):
            #: 图片所属用户
            #: - 如果不是匿名，那么判断请求用户是否属所属用户或管理员
            #: - 如果是匿名上传，那么只有管理员有权删除
            info = g.rc.hgetall(ik)
            husr = info.get("user")
            if g.is_admin or (g.userinfo.username == husr):
                pipe = g.rc.pipeline()
                pipe.srem(gk, sha)
                pipe.srem(rsp("index", "user", husr), sha)
                pipe.delete(ik)
                try:
                    pipe.execute()
                except RedisError:
                    res.update(msg="Program data storage service error")
                else:
                    res.update(code=0)
                    try:
                        #: 删除图片尝试执行senders的upimg_delete方法
                        #: 后端钩子未禁用时才会执行删除
                        #: TODO 无论禁用与否都删除?
                        senders = json.loads(info.get("senders"))
                        for i in senders:
                            g.hm.proxy(i["sender"]).upimg_delete(
                                sha=sha,
                                upload_path=info["upload_path"],
                                filename=info["filename"],
                                basedir=i.get("basedir"),
                                save_result=i,
                            )
                    except (ValueError, AttributeError, Exception) as e:
                        logger.warning(e, exc_info=True)
            else:
                return abort(403)
        else:
            return abort(404)
    elif request.method == "PUT":
        Action = request.args.get("Action") or request.form.get("Action")
        if Action == "updateAlbum":
            if not g.signin:
                return abort(403)
            if not has_image(sha):
                return abort(404)
            #: 更改相册名，允许图片所属用户或管理员修改，允许置空
            album = request.form.get("album") or ""
            owner = g.rc.hget(ik, "user")
            if g.userinfo.username == owner or g.is_admin:
                try:
                    g.rc.hset(ik, "album", album.strip())
                except RedisError:
                    res.update(msg="Program data storage service error")
                else:
                    res.update(code=0)
            else:
                return abort(403)
    elif request.method == "POST":
        Action = request.args.get("Action") or request.form.get("Action")
        if Action == "overrideUpload":
            if not g.signin:
                return abort(403)
            if not has_image(sha):
                return abort(404)
            data = g.rc.hgetall(ik)
            #: 限制只有图片所属用户可以覆盖上传
            if g.userinfo.username != data["user"]:
                return abort(403)
            sender = data["sender"]
            proxy = g.hm.proxy(sender)
            if proxy:
                fp = request.files.get(g.cfg.upload_field or "picbed")
                if fp and allowed_suffix(fp.filename):
                    stream = fp.stream.read()
                    res = proxy.upimg_save(
                        filename=data["filename"],
                        stream=stream,
                        upload_path=data["upload_path"],
                    )
                    if res["code"] == 0:
                        pipe: Pipeline = g.rc.pipeline()
                        pipe.hset(ik, "mtime", get_current_timestamp()).hset(
                            ik, "senders", json.dumps([res])
                        ).hset(
                            ik,
                            "origin",
                            request.form.get(
                                "origin",
                                "UA: %s"
                                % request.headers.get("User-Agent", ""),
                            ),
                        )
                else:
                    res.update(msg="No file or image format error")
            else:
                res.update(msg="The upload hook does not exist or is disabled")
    else:
        return abort(405)
    return res


@bp.route("/upload", methods=["POST"])
def upload():
    """上传逻辑：
    0. 判断是否登录，如果未登录则判断是否允许匿名上传
    1. 获取上传的文件，判断允许格式
        - 拦截下判断文件，如果为空，尝试获取body中提交的picbed
        - 如果picbed是合法base64，那么会返回Base64FileStorage类；
            如果是合法url，服务端则会自动下载，返回ImgUrlFileStorage类；否则为空。
            PS: 允许DATA URI形式, eg: data:image/png;base64,the base64 of image
    2. 生成文件名、唯一sha值、上传目录等，选择图片存储的后端钩子（单一）
        - 存储图片的钩子目前版本仅一个，默认是up2local（如果禁用则保存失败）
        - 如果提交album参数会自动创建相册，否则归档到默认相册
    3. 解析钩子数据，钩子回调数据格式：{code=?, sender=hook_name, src=?}
        - 后端保存失败或无后端的情况都要立刻返回响应
    4. 此时保存图片成功，持久化存储到全局索引、用户索引
    5. 返回响应：{code:0, data={src=?, sender=success_saved_hook_name}}
        - 允许使用一些参数调整响应数据、格式
    """
    res = dict(code=1, msg=None)
    #: 文件域或base64上传字段
    FIELD_NAME = (
        g.cfg.upload_field or request.form.get("_upload_field") or "picbed"
    )
    #: 匿名上传开关检测
    if not is_true(g.cfg.anonymous) and not g.signin:
        raise ApiError("Anonymous user is not sign in", 403)
    #: 判断已登录用户是否待审核
    if g.signin and g.userinfo.status in (-2, -1, 0):
        msg = (
            "Pending review, cannot upload pictures"
            if g.userinfo.status in (-2, -1)
            else "The user is disabled, no operation"
        )
        raise ApiError(msg, 403)
    #: 相册名称，可以是任意字符串
    album = (
        (
            request.form.get("album")
            or getattr(g, "up_album", g.userinfo.ucfg_default_upload_album)
            or ""
        )
        if g.signin
        else "anonymous"
    )
    #: 图片过期（单位：秒）
    try:
        expire = int(request.form.get("expire", 0))
        if expire < 0:
            raise ValueError
    except (ValueError, TypeError):
        raise ApiError("Invalid expire param")
    #: 尝试读取上传数据
    fp = request.files.get(FIELD_NAME)
    #: 当fp无效时尝试读取base64或url
    if fp:
        fp = FormFileStorage(fp)
    else:
        picstrurl = request.form.get(FIELD_NAME)
        filename = secure_filename(request.form.get("filename") or "")
        if picstrurl:
            if picstrurl.startswith("http://") or picstrurl.startswith(
                "https://"
            ):
                fp = ImgUrlFileStorage(picstrurl, filename).getObj
            else:
                try:
                    #: base64在部分场景发起http请求时，+可能会换成空格导致异常
                    fp = Base64FileStorage(picstrurl, filename)
                except ValueError as e:
                    raise ApiError(e)
    if fp and allowed_suffix(fp.filename):
        size = fp.size
        if size and size > up_size_limit():
            raise ApiError("the uploaded file exceeds the limit", 413)
        stream = fp.stream.read()
        suffix = splitext(fp.filename)[-1]
        is_video = 1 if allowed_file(fp.filename, ALLOWED_VIDEO) else 0
        #: 处理图片二进制的钩子
        if not is_video:
            for h in g.hm.get_call_list(
                "upimg_stream_processor", _type="func"
            ):
                rst = g.hm.proxy(h["name"]).upimg_stream_processor(
                    stream, suffix
                )
                if (
                    isinstance(rst, dict)
                    and rst.get("code") == 0
                    and isinstance(rst.get("data"), dict)
                    and "stream" in rst["data"]
                ):
                    stream = rst["data"]["stream"]
                    # 当处理后stream类型发生变化时，
                    # 如jpg格式转为webp格式，更新后缀
                    if rst.get("suffix") and rst["suffix"] != suffix:
                        suffix = rst["suffix"]
            for h in g.hm.call(
                "upimg_stream_interceptor",
                _args=(stream, suffix),
                _mode="any_false",
            ):
                if h.get("code") != 0:
                    res.update(
                        msg="Interceptor processing rejection, upload aborted",
                        errors={h["sender"]: h.get("msg")},
                    )
                    return res
        #: 定义图片文件名
        filename = secure_filename(fp.filename)
        origin_suffix = splitext(filename)[-1]
        if "." not in filename:
            filename = "%s%s" % (generate_random(8), suffix)
        elif suffix != origin_suffix:
            # 钩子处理后stream类型可能变化，更新suffix
            filename = "%s%s" % (filename[: -len(origin_suffix)], suffix)

        #: 根据文件名规则重定义图片名
        upload_file_rule = (
            (g.userinfo.ucfg_upload_file_rule or g.cfg.upload_file_rule)
            if is_true(g.cfg.upload_rule_overridden)
            else g.cfg.upload_file_rule
        )
        if upload_file_rule in ("time1", "time2", "time3"):
            filename = "%s%s" % (gen_rnd_filename(upload_file_rule), suffix)
        #: 上传文件位置前缀规则
        upload_path_rule = (
            (g.userinfo.ucfg_upload_path_rule or g.cfg.upload_path_rule)
            if is_true(g.cfg.upload_rule_overridden)
            else g.cfg.upload_path_rule
        )
        if upload_path_rule == "date1":
            upload_path = get_today("%Y/%m/%d")
        elif upload_path_rule == "date2":
            upload_path = get_today("%Y%m%d")
        else:
            upload_path = ""
        upload_path = join(g.userinfo.username or "anonymous", upload_path)
        #: 定义文件名唯一索引
        sha = "sha1.%s.%s" % (get_current_timestamp(True), sha1(filename))
        #: 定义保存图片时仅使用某些钩子，如: up2local
        #: TODO 目前版本仅允许设置了一个，后续聚合
        includes = parse_valid_comma(g.cfg.upload_includes or "up2local")
        if len(includes) > 1:
            includes = [choice(includes)]
        #: 当用户有标签且定义了用户上传分组则尝试覆盖默认includes
        up_grp = g.cfg.upload_group
        up_grp_rule = parse_valid_colon(up_grp) or {}
        if g.signin:
            usr_label = g.userinfo.label
            if up_grp_rule and usr_label:
                for label in usr_label:
                    if label in up_grp_rule:
                        includes = [up_grp_rule[label]]
                        break
            #: 按照上传标签限制用户上传数量 小于0直接禁止上传 0不限制 大于0即为限制数量
            up_limit_rule = parse_valid_colon(g.cfg.upload_limit) or {}
            if up_limit_rule and usr_label:
                #: TODO Fix homepage 多线程并发上传数量读取错误（读完但未写入redis）
                usr_current_upsize = g.rc.scard(
                    rsp("index", "user", g.userinfo.username)
                )
                for label in usr_label:
                    if label in up_limit_rule:
                        #: 进入此处表明用户存在标签被限制
                        limit_num = up_limit_rule[label]
                        try:
                            limit_num = int(limit_num)
                        except (ValueError, TypeError):
                            pass
                        else:
                            if limit_num < 0:
                                raise ApiError("User uploads are limited")
                            elif limit_num > 0:
                                if usr_current_upsize >= limit_num:
                                    raise ApiError("User uploads are limited")
        else:
            if up_grp:
                includes = [up_grp_rule["anonymous"]]
        #: TODO 定义保存图片时排除某些钩子，如: up2local, up2other
        #: excludes = parse_valid_comma(g.cfg.upload_excludes or '')
        #: 调用钩子中upimg_save方法（目前版本最终结果中应该最多只有1条数据）
        data = g.hm.call(
            _funcname="upimg_save",
            _include=includes,
            _kwargs=dict(
                filename=filename,
                stream=stream,
                upload_path=upload_path,
            ),
        )
        #: 判定后端存储全部失败时，上传失败
        if not data:
            raise ApiError("No valid backend storage service")
        if is_all_fail(data):
            res.update(
                code=1,
                msg="All backend storage services failed to save pictures",
                errors={
                    i["sender"]: i["msg"] for i in data if i.get("code") != 0
                },
            )
            return res
        #: 存储数据
        defaultSrc = data[0]["src"]
        meta = dict(
            sha=sha,
            album=album.strip(),
            filename=filename,
            upload_path=upload_path,
            user=g.userinfo.username if g.signin else "anonymous",
            ctime=get_current_timestamp(),
            status="enabled",  # deleted
            src=defaultSrc,
            sender=data[0]["sender"],
            senders=json.dumps(data),
            origin=request.form.get(
                "origin", "UA: %s" % request.headers.get("User-Agent", "")
            ),
            method=get_upload_method(fp.__class__.__name__),
            title=request.form.get("title") or "",
            is_video=is_video,
        )
        pipe: Pipeline = g.rc.pipeline()
        pipe.sadd(rsp("index", "global"), sha)
        if g.signin and g.userinfo.username:
            pipe.sadd(rsp("index", "user", g.userinfo.username), sha)
        for k, v in iteritems(meta):
            pipe.hset(rsp("image", sha), k, v)
        if expire > 0:
            pipe.expire(rsp("image", sha), expire)
        try:
            pipe.execute()
        except RedisError as e:
            logger.error(e, exc_info=True)
            res.update(code=3, msg="Program data storage service error")
        else:
            res.update(
                code=0,
                filename=filename,
                sender=meta["sender"],
                api=url_for("api.shamgr", sha=sha, _external=True),
                sha=sha,
                tpl=gen_url_tpl(meta),
                is_video=is_video == 1,
            )
            #: format指定图片地址的显示字段，默认src，可以用点号指定
            #: 比如data.src，那么返回格式{code, filename..., data:{src}, ...}
            #: 比如imgUrl，那么返回格式{code, filename..., imgUrl(=src), ...}
            fmt = request.form.get("format", request.args.get("format"))
            res.update(format_upload_src(fmt, defaultSrc))
    else:
        res.update(msg="No file or image format error")
    return res


@bp.route("/extendpoint", methods=["POST"])
def ep():
    """专用于钩子扩展API方法"""
    #: TODO 接口随意可访问扩展内方法，存在安全风险
    Object = request.args.get("Object")
    Action = request.args.get("Action")
    if Object and Action:
        obj = g.hm.proxy(Object)
        if obj and hasattr(obj, Action):
            return getattr(obj, Action)()
    return abort(404)


@bp.route("/album", methods=["GET", "POST"])
@apilogin_required
def album():
    res = dict(code=1, msg=None)
    #: 管理员账号查询所有相册
    is_mgr = is_true(request.args.get("is_mgr"))
    if g.userinfo.username:
        if is_mgr and g.is_admin:
            uk = rsp("index", "global")
        else:
            uk = rsp("index", "user", g.userinfo.username)
        pipe = g.rc.pipeline()
        for sha in g.rc.smembers(uk):
            pipe.hget(rsp("image", sha), "album")
        try:
            result = pipe.execute()
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            albums = [i for i in result if i]
            res.update(code=0, data=list(set(albums)), counter=Counter(albums))
    else:
        res.update(msg="No valid username found")
    return res


@bp.route("/link", methods=["GET", "POST", "PUT", "DELETE"])
@apilogin_required
def link():
    res = dict(code=1, msg=None)
    ltk = rsp("linktokens")
    username = g.userinfo.username

    def check_body():
        """校验post、put参数，返回值有效说明校验不通过"""
        allow_origin = request.form.get("allow_origin")
        allow_ip = request.form.get("allow_ip")
        allow_ep = request.form.get("allow_ep")
        allow_method = request.form.get("allow_method")
        er = request.form.get("exterior_relation")
        ir = request.form.get("interior_relation")
        if allow_origin:
            origins = parse_valid_comma(allow_origin)
            if not origins or not isinstance(origins, (tuple, list)):
                return "Invalid url address"
            for url in origins:
                if url and not check_origin(url):
                    return "Invalid url address"
        if allow_ip:
            ips = parse_valid_comma(allow_ip)
            if not ips or not isinstance(ips, (tuple, list)):
                return "Invalid IP address"
            for ip in ips:
                if ip and not check_ip(ip):
                    return "Invalid IP address"
        if allow_ep:
            eps = parse_valid_comma(allow_ep)
            if not eps or not isinstance(eps, (tuple, list)):
                return "Not found the endpoint"
            for ep in eps:
                if ep and ep not in current_app.view_functions.keys():
                    return "Not found the endpoint"
        if allow_method:
            methods = parse_valid_comma(allow_method)
            if not methods or not isinstance(methods, (tuple, list)):
                return "Invalid HTTP method"
            for md in methods:
                if md and md.upper() not in ALLOWED_HTTP_METHOD:
                    return "Invalid HTTP method"
        if er:
            if not er_pat.match(er.strip()):
                return "Invalid exterior_relation"
        if ir:
            if not ir_pat.match(ir.strip()):
                return "Invalid interior_relation"
            else:
                try:
                    check_ir(ir)
                except (ValueError, TypeError):
                    return "Invalid interior_relation"

    if request.method == "GET":
        is_mgr = is_true(request.args.get("is_mgr"))
        linktokens = g.rc.hgetall(ltk)
        pipe = g.rc.pipeline()
        for ltid, usr in iteritems(linktokens):
            if is_mgr and g.is_admin:
                pipe.hgetall(rsp("linktoken", ltid))
            else:
                if username == usr:
                    pipe.hgetall(rsp("linktoken", ltid))
        try:
            result = pipe.execute()
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            res.update(code=0, data=result, count=len(result))

    elif request.method == "POST":
        comment = request.form.get("comment") or ""
        #: 定义此引用上传图片时默认设置的相册名
        album = request.form.get("album") or ""
        #: 定义以下几个权限之间的允许访问条件，opt and/or/not opt
        er = request.form.get("exterior_relation", "").strip()
        #: 定义权限内部允许访问条件 in/not in:opt,
        ir = request.form.get("interior_relation", "").strip()
        #: 定义权限项及默认值，检测参数时不包含默认值
        allow_origin = request.form.get("allow_origin") or ""
        allow_ip = request.form.get("allow_ip") or ""
        allow_ep = request.form.get("allow_ep") or "api.upload"
        allow_method = request.form.get("allow_method") or "post"
        #: 判断用户是否有token
        ak = rsp("account", username)
        if not g.rc.hget(ak, "token"):
            res.update(msg="No token yet")
            return res
        cv = check_body()
        if cv:
            res.update(msg=cv)
            return res
        if allow_origin:
            allow_origin = ",".join(
                [
                    get_origin(url)
                    for url in parse_valid_comma(allow_origin)
                    if url
                ]
            )
        #: 生成一个引用
        LinkId = gen_uuid()
        LinkSecret = generate_password_hash(LinkId)
        lid = "%s:%s:%s" % (
            get_current_timestamp(),
            LinkId,
            hmac_sha256(LinkId, LinkSecret),
        )
        LinkToken = b64encode(lid.encode("utf-8")).decode("utf-8")
        pipe: Pipeline = g.rc.pipeline()
        pipe.hset(ltk, LinkId, username)
        for k, v in iteritems(
            dict(
                LinkId=LinkId,
                LinkSecret=LinkSecret,
                LinkToken=LinkToken,
                ctime=get_current_timestamp(),
                user=username,
                comment=comment,
                album=album.strip(),
                status=1,  # 状态，1是启用，0是禁用
                allow_origin=allow_origin,
                allow_ip=allow_ip,
                allow_ep=allow_ep,
                allow_method=allow_method,
                exterior_relation=er,
                interior_relation=ir,
            )
        ):
            pipe.hset(rsp("linktoken", LinkId), k, v)
        try:
            pipe.execute()
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            res.update(code=0, LinkToken=LinkToken)

    elif request.method == "PUT":
        LinkId = request.form.get("LinkId")
        Action = request.args.get("Action")
        key = rsp("linktoken", LinkId)
        if Action == "disable":
            try:
                g.rc.hset(key, "status", 0)
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0)
            return res
        elif Action == "enable":
            try:
                g.rc.hset(key, "status", 1)
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0)
            return res
        if LinkId and g.rc.exists(key):
            comment = request.form.get("comment") or ""
            album = request.form.get("album") or ""
            er = request.form.get("exterior_relation", "").strip()
            ir = request.form.get("interior_relation", "").strip()
            allow_origin = request.form.get("allow_origin") or ""
            allow_ip = request.form.get("allow_ip") or ""
            allow_ep = request.form.get("allow_ep") or "api.upload"
            allow_method = request.form.get("allow_method") or "post"
            cv = check_body()
            if cv:
                res.update(msg=cv)
                return res
            if allow_origin:
                allow_origin = ",".join(
                    [
                        get_origin(url)
                        for url in parse_valid_comma(allow_origin)
                        if url
                    ]
                )
            pipe: Pipeline = g.rc.pipeline()
            pipe.hset(ltk, LinkId, username)
            for k, v in iteritems(
                dict(
                    mtime=get_current_timestamp(),
                    comment=comment,
                    album=album,
                    allow_origin=allow_origin,
                    allow_ip=allow_ip,
                    allow_ep=allow_ep,
                    allow_method=allow_method,
                    exterior_relation=er,
                    interior_relation=ir,
                )
            ):
                pipe.hset(key, k, v)
            try:
                pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0)
        else:
            res.update(msg="Not found the LinkId")

    elif request.method == "DELETE":
        LinkId = request.form.get("LinkId")
        if LinkId:
            pipe = g.rc.pipeline()
            pipe.hdel(ltk, LinkId)
            pipe.delete(rsp("linktoken", LinkId))
            try:
                pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0)
        else:
            res.update(msg="Parameter error")

    return res


@bp.route("/report/<classify>")
@apilogin_required
def report(classify):
    res = dict(code=1, msg=None)
    start = request.args.get("start")
    end = request.args.get("end")
    page = request.args.get("page")
    limit = request.args.get("limit")
    sort = (request.args.get("sort") or "asc").upper()
    if classify in ("linktokens",):
        try:
            #: start、end可正可负
            start = int(start)
            end = int(end)
        except (ValueError, TypeError):
            try:
                page = int(page)
                limit = int(limit or 10)
                if page - 1 < 0:
                    raise ValueError
            except (ValueError, TypeError):
                res.update(msg="Parameter error")
                return res
            else:
                start = (page - 1) * limit
                end = start + limit - 1
        if isinstance(start, int) and isinstance(end, int):
            key = rsp("report", classify, g.userinfo.username)
            try:
                pipe = g.rc.pipeline()
                pipe.llen(key)
                pipe.lrange(key, start, end)
                result = pipe.execute()
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                count, data = result
                if sort == "DESC":
                    data.reverse()
                res.update(
                    code=0,
                    data=[json.loads(r) for r in data if r],
                    count=count,
                )
        else:
            res.update(msg="Wrong query range parameter")
    else:
        return abort(404)
    return res


@bp.route("/load", methods=["POST"])
@apilogin_required
def load():
    """把图片/视频导入系统"""
    res = dict(code=1)
    #: 应该提交JSON数据，是一个数组，元素是字典对象
    #: 其字段必须有url，建议filename，可选title、album
    data = request.json
    if data and isinstance(data, list):
        fail = []
        todo = []
        #: 筛选
        for img in data:
            if img and isinstance(img, dict) and check_url(img.get("url")):
                filename = secure_filename(
                    img.get("filename")
                    or guess_filename_from_url(img["url"])
                    or ""
                )
                if allowed_suffix(filename):
                    img["filename"] = filename
                    todo.append(img)
                    continue
            fail.append(img)
        #: 处理
        pipe: Pipeline = g.rc.pipeline()
        success = []
        for img in todo:
            filename = img["filename"]
            #: 定义文件名唯一索引
            sha = "sha1.%s.%s" % (get_current_timestamp(True), sha1(filename))
            #: 入库
            pipe.sadd(rsp("index", "global"), sha)
            pipe.sadd(rsp("index", "user", g.userinfo.username), sha)
            for k, v in iteritems(
                dict(
                    sha=sha,
                    album=img.get("album") or "",
                    filename=filename,
                    upload_path=g.userinfo.username + "/",
                    user=g.userinfo.username,
                    ctime=get_current_timestamp(),
                    status="enabled",
                    src=img["url"],
                    sender="load",
                    senders=json.dumps([]),
                    origin=request.form.get(
                        "origin",
                        "UA: %s" % request.headers.get("User-Agent", ""),
                    ),
                    method="load",
                    title=img.get("title") or "",
                    is_video=1 if allowed_file(filename, ALLOWED_VIDEO) else 0,
                )
            ):
                pipe.hset(rsp("image", sha), k, v)
            try:
                pipe.execute()
            except RedisError:
                fail.append(img)
            else:
                img["sha"] = sha
                success.append(img)
        res.update(
            code=0,
            success=success,
            fail=fail,
            count=dict(success=len(success), fail=len(fail)),
        )
    else:
        res.update(msg="Parameter error")
    return res
