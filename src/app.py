# -*- coding: utf-8 -*-
"""
    app
    ~~~

    Entrance

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from uuid import uuid4
from flask import Flask, g, jsonify
from version import __version__
from views import front_bp, api_bp
from utils.tool import Attribute, err_logger, is_true
from utils.web import get_site_config, JsonResponse, default_login_auth
from libs.hook import HookManager
from config import GLOBAL

__author__ = 'staugur'
__email__ = 'staugur@saintic.com'
__date__ = '2019-12-20'
__doc__ = 'Flask-based Web self-built pictures bed'

app = Flask(__name__)
app.response_class = JsonResponse
app.config.update(
    SECRET_KEY=GLOBAL.get("SecretKey") or str(uuid4()),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
)

hm = HookManager(app)

app.register_blueprint(front_bp)
app.register_blueprint(api_bp, url_prefix="/api")


@app.context_processor
def GlobalTemplateVariables():
    return {"Version": __version__, "is_true": is_true}


@app.before_request
def before_request():
    g.signin, g.userinfo = default_login_auth()
    #: Trigger hook, you can modify flask.g
    hm.call("before_request")
    #: No Required field
    g.site = get_site_config()
    g.cfg = Attribute(g.site)
    #: Required field: username, is_admin
    g.userinfo = Attribute(g.userinfo)
    g.is_admin = is_true(g.userinfo.is_admin)


@app.after_request
def after_request(res):
    #: Trigger hook, you can modify the response
    hm.call("after_request", res=res)
    return res


@app.errorhandler(500)
def server_error(error=None):
    if error:
        err_logger.error(error, exc_info=True)
    message = {
        "msg": "Internal Server Error",
        "code": 500
    }
    return jsonify(message), 500


@app.errorhandler(404)
def not_found(error=None):
    message = {
        'code': 404,
        'msg': 'Not Found'
    }
    resp = jsonify(message)
    resp.status_code = 404
    return resp


@app.errorhandler(403)
def permission_denied(error=None):
    return jsonify({
        "msg": "Forbidden",
        "code": 403
    }), 403


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "msg": "Request Entity Too Large",
        "code": 403
    }), 413
