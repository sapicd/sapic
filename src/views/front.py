# -*- coding: utf-8 -*-
"""
    views.front
    ~~~~~~~~~~~

    Frontend view functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from flask import Blueprint, render_template, make_response, redirect, \
    url_for, current_app, Response, g, abort
from utils.web import admin_apilogin_required, anonymous_required, \
    login_required, check_activate_token, dfr
from utils.tool import is_true, rsp, string_types
from utils._compat import PY2, text_type

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
    if res["code"] == 0:
        data = res["data"]
        Action = data["Action"]

        if Action == "verifyEmail":
            username = data["username"]
            checkmail = data["email"]
            uk = rsp("account", username)
            usermail = g.rc.hget(uk, "email")
            success = False
            url = url_for("front.my") if g.signin else url_for("front.login")
            if checkmail == usermail:
                g.rc.hset(uk, "email_verified", 1)
                success = True
            return render_template("public/go.html", url=url, success=success)

        elif Action == "resetPassword":
            username = data["username"]
            return render_template(
                "public/forgot.html", is_reset=True, token=token, user=username
            )

    else:
        name = res["msg"]
        if PY2 and not isinstance(name, text_type):
            name = name.decode("utf-8")
        return render_template(
            "public/error.html", code=res["code"], name=name
        )


@bp.route("/forgot")
@anonymous_required
def forgot():
    return render_template("public/forgot.html")


@bp.route("/extendpoint/<hook_name>/", defaults=dict(route_name=None))
@bp.route("/extendpoint/<hook_name>/<route_name>")
def ep(hook_name, route_name):
    obj = current_app.extensions["hookmanager"].proxy(hook_name)
    if obj and hasattr(obj, "route"):
        rule = obj.route()
        if isinstance(rule, string_types):
            return rule
        elif isinstance(rule, dict) and route_name in rule:
            return rule[route_name]
    return abort(404)
