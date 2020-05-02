# -*- coding: utf-8 -*-
"""
    hooks.token
    ~~~~~~~~~~~

    Validate Api request with token.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.3.0'
__author__ = 'staugur'
__description__ = '使用Token验证Api'

import json
from flask import request, g
from base64 import urlsafe_b64decode as b64decode
from utils.tool import rsp, hmac_sha256, logger, get_current_timestamp, \
    parse_valid_comma, Attribution
from utils._compat import PY2, text_type

intpl_profile = u"""
<div class="layui-form-item">
    <label class="layui-form-label">Token</label>
    <div class="layui-input-inline">
        <input type="text" name="token" id="token" autocomplete="off" value="{{ g.userinfo.token }}" class="layui-input" readonly="" placeholder="暂无Api登录密钥">
    </div>
    <div class="layui-form-mid layui-word-aux">
        {% if g.userinfo.token %}
        {% set yesClass = 'layui-show' %}
        {% set noClass = 'layui-hide' %}
        {% else %}
        {% set yesClass = 'layui-hide' %}
        {% set noClass = 'layui-show' %}
        {% endif %}
        <div id="yesToken" class="{{ yesClass }}">
            <a href="javascript:;" style="color: #5FB878" id="copyToken">复制</a> <a href="javascript:;" style="color: #FFB800" id="resetToken">重置</a> <a href="javascript:;" style="color: #FF5722" id="revokeToken">销毁</a>
        </div>
        <div id="noToken" class="{{ noClass }}">
            <a href="javascript:;" style="color: #009688" id="createToken">生成</a>
        </div>
    </div>
</div>
"""

intpl_before_usersetting = u'<table id="linktokenTable" class="layui-table" lay-filter="linktokenTable"></table>'


def parseAuthorization(prefix="Token"):
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("%s " % prefix):
        return auth.lstrip("%s " % prefix)


def get_origin():
    return request.headers.get("Origin")


def get_ip():
    return request.headers.get('X-Real-Ip', request.remote_addr)


def is_allow_ip(secure_ips):
    """当secure_ips有效时，检测access_ip值，否则直接通过"""
    access_ip = get_ip()
    if secure_ips:
        if not isinstance(secure_ips, (tuple, list)):
            secure_ips = secure_ips.split(",")
        secure_ips = [ip for ip in secure_ips if ip]
        if access_ip not in secure_ips:
            return False
    return True


def is_allow_origin(secure_origins):
    """当secure_origins有效时，检测access_origin值，否则直接通过"""
    access_origin = get_origin()
    if secure_origins:
        if not isinstance(secure_origins, (tuple, list)):
            secure_origins = secure_origins.split(",")
        secure_origins = [o for o in secure_origins if o]
        if access_origin not in secure_origins:
            return False
    return True


def _allow_ir(ir, allow):
    """//"""
    if ir:
        for key in allow.keys():
            ir = ir.replace(key, allow[key])
        print("_allow_ir: %s" % ir)
    else:
        return True


def verify_rule(Ld):
    """根据er、ir规则判断是否放行请求"""
    allow = Attribution(dict(
        ip=parse_valid_comma(Ld["allow_ip"]) or [],
        ep=parse_valid_comma(Ld["allow_ep"]) or [],
        origin=parse_valid_comma(Ld["allow_origin"]) or [],
        method=parse_valid_comma(Ld["allow_method"]) or [],
    ))
    #: 参数 逻辑运算符 参数 逻辑运算符 参数...
    #: 参数: origin and ip and ep or method
    #: 逻辑运算符: and or not in not in
    #: er控制的是参数之前的逻辑运算符
    #: ir控制的是参数如何返回True
    er = Ld["exterior_relation"]
    ir = Ld["interior_relation"]

    ip = get_ip()
    ep = request.endpoint
    origin = get_origin()
    if not er and not ir:
        #: 默认模式，er是and，ir是in
        if is_allow_ip(allow.ip) and ep in allow.ep and \
                is_allow_origin(allow.origin):
            return True


def before_request():
    if g.signin:
        return
    token = request.form.get("token") or parseAuthorization()
    #: 尝试使用LinkToken映射出token
    LinkToken = parseAuthorization("LinkToken")
    if not token and LinkToken:
        try:
            if PY2 and isinstance(LinkToken, text_type):
                LinkToken = LinkToken.encode("utf-8")
            LinkToken = b64decode(LinkToken)
            if not PY2 and not isinstance(LinkToken, text_type):
                LinkToken = LinkToken.decode("utf-8")
            ctime, LinkId, LinkSig = LinkToken.split(":")
            ctime = int(ctime)
            if not LinkId or not LinkSig:
                raise ValueError
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug(e, exc_info=True)
        else:
            pipe = g.rc.pipeline()
            pipe.hexists(rsp("linktokens"), LinkId)
            pipe.hgetall(rsp("linktoken", LinkId))
            result = pipe.execute()
            if result[0] is True and result[1] and isinstance(result[1], dict):
                #: LinkId有效，但等待校验签名与权限，可以统计请求数据
                Ld = result[1]
                usr = Ld.get("user")
                secret = Ld.get("LinkSecret")
                status = int(Ld.get("status", 1))
                if status == 1 and hmac_sha256(LinkId, secret) == LinkSig:
                    authentication = "ok"
                    # 权限校验规则
                    #: 此不仅限于AJAX跨域请求了，相当于token分权
                    origin = get_origin()
                    #: 限定允许访问部分路由，并校验安全域名、ip
                    allow_ip = Ld["allow_ip"]
                    allow_ep = Ld["allow_ep"].split(",")
                    allow_origin = Ld["allow_origin"].split(",")
                    if is_allow_ip(allow_ip) and request.endpoint in allow_ep \
                            and origin in allow_origin:
                        authorization = "ok"
                        logger.info("LinkToken ok and permission pass")
                        g.up_album = Ld.get("album")
                        token = g.rc.hget(rsp("account", usr), "token")
                    else:
                        authorization = "fail"
                        logger.info("LinkToken ok and permission deny")
                else:
                    authentication = "fail"
                    authorization = "fail"
                    logger.debug("LinkToken fail: %s" % LinkToken)
                #: 统计入库
                g.rc.lpush(rsp("report", "linktokens"), json.dumps(dict(
                    LinkId=LinkId,
                    user=usr,
                    ctime=get_current_timestamp(),
                    ip=get_ip(),
                    agent=request.headers.get('User-Agent', ''),
                    referer=request.headers.get('Referer', ''),
                    origin=request.headers.get('Origin', ''),
                    ep=request.endpoint,
                    authentication=authentication,
                    authorization=authorization,
                )))
    if token:
        try:
            oldToken = token
            if PY2 and isinstance(token, text_type):
                token = token.encode("utf-8")
            token = b64decode(token)
            if not PY2 and not isinstance(token, text_type):
                token = token.decode("utf-8")
            rdm, usr, ctime, sig = token.split(".")
            ctime = int(ctime)
            assert len(rdm) == 6
        except (TypeError, ValueError, AttributeError, Exception) as e:
            logger.debug(e, exc_info=True)
        else:
            tk = rsp("tokens")
            token2usr = g.rc.hget(tk, oldToken)
            if token2usr and token2usr == usr:
                ak = rsp("account", usr)
                userinfo = g.rc.hgetall(ak)
                if userinfo and isinstance(userinfo, dict):
                    pwd = userinfo.pop("password", None)
                    tkey = userinfo.pop("token_key", None)
                    if hmac_sha256(pwd, usr) == sig or \
                            (tkey and hmac_sha256(tkey, usr) == sig):
                        g.signin = True
                        g.userinfo = userinfo


def after_request(res):
    res.headers.add("Access-Control-Allow-Headers", "Authorization")
