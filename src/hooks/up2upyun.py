# -*- coding: utf-8 -*-
"""
    up2upyun
    ~~~~~~~~

    Save uploaded pictures in Upyun.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.2.1'
__author__ = 'staugur <staugur@saintic.com>'
__hookname__ = 'up2upyun'
__description__ = '将图片保存到又拍云'
__state__ = 'disabled'
__catalog__ = 'upload'

from os.path import join
from flask import g
from utils._compat import string_types
from utils.tool import slash_join

intpl_localhooksetting = '''
<div class="layui-col-xs12 layui-col-sm12 layui-col-md6">
<fieldset class="layui-elem-field layui-field-title">
    <legend>又拍云存储（{% if "up2upyun" in g.site.upload_includes %}使用中{% else %}未使用{% endif %}）</legend>
    <div class="layui-field-box">
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 加速域名</label>
            <div class="layui-input-block">
                <input type="url" name="upyun_dn" value="{{ g.site.upyun_dn }}" placeholder="云存储服务的加速域名"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> Bucket</label>
            <div class="layui-input-block">
                <input type="text" name="upyun_bucket" value="{{ g.site.upyun_bucket }}" placeholder="云存储服务的名称"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 操作员</label>
            <div class="layui-input-block">
                <input type="text" name="upyun_username" value="{{ g.site.upyun_username }}" placeholder="云存储操作员账号（具有读写删除权限）"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 密码</label>
            <div class="layui-input-block">
                <input type="password" name="upyun_password" value="{{ g.site.upyun_password }}" placeholder="云存储操作员密码"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">存储根目录</label>
            <div class="layui-input-block">
                <input type="text" name="upyun_basedir" value="{{ g.site.upyun_basedir }}"
                    placeholder="图片存储到又拍云的基础目录，默认是根目录" autocomplete="off" class="layui-input">
            </div>
        </div>
    </div>
</fieldset>
</div>
'''


def upimg_save(**kwargs):
    res = dict(code=1)
    try:
        filename = kwargs["filename"]
        stream = kwargs["stream"]
        upload_path = kwargs.get("upload_path") or ""
        if not filename or not stream:
            return ValueError
    except (KeyError, ValueError):
        res.update(msg="Parameter error")
    else:
        try:
            from upyun import UpYun, ED_AUTO
        except ImportError:
            res.update(msg="Please install upyun module")
            return res
        dn = g.cfg.upyun_dn
        bucket = g.cfg.upyun_bucket
        user = g.cfg.upyun_username
        passwd = g.cfg.upyun_password
        upyun_basedir = g.cfg.upyun_basedir or '/'
        if not dn or not bucket or not user or not passwd:
            res.update(msg="The upyun parameter error")
            return res
        if isinstance(upload_path, string_types):
            if upload_path.startswith("/"):
                upload_path = upload_path.lstrip('/')
            if not upyun_basedir.startswith("/"):
                upyun_basedir = "/%s" % upyun_basedir
            saveto = join(upyun_basedir, upload_path)
            filepath = join(saveto, filename)
            up = UpYun(bucket, user, passwd, timeout=30, endpoint=ED_AUTO)
            res.update(up.put(filepath, stream))
            res.update(
                code=0,
                src=slash_join(dn, filepath),
                basedir=upyun_basedir,
            )
        else:
            res.update(msg="The upload_path type error")
    return res


def upimg_delete(sha, upload_path, filename, basedir, save_result):
    try:
        from upyun import UpYun, ED_AUTO
    except ImportError:
        raise ImportError("Please install upyun module")
    else:
        bucket = g.cfg.upyun_bucket
        user = g.cfg.upyun_username
        passwd = g.cfg.upyun_password
        upyun_basedir = g.cfg.upyun_basedir or '/'
        if not upyun_basedir.startswith("/"):
            upyun_basedir = "/%s" % upyun_basedir
        up = UpYun(bucket, user, passwd, timeout=10, endpoint=ED_AUTO)
        filepath = join(basedir or upyun_basedir, upload_path, filename)
        up.delete(filepath)
