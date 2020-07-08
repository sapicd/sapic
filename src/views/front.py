# -*- coding: utf-8 -*-
"""
    views.front
    ~~~~~~~~~~~

    Frontend view functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from flask import Blueprint, render_template, make_response, redirect, \
    url_for, current_app, Response, g, abort, render_template_string
from utils.web import admin_apilogin_required, anonymous_required, \
    login_required, check_activate_token, dfr
from utils.tool import is_true, rsp

bp = Blueprint("front", "front")


@bp.route("/")
def index():
    return render_template("public/index.html")


@bp.route("/login")
@anonymous_required
def login():
    if g.cfg.site_auth:
        so = current_app.extensions["hookmanager"].proxy(g.cfg.site_auth)
        if so and hasattr(so, "login_handler"):
            result = so.login_handler()
            if result and isinstance(result, Response):
                return result
    return render_template("public/login.html")


@bp.route("/logout")
@login_required
def logout():
    if g.cfg.site_auth:
        so = current_app.extensions["hookmanager"].proxy(g.cfg.site_auth)
        if so and hasattr(so, "logout_handler"):
            result = so.logout_handler()
            if result and isinstance(result, Response):
                return result
    res = make_response(redirect(url_for("front.index")))
    res.set_cookie(key='dSid',  value='', expires=0)
    return res


@bp.route("/register")
@anonymous_required
def register():
    if is_true(g.cfg.register):
        return render_template("public/register.html")
    else:
        return abort(404)


@bp.route("/control/myself")
@login_required
def my():
    return render_template("control/my.html")


@bp.route("/control/admin")
@admin_apilogin_required
def admin():
    return render_template("control/admin.html")


@bp.route("/picbed.user.js")
def userscript():
    if g.signin and is_true(g.userinfo.ucfg_userscript):
        resp = make_response(render_template("public/userscript.js"))
        resp.headers['Content-type'] = 'application/javascript; charset=utf-8'
        return resp
    else:
        return abort(404)


@bp.route("/activate/<token>")
def activate(token):
    res = dfr(check_activate_token(token))
    print(res)
    if res["code"] == 0:
        data = res["data"]
        Action = data["Action"]
        ActionMsg = None
        if Action == "VerifyEmail":
            ActionMsg = "邮箱"
            username = data["username"]
            checkmail = data["email"]
            uk = rsp("account", username)
            usermail = g.rc.hget(uk, "email")
            if checkmail == usermail:
                g.rc.hset(uk, "email_verified", 1)
        url = url_for("front.my") if g.signin else url_for("front.login")
        return render_template_string(
            '''
            <!doctype html>
            <html>
            <head>
                <title>{{ g.site.title_name or "picbed" }}</title>
                <meta http-equiv="refresh" content="2; url='{{ url }}'">
            </head>
            <body>
                <h3 style="color:#009688">Hi %s, %s验证通过！</h3>
            </body>
            </html>
            ''' % (username, ActionMsg),
            url=url,
        )
    else:
        return render_template(
            "public/error.html", code=res["code"], name=res["msg"]
        )
