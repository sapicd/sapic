# -*- coding: utf-8 -*-
"""
    views.front
    ~~~~~~~~~~~

    Frontend view functions.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from flask import Blueprint, render_template, make_response, redirect, url_for
from utils.web import login_required, admin_apilogin_required

bp = Blueprint("front", "front")


@bp.route("/")
def index():
    return render_template("public/index.html")


@bp.route("/login")
def login():
    return render_template("public/login.html")


@bp.route("/logout")
def logout():
    res = make_response(redirect(url_for("front.index")))
    res.set_cookie(key='dSid',  value='', expires=0)
    return res


@bp.route("/control/profile.im")
@login_required
def profile():
    return render_template("control/profile.html")


@bp.route("/control/image.pic")
@login_required
def image():
    return render_template("control/image.html")


@bp.route("/control/admin.ext")
@admin_apilogin_required
def admin():
    return render_template("control/admin.html")
