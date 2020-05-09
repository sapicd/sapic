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
    parse_valid_verticaline, get_today, gen_rnd_filename, hmac_sha256, rsp, \
    sha256, get_current_timestamp, ListEqualSplit, generate_random, er_pat, \
    format_upload_src, check_origin, get_origin, check_ip, gen_uuid, ir_pat, \
    check_ir
from utils.web import dfr, admin_apilogin_required, apilogin_required, \
    set_site_config, check_username, Base64FileStorage
from utils._compat import iteritems

bp = Blueprint("api", "api")
#: 定义本地上传的钩子在保存图片时的基础目录前缀（在static子目录下）
UPLOAD_FOLDER = "upload"
FIELD_NAME = "picbed"


@bp.after_request
def translate(res):
    if res.is_json:
        data = res.get_json()
        if isinstance(data, dict):
            res.set_data(json.dumps(dfr(data)))
    return res


@bp.route("/", methods=["GET", "POST"])
@bp.route("/index", methods=["GET", "POST"])
def index():
    return jsonify(
        "Hello %s." % (g.userinfo.username if g.signin else "picbed")
    )


@bp.route("/login", methods=["POST"])
def login():
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
    if usr and pwd and len(pwd) >= 6:
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


@bp.route("/register", methods=["POST"])
def register():
    if is_true(g.cfg.register) is False:
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


@bp.route("/token", methods=["POST"])
@apilogin_required
def token():
    res = dict(code=1)
    usr = g.userinfo.username
    tk = rsp("tokens")
    ak = rsp("account", usr)

    def gen_token(key):
        """生成可以用key校验的token"""
        return b64encode(
            ("%s.%s.%s.%s" % (
                generate_random(),
                usr,
                get_current_timestamp(),
                hmac_sha256(key, usr)
            )).encode("utf-8")
        ).decode("utf-8")
    Action = request.args.get("Action")
    if Action == "create":
        if g.rc.hget(ak, "token"):
            res.update(msg="Existing token")
        else:
            tkey = generate_random(randint(6, 12))
            token = gen_token(tkey)
            try:
                pipe = g.rc.pipeline()
                pipe.hset(tk, token, usr)
                pipe.hmset(ak, dict(token=token, token_key=tkey))
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
        tkey = generate_random(randint(6, 12))
        token = gen_token(tkey)
        try:
            pipe = g.rc.pipeline()
            if oldToken:
                pipe.hdel(tk, oldToken)
            pipe.hset(tk, token, usr)
            pipe.hmset(ak, dict(token=token, token_key=tkey))
            pipe.execute()
        except RedisError:
            res.update(msg="Program data storage service error")
        else:
            res.update(code=0, token=token)
    return res


@bp.route("/myself", methods=["PUT", "POST"])
@apilogin_required
def my():
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
    elif Action == "updateUserCfg":
        #: 更新用户设置，为避免覆盖ak字段，所有更新的key必须`ucfg_`开头
        cfgs = request.form.to_dict()
        if cfgs:
            for k in cfgs:
                if not k.startswith("ucfg_"):
                    res.update(msg="The user setting must start with `ucfg_`")
                    return res
            try:
                g.rc.hmset(ak, cfgs)
            except RedisError:
                res.update(msg="Program data storage service error")
            else:
                res.update(code=0)
    return res


@bp.route("/waterfall", methods=["POST"])
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
    fp = request.files.get(FIELD_NAME)
    #: 当fp无效时尝试读取base64
    if not fp:
        pic64str = request.form.get(FIELD_NAME)
        filename = request.form.get("filename")
        if pic64str:
            try:
                #: 注意，base64在部分客户端发起http请求时，可能+换成空格，出现异常
                fp = Base64FileStorage(pic64str, filename)
            except ValueError as e:
                logger.debug(e, exc_info=True)
                fp = None
    #: 相册名称，可以是任意字符串
    album = (
        request.form.get("album") or getattr(g, "up_album", "")
    ) if g.signin else 'anonymous'
    #: 实时获取后台配置中允许上传的后缀，如: jpg|jpeg|png
    allowed_suffix = partial(
        allowed_file,
        suffix=parse_valid_verticaline(g.cfg.upload_exts)
    )
    if fp and allowed_suffix(fp.filename):
        try:
            g.rc.ping()
        except RedisError as e:
            logger.error(e, exc_info=True)
            res.update(code=2, msg="Program data storage service error")
            return res
        stream = fp.stream.read()
        suffix = splitext(fp.filename)[-1]
        filename = secure_filename(fp.filename)
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
        res.update(msg="No file or image format error")
    return res


@bp.route("/extendpoint", methods=["POST"])
def ep():
    """专用于钩子扩展API方法"""
    Object = request.args.get("Object")
    Action = request.args.get("Action")
    if Object and Action:
        obj = current_app.extensions["hookmanager"].proxy(Object)
        if obj and hasattr(obj, Action):
            result = getattr(obj, Action)()
            if result and isinstance(result, Response):
                return result


@bp.route("/album", methods=["POST"])
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
            res.update(
                code=0,
                data=list(set(albums)),
                counter=Counter(albums)
            )
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
                if md and md.upper() not in ["GET", "POST", "PUT", "DELETE"]:
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
        # TODO Administrator limit, user select
        allow_ep = request.form.get("allow_ep") or "api.index,api.upload"
        allow_method = request.form.get("allow_method") or "post"
        #: 判断用户是否有token
        ak = rsp("account", username)
        if not g.rc.hget(ak, "token"):
            res.update(msg="No tokens yet")
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
            hmac_sha256(LinkId, LinkSecret)
        )
        LinkToken = b64encode(lid.encode("utf-8")).decode("utf-8")
        pipe = g.rc.pipeline()
        pipe.hset(ltk, LinkId, username)
        pipe.hmset(rsp("linktoken", LinkId), dict(
            LinkId=LinkId,
            LinkSecret=LinkSecret,
            LinkToken=LinkToken,
            ctime=get_current_timestamp(),
            user=username,
            comment=comment,
            album=album,
            status=1,  # 状态，1是启用，0是禁用
            allow_origin=allow_origin,
            allow_ip=allow_ip,
            allow_ep=allow_ep,
            allow_method=allow_method,
            exterior_relation=er,
            interior_relation=ir,
        ))
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
            allow_ep = request.form.get("allow_ep") or "api.index,api.upload"
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
            pipe = g.rc.pipeline()
            pipe.hset(ltk, LinkId, username)
            pipe.hmset(key, dict(
                mtime=get_current_timestamp(),
                comment=comment,
                album=album,
                allow_origin=allow_origin,
                allow_ip=allow_ip,
                allow_ep=allow_ep,
                allow_method=allow_method,
                exterior_relation=er,
                interior_relation=ir,
            ))
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
    res = dict(code=1)
    start = request.args.get("start")
    end = request.args.get("end")
    page = request.args.get("page")
    limit = request.args.get("limit")
    sort = (request.args.get("sort") or "asc").upper()
    is_mgr = is_true(request.args.get("is_mgr"))
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
                start = (page-1) * limit
                end = start + limit - 1
        if isinstance(start, int) and isinstance(end, int):
            key = rsp("report", classify)
            pipe = g.rc.pipeline()
            pipe.llen(key)
            pipe.lrange(key, start, end)
            result = pipe.execute()
            if result and isinstance(result, list) and len(result) == 2:
                count, data = result
                if sort == "DESC":
                    data.reverse()
                new = []
                for r in data:
                    r = json.loads(r)
                    if is_mgr and g.is_admin:
                        new.append(r)
                    else:
                        if r.get("user") == g.userinfo.username:
                            new.append(r)
                res.update(code=0, data=new, count=count)
        else:
            res.update(msg="Wrong query range parameter")
    else:
        return abort(404)
    return res
