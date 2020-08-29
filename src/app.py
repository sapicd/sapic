# -*- coding: utf-8 -*-
"""
    app
    ~~~

    Entrance

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from flask import Flask, g, request, render_template, jsonify
from views import front_bp, api_bp
from utils.tool import Attribute, is_true, parse_valid_comma, err_logger, \
    timestamp_to_timestring
from utils.web import get_site_config, JsonResponse, default_login_auth, \
    get_redirect_url, change_userinfo, rc, get_page_msg, get_push_msg, dfr
from utils.exceptions import ApiError, PageError
from utils.cli import sa_cli
from libs.hook import HookManager
from config import GLOBAL
from version import __version__

__author__ = 'staugur'
__email__ = 'staugur@saintic.com'
__date__ = '2019-12-20'
__doc__ = 'Flask-based web self-built pictures bed'

app = Flask(__name__)
app.response_class = JsonResponse
app.config.update(
    SECRET_KEY=GLOBAL["SecretKey"],
    MAX_UPLOAD=GLOBAL["MaxUpload"],
    MAX_CONTENT_LENGTH=GLOBAL["MaxUpload"] * 1024 * 1024,
    DOCS_BASE_URL="https://picbed.rtfd.vip",
    UPLOAD_FOLDER="upload",
)

hm = HookManager(app)
app.register_blueprint(front_bp)
app.register_blueprint(api_bp, url_prefix="/api")
app.cli.add_command(sa_cli)


@app.context_processor
def gtv():
    return {
        "Version": __version__, "Doc": __doc__, "is_true": is_true,
        "timestamp_to_timestring": timestamp_to_timestring,
        "get_page_msg": get_page_msg, "get_push_msg": get_push_msg,
    }


@app.before_request
def before_request():
    g.rc = rc
    g.site = get_site_config()
    g.cfg = Attribute(g.site)
    g.signin, g.userinfo = default_login_auth()
    #: Trigger hook, you can modify flask.g
    hm.call("before_request")
    #: (Logged-on state)required field: username, is_admin
    g.userinfo = Attribute(change_userinfo(g.userinfo))
    g.is_admin = is_true(g.userinfo.is_admin)
    g.next = get_redirect_url()
    g.site_name = g.cfg.title_name or "picbed"
    g.hm = hm


@app.after_request
def after_request(res):
    #: Trigger hook, you can modify the response
    hm.call("after_request", _args=(res,))
    if g.cfg.cors:
        if g.cfg.cors == "*":
            res.headers.add("Access-Control-Allow-Origin", "*")
        else:
            cors = parse_valid_comma(g.cfg.cors)
            origin = request.headers.get("Origin")
            if origin in cors:
                res.headers.add("Access-Control-Allow-Origin", origin)
    res.headers['X-Content-Type-Options'] = 'nosniff'
    res.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return res


@app.errorhandler(500)
@app.errorhandler(405)
@app.errorhandler(404)
@app.errorhandler(403)
@app.errorhandler(413)
@app.errorhandler(400)
def handle_error(e):
    if getattr(e, "code", None) == 500:
        err_logger.error(e, exc_info=True)
    code = e.code
    name = e.name
    if request.path.startswith("/api/"):
        return jsonify(dict(msg=name, code=code)), code
    return render_template("public/error.html", code=code, name=name), code


@app.errorhandler(ApiError)
def handle_api_error(e):
    response = jsonify(dfr(e.to_dict()))
    response.status_code = e.status_code
    return response


@app.errorhandler(PageError)
def handle_page_error(e):
    resp = dfr(e.to_dict())
    return render_template(
        "public/error.html", code=resp["code"], name=resp["msg"]
    ), e.status_code
