# -*- coding: utf-8 -*-
"""
    hooks.token
    ~~~~~~~~~~~

    Validate Api request with token.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""


__version__ = '0.1.0'
__author__ = 'staugur'
__description__ = '使用Token验证Api'


from flask import request, g
from base64 import urlsafe_b64decode as b64decode
from utils.tool import rsp, hmac_sha256
from utils.web import parseAuthorization
from utils._compat import PY2, text_type

intpl_profile = u"""
<div class="layui-form-item">
    <label class="layui-form-label">Token</label>
    <div class="layui-input-inline">
        <input type="text" name="token" id="token" autocomplete="off" value="{{ g.userinfo.token }}" class="layui-input" readonly="" placeholder="Api登录密钥">
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


def before_request():
    if g.signin:
        return
    token = request.form.get("token") or parseAuthorization()
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
        except (TypeError, ValueError, AttributeError, Exception):
            pass
        else:
            tk = rsp("tokens")
            token2usr = g.rc.hget(tk, oldToken)
            if token2usr and token2usr == usr:
                ak = rsp("account", usr)
                userinfo = g.rc.hgetall(ak)
                if userinfo and isinstance(userinfo, dict):
                    pwd = userinfo.pop("password", None)
                    if hmac_sha256(pwd, usr) == sig:
                        g.signin = True
                        g.userinfo = userinfo


def after_request(res):
    res.headers.add("Access-Control-Allow-Headers", "Authorization")
