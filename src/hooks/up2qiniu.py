# -*- coding: utf-8 -*-
"""
    up2qiniu
    ~~~~~~~~

    Save uploaded pictures in Qiniu.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.2.2'
__author__ = 'staugur <staugur@saintic.com>'
__hookname__ = 'up2qiniu'
__description__ = '将图片保存到七牛云'
__state__ = 'disabled'
__catalog__ = 'upload'

from flask import g
from posixpath import join
from utils._compat import string_types
from utils.tool import slash_join

intpl_localhooksetting = '''
<div class="layui-col-xs12 layui-col-sm12 layui-col-md6">
<fieldset class="layui-elem-field layui-field-title">
    <legend>七牛云存储（{% if "up2qiniu" in g.site.upload_includes %}使用中{% else %}未使用{% endif %}）</legend>
    <div class="layui-field-box">
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 加速域名</label>
            <div class="layui-input-block">
                <input type="url" name="qiniu_dn" value="{{ g.site.qiniu_dn }}" placeholder="云存储服务的加速域名"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> Bucket</label>
            <div class="layui-input-block">
                <input type="text" name="qiniu_bucket" value="{{ g.site.qiniu_bucket }}" placeholder="云存储服务的名称"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> AccessKey</label>
            <div class="layui-input-block">
                <input type="text" name="qiniu_ak" value="{{ g.site.qiniu_ak }}" placeholder="七牛云个人密钥的AK"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> SecretKey</label>
            <div class="layui-input-block">
                <input type="password" name="qiniu_sk" value="{{ g.site.qiniu_sk }}" placeholder="七牛云个人密钥的SK"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">存储根目录</label>
            <div class="layui-input-block">
                <input type="text" name="qiniu_basedir" value="{{ g.site.qiniu_basedir }}"
                    placeholder="图片存储到七牛云的基础目录，默认是根目录" autocomplete="off" class="layui-input">
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
            from qiniu import Auth, put_data
        except ImportError:
            res.update(msg="Please install qiniu module")
            return res
        dn = g.cfg.qiniu_dn
        bucket = g.cfg.qiniu_bucket
        ak = g.cfg.qiniu_ak
        sk = g.cfg.qiniu_sk
        qiniu_basedir = g.cfg.qiniu_basedir or ''
        if not dn or not bucket or not ak or not sk:
            res.update(msg="The qiniu parameter error")
            return res
        if isinstance(upload_path, string_types):
            if upload_path.startswith("/"):
                upload_path = upload_path.lstrip('/')
            if qiniu_basedir.startswith("/"):
                qiniu_basedir = qiniu_basedir.lstrip('/')
            saveto = join(qiniu_basedir, upload_path)
            filepath = join(saveto, filename)
            #: 使用七牛云SDK上传
            qn = Auth(ak, sk)
            token = qn.upload_token(bucket, filepath, 60)
            ret, info = put_data(token, filepath, stream)
            if info.ok():
                res.update(ret)
                res.update(
                    code=0,
                    src=slash_join(dn, filepath),
                    basedir=qiniu_basedir,
                )
        else:
            res.update(msg="The upload_path type error")
    return res


def upimg_delete(sha, upload_path, filename, basedir, save_result):
    try:
        from qiniu import Auth, BucketManager
    except ImportError:
        raise ImportError("Please install qiniu module")
    else:
        ak = g.cfg.qiniu_ak
        sk = g.cfg.qiniu_sk
        qn = Auth(ak, sk)
        bm = BucketManager(qn)
        bucket = g.cfg.qiniu_bucket
        qiniu_basedir = g.cfg.qiniu_basedir or ''
        if qiniu_basedir.startswith("/"):
            qiniu_basedir = qiniu_basedir.lstrip('/')
        filepath = join(basedir or qiniu_basedir, upload_path, filename)
        bm.delete(bucket, filepath)
