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


def before_request():
    if g.signin:
        return
    token = request.form.get("token") or parseAuthorization()
    if token:
        try:
            if PY2 and isinstance(token, text_type):
                token = token.encode("utf-8")
            token = b64decode(token)
            if not PY2 and not isinstance(token, text_type):
                token = token.decode("utf-8")
            usr, ctime, sig = token.split(".")
            ctime = int(ctime)
        except (TypeError, ValueError, AttributeError, Exception):
            pass
        else:
            tk = rsp("tokens")
            usr = g.rc.hget(tk, token)
            if usr:
                ak = rsp("account", usr)
                userinfo = g.rc.hgetall(ak)
                if userinfo and isinstance(userinfo, dict):
                    pwd = userinfo.pop("password", None)
                    if ("%s.%s.%s" % (
                        usr,
                        ctime,
                        hmac_sha256(pwd, usr)
                    )) == sig:
                        g.signin = True
                        g.userinfo = userinfo


def after_request(res):
    res.headers.add("Access-Control-Allow-Headers", "Authorization")
