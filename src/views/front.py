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
    login_required
from utils.tool import is_true

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
