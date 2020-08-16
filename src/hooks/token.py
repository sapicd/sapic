# -*- coding: utf-8 -*-
"""
    hooks.token
    ~~~~~~~~~~~

    Validate Api request with token.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.3.4'
__author__ = 'staugur'
__description__ = '使用Token验证Api'
__catalog__ = 'auth'

import json
from flask import request, g
from base64 import urlsafe_b64decode as b64decode
from utils.tool import rsp, hmac_sha256, logger, get_current_timestamp, \
    parse_valid_comma, Attribution, ALLOWED_RULES, is_true, parse_ua
from utils._compat import PY2, text_type

intpl_profile = """
<div class="layui-form-item">
    <label class="layui-form-label"><i class="layui-icon layui-icon-about" id="tokentip"></i> Token</label>
    <div class="layui-input-inline">
        <input type="text" name="token" id="token" autocomplete="off" value="{{ g.userinfo.token }}" class="layui-input layui-disabled" disabled placeholder="暂无Api密钥">
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

intpl_before_usersetting = '<table id="linktokenTable" class="layui-table" lay-filter="linktokenTable"></table>'


def parse_authorization(prefix="Token"):
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("%s " % prefix):
        return auth.lstrip("%s " % prefix)


def get_origin():
    return request.headers.get("Origin") or ""


def get_ip():
    return request.headers.get('X-Real-Ip', request.remote_addr)


def get_ua():
    return request.headers.get('User-Agent', '')


def _parse_ir(ir):
    """解析ir规则，其格式是: in:opt1, not in:opt2"""
    if ir:
        rules = {}
        for i in parse_valid_comma(ir):
            opr, opt = i.split(":")
            if opt in ALLOWED_RULES and opr in ("in", "not in"):
                rules[opt] = opr
        return rules


def _allow_ir(ir, allow):
    """解析ir规则，返回所有参数最终判断True的语句字符串
    :param ir: in opt, not in opt
    :return: {opt:(access_opt in/not in secure_opt), opt:(other)...}
    """
    #: ir解析成{opt:not in, opt:in, ...}
    rules = _parse_ir(ir) or {}
    cmd = {}
    for opt in ALLOWED_RULES:
        #: 只有用户定义了参数的安全项时才判断访问合法性
        if allow[opt].secure:
            cmd[opt] = "('%s' %s %s)" % (
                allow[opt].access, rules.get(opt, "in"), allow[opt].secure
            )
        else:
            cmd[opt] = "True"
    return cmd


def verify_rule(Ld):
    """根据er、ir规则判断是否放行请求"""
    allow = Attribution(dict(
        ip=Attribution(dict(
            access=get_ip(),
            secure=parse_valid_comma(Ld["allow_ip"]) or []
        )),
        origin=Attribution(dict(
            access=get_origin(),
            secure=parse_valid_comma(Ld["allow_origin"]) or []
        )),
        ep=Attribution(dict(
            access=request.endpoint,
            secure=parse_valid_comma(Ld["allow_ep"]) + ["api.index"]
        )),
        method=Attribution(dict(
            access=request.method,
            secure=[
                m.upper()
                for m in parse_valid_comma(Ld["allow_method"]) or []
                if m
            ]
        ))
    ))
    #: 参数 逻辑运算符 参数 逻辑运算符 参数...
    #: 参数: origin and ip and ep and method
    #: 逻辑运算符: and or not in not in
    #: er控制的是参与逻辑运算的参数及之间的逻辑运算符
    #: ir控制的是参数如何返回True
    er = Ld["exterior_relation"]
    ir = Ld["interior_relation"]
    if not er:
        er = "origin and ip and ep and method"
    #: ir定义的最终规则
    ir_cmd = _allow_ir(ir, allow)
    #: 综合er、ir构建最终执行的命令字符串
    for opt in ALLOWED_RULES:
        er = er.replace(opt, ir_cmd[opt])
    logger.debug("last er: %s" % er)
    return eval(er)


def before_request():
    if g.signin:
        return
    token = request.form.get("token") or parse_authorization()
    #: 尝试使用LinkToken映射出token
    LinkToken = request.form.get(
        "LinkToken", request.args.get("LinkToken")
    ) or parse_authorization("LinkToken")
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
                userinfo = g.rc.hmget(
                    rsp("account", usr), "token", "ucfg_report_linktoken"
                )
                if status == 1 and hmac_sha256(LinkId, secret) == LinkSig:
                    authentication = "ok"
                    #: 权限校验规则
                    if verify_rule(Ld):
                        authorization = "ok"
                        logger.info("LinkToken ok and permission pass")
                        g.up_album = Ld.get("album")
                        token = userinfo[0]
                    else:
                        authorization = "fail"
                        logger.info("LinkToken ok and permission deny")
                else:
                    authentication = "fail"
                    authorization = "fail"
                #: 统计入库
                if is_true(userinfo[1]):
                    g.rc.lpush(
                        rsp("report", "linktokens", usr),
                        json.dumps(dict(
                            LinkId=LinkId,
                            user=usr,
                            ctime=get_current_timestamp(),
                            ip=get_ip(),
                            agent=get_ua(),
                            uap=parse_ua(get_ua()),
                            referer=request.headers.get('Referer', ''),
                            origin=get_origin(),
                            ep=request.endpoint,
                            authentication=authentication,
                            authorization=authorization,
                        ))
                    )
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
                userstatus = int(userinfo.get("status", 1))
                if userinfo and userstatus != 0:
                    pwd = userinfo.pop("password", None)
                    tkey = userinfo.pop("token_key", None)
                    if hmac_sha256(pwd, usr) == sig or \
                            (tkey and hmac_sha256(tkey, usr) == sig):
                        g.signin = True
                        g.userinfo = userinfo
                        #: token验证通过，判断是否禁止普通用户登录
                        if is_true(g.cfg.disable_login) and \
                                not is_true(userinfo.get("is_admin")):
                            g.signin = False
                            g.userinfo = {}


def after_request(res):
    res.headers.add("Access-Control-Allow-Headers", "Authorization")
