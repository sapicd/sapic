# -*- coding: utf-8 -*-
"""
    hooks.sendmail
    ~~~~~~~~~~~~~~

    Encapsulate multiple mail sending methods.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.1.1'
__author__ = 'staugur'
__description__ = '多方式发送邮件'


from flask import request, g
from utils.tool import Mailbox, try_request, logger, is_true


intpl_emailsetting = '''
<div class="layui-col-xs12 layui-col-sm12 layui-col-md12">
    <div class="layui-form-item">
        <div class="layui-inline">
            <label class="layui-form-label" style="width: auto;">不使用本地邮件服务发送</label>
            <div class="layui-input-inline" style="width: auto;">
                <input type="checkbox" name="email_nolocal" lay-skin="switch" lay-text="是|否"
                    {% if is_true(g.site.email_nolocal) %}checked="checked" {% endif %} autocomplete="off"
                    value="1">
            </div>
        </div>
    </div>
    <div class="layui-form-item">
        <div class="layui-inline">
            <label class="layui-form-label">SaintIC Open</label>
            <div class="layui-input-block">
                <input type="text" name="email_open_token"
                    value="{{ g.site.email_open_token }}" placeholder="Api密钥"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
    </div>
    <fieldset class="layui-elem-field layui-field-title">
        <legend><i class="saintic-icon saintic-icon-info" id="tip-sc" style="font-size:120%"></i> SendCloud</legend>
        <div class="layui-field-box">
            <div class="layui-form-item">
                <label class="layui-form-label">Api User</label>
                <div class="layui-input-block">
                    <input type="text" name="email_sendcloud_apiuser" value="{{ g.site.email_sendcloud_apiuser }}"
                        placeholder="SendCloud.sohu.com API USER" autocomplete="off" class="layui-input">
                </div>
            </div>
            <div class="layui-form-item">
                <label class="layui-form-label">Api Key</label>
                <div class="layui-input-block">
                    <input type="text" name="email_sendcloud_apikey" value="{{ g.site.email_sendcloud_apikey }}"
                        placeholder="SendCloud KEY of API USER" autocomplete="off" class="layui-input">
                </div>
            </div>
            <div class="layui-form-item">
                <label class="layui-form-label">From</label>
                <div class="layui-input-block">
                <input type="text" name="email_sendcloud_from" value="{{ g.site.email_sendcloud_from }}"
                    placeholder="(可选)发件人地址" autocomplete="off" class="layui-input">
                </div>
            </div>
        </div>
    </fieldset>
</div>
'''


def _sendcloud(API_USER, API_KEY, subject, html, to, from_addr, from_name=""):
    url = "https://api.sendcloud.net/apiv2/mail/send"
    data = {
        "apiUser": API_USER,
        "apiKey": API_KEY,
        "from": from_addr,
        "fromName": from_name,
        "to": to.replace(",", ";"),
        "subject": subject,
        "html": html,
    }
    r = try_request(url, data=data)
    return r.json()


def _saintic_open(TOKEN, subject, html, to, from_name=""):
    url = "https://open.saintic.com/api/sendmail"
    data = dict(
        token=TOKEN,
        from_name=from_name,
        to=to,
        subject=subject,
        html=html,
    )
    r = try_request(url, data=data)
    return r.json()


def sendmail(subject, message, to_addr):
    """Web环境下发送邮件"""
    #: from_addr建议设置发件人邮箱，否则基本会被拦截或进入垃圾邮箱
    from_addr = "picbed@{}".format(request.host)
    from_name = g.cfg.email_from_name or g.site_name
    #: 关闭通过本地服务器发送邮件
    no_local = g.cfg.email_nolocal
    if is_true(no_local):
        res = dict(code=1)
    else:
        #: 通过本地邮件服务发送
        mb = Mailbox(from_addr, "", "localhost")
        res = mb.send(subject, message, to_addr, from_name)
        logger.debug("sendmail with localhost: {}".format(res))
    if res["code"] != 0:
        #: 根据钩子配置依次发送邮件，除非某次发送成功
        API_USER = g.cfg.email_sendcloud_apiuser
        API_KEY = g.cfg.email_sendcloud_apikey
        TOKEN = g.cfg.email_open_token
        #: SaintIC Open(open.saintic.com) Email Service(private now)
        if TOKEN:
            res = _saintic_open(TOKEN, subject, message, to_addr, from_name)
            logger.debug("sendmail with saintic open: {}".format(res))
            res.update(method="open")
        #: Sohu(sendcloud.sohu.com) public service
        if res["code"] != 0 and API_USER and API_KEY:
            #: See docs: https://www.sendcloud.net/doc/email_v2/
            _sr = _sendcloud(
                API_USER, API_KEY, subject, message, to_addr,
                g.cfg.email_sendcloud_from or from_addr, from_name
            )
            if is_true(_sr.get("result")):
                res = dict(code=0, data=_sr.get("info"))
            else:
                res = dict(code=_sr.get("statusCode"), msg=_sr.get("message"))
            logger.debug("sendmail with sendcloud: {}".format(res))
            res.update(method="sendcloud")
    else:
        res.update(method="local")
    return res
