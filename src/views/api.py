# -*- coding: utf-8 -*-
"""
    views.api
    ~~~~~~~~~

    Api view functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import json
from random import choice
from os.path import join, splitext
from base64 import urlsafe_b64encode as b64encode
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from flask import Blueprint, request, g, url_for, current_app, abort, \
    make_response, jsonify, Response
from functools import partial
from redis.exceptions import RedisError
from collections import Counter
from utils.tool import allowed_file, parse_valid_comma, is_true, logger, sha1,\
    parse_valid_verticaline, get_today, gen_rnd_filename, hmac_sha256, \
    rsp, get_current_timestamp, ListEqualSplit, sha256, generate_random, \
    err_logger, format_upload_src
from utils.web import dfr, admin_apilogin_required, apilogin_required, \
    set_site_config, check_username
from utils._compat import iteritems

bp = Blueprint("api", "api")
#: 定义本地上传的钩子在保存图片时的基础目录前缀（在static子目录下）
UPLOAD_FOLDER = "upload"


@bp.errorhandler(500)
@bp.errorhandler(404)
@bp.errorhandler(403)
@bp.errorhandler(413)
def api_error(e):
    if getattr(e, "code", None) == 500:
        err_logger.error(e, exc_info=True)
    return jsonify(dict(
        msg=e.name,
        code=e.code
    )), e.code


@bp.after_request
def translate(res):
    if res.is_json:
        data = res.get_json()
        if isinstance(data, dict):
            res.set_data(json.dumps(dfr(data)))
    return res


@bp.route("/")
def index():
    return "Hello picbed."


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return abort(404)
    res = dict(code=1)
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
            so = current_app.extensions["hookmanager"].proxy(g.cfg.site_auth)
            if so and hasattr(so, "login_api"):
                result = so.login_api(usr, pwd, set_state, max_age, is_secure)
                if result and isinstance(result, Response):
                    return result
    except (ValueError, TypeError, Exception) as e:
        logger.warning(e, exc_info=True)
    if usr and pwd and check_username(usr) and len(pwd) >= 6:
        ak = rsp("accounts")
        if g.rc.sismember(ak, usr):
            userinfo = g.rc.hgetall(rsp("account", usr))
            if is_true(g.cfg.disable_login) and \
                    not is_true(userinfo.get("is_admin")):
                res.update(msg="Normal user login has been disabled")
                return res
            password = userinfo.get("password")
            if password and check_password_hash(password, pwd):
                expire = get_current_timestamp() + max_age
                sid = "%s.%s.%s" % (
                    usr,
                    expire,
                    sha256("%s:%s:%s:%s" % (
                        usr, password, expire, current_app.config["SECRET_KEY"]
                    ))
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
                        secure=is_secure
                    )
            else:
                res.update(msg="Password verification failed")
        else:
            res.update(msg="No valid username found")
    else:
        res.update(msg="The username or password parameter error")
    return res


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET" or is_true(g.cfg.register) is False:
        return abort(404)
    res = dict(code=1)
    #: Required fields
    username = request.form.get("username")
    password = request.form.get("password")
    if username and password:
        if check_username(username):
            if len(password) < 6:
                res.update(msg="Password must be at least 6 characters")
            else:
                ak = rsp("accounts")
                if g.rc.sismember(ak, username):
                    res.update(msg="The username already exists")
                else:
                    #: 参数校验通过，执行注册
                    options = dict(
                        username=username,
                        password=generate_password_hash(password),
                        is_admin=0,
                        avatar=request.form.get("avatar") or "",
                        nickname=request.form.get("nickname") or "",
                        ctime=get_current_timestamp(),
                    )
                    uk = rsp("account", username)
                    pipe = g.rc.pipeline()
                    pipe.sadd(ak, username)
                    pipe.hmset(uk, options)
                    try:
                        pipe.execute()
                    except RedisError:
                        res.update(msg="Program data storage service error")
                    else:
                        res.update(code=0)
        else:
            res.update(
                msg="The username is invalid or registration is not allowed"
            )
    return res


@bp.route("/config", methods=["GET", "POST"])
@admin_apilogin_required
def config():
    if request.method == "GET":
        return abort(404)
    try:
        set_site_config(request.form.to_dict())
    except Exception as e:
        logger.error(e, exc_info=True)
        return dict(code=1, msg="An unknown error occurred in the program")
    else:
        return dict(code=0)


@bp.route("/hook", methods=["GET", "POST"])
@admin_apilogin_required
def hook():
    if request.method == "GET":
        return abort(404)
    res = dict(code=1, msg=None)
    Action = request.args.get("Action")
    hm = current_app.extensions["hookmanager"]
    if Action == "query":
        hooks = hm.get_all_hooks
        data = [
            dict(
                name=h.name,
                description=h.description,
                version=h.version,
                author=h.author,
                catalog=h.catalog,
                state=h.state,
                ltime=h.time,
                mtime=h.proxy.__mtime__,
                family=h.proxy.__family__,
            )
            for h in hooks
        ]
        res.update(code=0, data=data, count=len(data))
    elif Action == 'disable':
        name = request.form.get("name")
        try:
            hm.disable(name)
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    elif Action == 'enable':
        name = request.form.get("name")
        try:
            hm.enable(name)
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    elif Action == 'reload':
        try:
            hm.reload()
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    elif Action == 'add_third_hook':
        name = request.form.get("name")
        try:
            __import__(name)
            hm.add_third_hook(name)
        except ImportError:
            res.update(msg="The third module not found")
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    elif Action == 'remove_third_hook':
        name = request.form.get("name")
        try:
            hm.remove_third_hook(name)
        except:
            res.update(msg="An unknown error occurred in the program")
        else:
            res.update(code=0)
    return res


@bp.route("/token", methods=["GET", "POST"])
@apilogin_required
def token():
    if request.method == "GET":
        return abort(404)
    res = dict(code=1)
    usr = g.userinfo.username
    tk = rsp("tokens")
    ak = rsp("account", usr)
    #: 生成token

    def gen_token(): return b64encode(
        ("%s.%s.%s.%s" % (
            generate_random(),
            usr,
            get_current_timestamp(),
            hmac_sha256(g.rc.hget(ak, "password"), usr)
        )).encode("utf-8")
    ).decode("utf-8")
    Action = request.args.get("Action")
    if Action == "create":
        if g.rc.hget(ak, "token"):
            res.update(msg="Existing token")
        else:
            token = gen_token()
            try:
                pipe = g.rc.pipeline()
                pipe.hset(tk, token, usr)
                pipe.hset(ak, "token", token)
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
            res.update(msg="No tokens yet")
    elif Action == "reset":
        oldToken = g.rc.hget(ak, "token")
        token = gen_token()
        try:
            pipe = g.rc.pipeline()
            if oldToken:
                pipe.hdel(tk, oldToken)
            pipe.hset(tk, token, usr)
            pipe.hset(ak, "token", token)
            pipe.execute()
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            res.update(code=0, token=token)
    return res


@bp.route("/myself", methods=["GET", "PUT"])
@apilogin_required
def my():
    if request.method == "GET":
        return abort(404)
    res = dict(code=1)
    ak = rsp("account", g.userinfo.username)
    Action = request.args.get("Action")
    if Action == "updateProfile":
        allowed_fields = ["nickname", "avatar"]
        data = {
            k: v
            for k, v in iteritems(request.form.to_dict())
            if k in allowed_fields
        }
        try:
            data.update(mtime=get_current_timestamp())
            g.rc.hmset(ak, data)
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            res.update(code=0)
            #: 更新资料触发一次钩子
            current_app.extensions["hookmanager"].call(
                "profile_update", **data
            )
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
                        g.rc.hmset(ak, dict(
                            password=generate_password_hash(passwd),
                        ))
                    except RedisError:
                        res.update(msg="Program data storage service error")
                    else:
                        res.update(code=0)
        else:
            res.update(msg="Parameter error")
    return res


@bp.route("/waterfall", methods=["GET", "POST"])
@apilogin_required
def waterfall():
    if request.method == "GET":
        return abort(404)
    res = dict(code=1, msg=None)
    #: 依次根据ctime、filename排序
    sort = request.args.get("sort") or "desc"
    #: 符合人类习惯的page，第一页是1（程序计算需要减1）
    page = request.args.get("page") or 1
    #: 返回数据条数
    limit = request.args.get("limit") or 10
    #: 管理员账号读取所有图片数据
    is_mgr = is_true(request.args.get("is_mgr"))
    #: 相册，当album不为空时，近返回此相册数据
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
                if result and isinstance(result, (tuple, list)):
                    for i in result:
                        albums.append(i.get("album"))
                        i.update(
                            senders=json.loads(i["senders"]),
                            ctime=int(i["ctime"]),
                        )
                        if album:
                            if i.get("album") == album:
                                data.append(i)
                        else:
                            data.append(i)
                data = sorted(
                    data,
                    key=lambda k: (k.get('ctime', 0), k.get('filename', '')),
                    reverse=False if sort == "asc" else True
                )
                count = len(data)
                data = ListEqualSplit(data, limit)
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


@bp.route("/sha/<sha>", methods=["GET", "DELETE", "PUT"])
def shamgr(sha):
    """图片查询、删除接口"""
    res = dict(code=1)
    gk = rsp("index", "global")
    ik = rsp("image", sha)
    dk = rsp("index", "deleted")
    if request.method == "GET":
        if g.rc.sismember(gk, sha):
            data = g.rc.hgetall(ik)
            u, n = data["src"], data["filename"]
            data.update(
                senders=json.loads(data["senders"]) if g.is_admin else None,
                ctime=int(data["ctime"]),
                tpl=dict(
                    HTML="<img src='%s' alt='%s'>" % (u, n),
                    rST=".. image:: %s" % u,
                    Markdown="![%s](%s)" % (n, u)
                )
            )
            res.update(code=0, data=data)
        else:
            return abort(404)
    elif request.method == "DELETE":
        if not g.signin:
            return abort(403)
        if g.rc.sismember(gk, sha):
            #: 图片所属用户
            #: - 如果不是匿名，那么判断请求用户是否属所属用户或管理员
            #: - 如果是匿名上传，那么只有管理员有权删除
            info = g.rc.hgetall(ik)
            husr = info.get("user")
            if g.is_admin or (g.userinfo.username == husr):
                pipe = g.rc.pipeline()
                pipe.srem(gk, sha)
                pipe.sadd(dk, sha)
                pipe.hset(ik, "status", "deleted")
                pipe.srem(rsp("index", "user", husr), sha)
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
                            current_app.extensions["hookmanager"].proxy(
                                i["sender"]
                            ).upimg_delete(
                                sha=sha,
                                upload_path=info["upload_path"],
                                filename=info["filename"],
                                basedir=(join(
                                    current_app.root_path,
                                    current_app.static_folder,
                                    UPLOAD_FOLDER
                                ) if i["sender"] == "up2local"
                                    else i.get("basedir")),
                                save_result=i
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
            #: 更改相册名，允许图片所属用户或管理员修改，允许置空
            album = request.form.get("album")
            shaOwner = g.rc.hget(ik, "user")
            if g.userinfo.username == shaOwner or g.is_admin:
                try:
                    g.rc.hset(ik, "album", album)
                except RedisError:
                    res.update(msg="Program data storage service error")
                else:
                    res.update(code=0)
            else:
                res.update(msg="Illegal users are not allowed to modify")
    else:
        return abort(405)
    return res


@bp.route("/upload", methods=["POST"])
def upload():
    """上传逻辑：
    0. 判断是否登录，如果未登录则判断是否允许匿名上传
    1. 获取上传的文件，判断允许格式
    2. 生成文件名、唯一sha值、上传目录等，选择图片存储的后端钩子（单一）
        - 存储图片的钩子目前版本仅一个，默认是up2local（如果禁用则保存失败）
        - 如果提交album参数会自动创建相册，否则归档到默认相册
    3. 解析钩子数据，钩子回调数据格式：{code=?, sender=hook_name, src=?}
        - 后端保存失败或无后端的情况都要立刻返回响应
    4. 此时保存图片成功，持久化存储到全局索引、用户索引
    5. 返回响应：{code:0, data={src=?, sender=success_saved_hook_name}}
    """
    res = dict(code=1, msg=None)
    #: 匿名上传开关检测
    if not is_true(g.cfg.anonymous) and not g.signin:
        res.update(code=403, msg="Anonymous user is not sign in")
        return res
    f = request.files.get('picbed')
    #: 相册名称，可以是任意字符串
    album = (request.form.get("album") or "") if g.signin else 'anonymous'
    #: 实时获取后台配置中允许上传的后缀，如: jpg|jpeg|png
    allowed_suffix = partial(
        allowed_file,
        suffix=parse_valid_verticaline(g.cfg.upload_exts)
    )
    if f and allowed_suffix(f.filename):
        try:
            g.rc.ping()
        except RedisError as e:
            logger.error(e, exc_info=True)
            res.update(code=2, msg="Program data storage service error")
            return res
        stream = f.stream.read()
        suffix = splitext(f.filename)[-1]
        filename = secure_filename(f.filename)
        if "." not in filename:
            filename = "%s%s" % (generate_random(8), suffix)
        #: 根据文件名规则重定义图片名
        upload_file_rule = g.cfg.upload_file_rule
        if upload_file_rule in ("time1", "time2", "time3"):
            filename = "%s%s" % (
                gen_rnd_filename(upload_file_rule),
                suffix
            )
        #: 上传文件位置前缀规则
        upload_path_rule = g.cfg.upload_path_rule
        if upload_path_rule == 'date1':
            upload_path = get_today("%Y/%m/%d")
        elif upload_path_rule == 'date2':
            upload_path = get_today("%Y%m%d")
        else:
            upload_path = ''
        upload_path = join(g.userinfo.username or 'anonymous', upload_path)
        #: 定义文件名唯一索引
        sha = "sha1.%s.%s" % (get_current_timestamp(True), sha1(filename))
        #: 定义保存图片时仅使用某些钩子，如: up2local
        #: TODO 目前版本仅允许设置了一个，后续聚合
        includes = parse_valid_comma(g.cfg.upload_includes or 'up2local')
        if len(includes) > 1:
            includes = [choice(includes)]
        #: TODO 定义保存图片时排除某些钩子，如: up2local, up2other
        # excludes = parse_valid_comma(g.cfg.upload_excludes or '')
        #: 钩子返回结果（目前版本最终结果中应该最多只有1条数据）
        data = []
        #: 保存图片的钩子回调
        def callback(result):
            logger.info(result)
            if result["sender"] == "up2local":
                result["src"] = url_for(
                    "static",
                    filename=join(UPLOAD_FOLDER, upload_path, filename),
                    _external=True
                )
            data.append(dfr(result))
        #: 调用钩子中upimg_save方法
        current_app.extensions["hookmanager"].call(
            _funcname="upimg_save",
            _callback=callback,
            _include=includes,
            filename=filename,
            stream=stream,
            upload_path=upload_path,
            local_basedir=join(
                current_app.root_path, current_app.static_folder, UPLOAD_FOLDER
            )
        )
        #: 判定后端存储全部失败时，上传失败
        if not data:
            res.update(code=1, msg="No valid backend storage service")
            return res
        if len(data) == len(
            [i for i in data if i.get("code") != 0]
        ):
            res.update(
                code=1,
                msg="All backend storage services failed to save pictures"
            )
            return res
        #: 存储数据
        defaultSrc = data[0]["src"]
        pipe = g.rc.pipeline()
        pipe.sadd(rsp("index", "global"), sha)
        if g.signin and g.userinfo.username:
            pipe.sadd(rsp("index", "user", g.userinfo.username), sha)
        pipe.hmset(rsp("image", sha), dict(
            sha=sha,
            album=album,
            filename=filename,
            upload_path=upload_path,
            user=g.userinfo.username if g.signin else 'anonymous',
            ctime=get_current_timestamp(),
            status='enabled',  # disabled, deleted
            src=defaultSrc,
            sender=data[0]["sender"],
            senders=json.dumps(data)
        ))
        try:
            pipe.execute()
        except RedisError as e:
            logger.error(e, exc_info=True)
            res.update(code=3, msg="Program data storage service error")
        else:
            res.update(
                code=0,
                filename=filename,
                sender=data[0]["sender"],
                api=url_for("api.shamgr", sha=sha, _external=True),
            )
            #: format指定图片地址的显示字段，默认src，可以用点号指定
            #: 比如data.src，那么返回格式{code, filename..., data:{src}, ...}
            fmt = request.form.get("format", request.args.get("format"))
            res.update(format_upload_src(fmt, defaultSrc))
    else:
        res.update(msg="No file or image format allowed")
    return res


@bp.route("/extendpoint", methods=["GET", "POST"])
def ep():
    if request.method == "GET":
        return abort(404)
    Object = request.args.get("Object")
    Action = request.args.get("Action")
    if Object and Action:
        obj = current_app.extensions["hookmanager"].proxy(Object)
        if obj and hasattr(obj, Action):
            result = getattr(obj, Action)()
            if result and isinstance(result, Response):
                return result


@bp.route("/album", methods=["GET", "POST"])
@apilogin_required
def album():
    if request.method == "GET":
        return abort(404)
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
            res.update(
                code=0,
                data=list(set(albums)),
                counter=Counter(albums)
            )
    else:
        res.update(msg="No valid username found")
    return jsonify(res)
