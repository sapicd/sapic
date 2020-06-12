# -*- coding: utf-8 -*-
"""
    up2oss
    ~~~~~~

    Save uploaded pictures in Aliyun.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.1.3'
__author__ = 'staugur <staugur@saintic.com>'
__hookname__ = 'up2oss'
__description__ = '将图片保存到阿里云'
__state__ = 'disabled'
__catalog__ = 'upload'

from flask import g
from posixpath import join
from oss2 import Auth, Service, Bucket, BucketIterator
from utils._compat import string_types
from utils.web import set_site_config
from utils.tool import slash_join


intpl_hooksetting = '''
<div class="layui-col-xs12 layui-col-sm12 layui-col-md6">
<fieldset class="layui-elem-field">
    <legend>阿里云对象存储OSS（{% if "up2oss" in g.site.upload_includes %}使用中{% else %}未使用{% endif %}）</legend>
    <div class="layui-field-box">
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 用户域名</label>
            <div class="layui-input-block">
                <input type="url" name="aliyun_dn" value="{{ g.site.aliyun_dn }}" placeholder="OSS服务绑定的用户域名"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> Bucket</label>
            <div class="layui-input-block">
                <input type="text" name="aliyun_bucket" value="{{ g.site.aliyun_bucket }}" placeholder="OSS服务的存储空间名称"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> AccessKeyID</label>
            <div class="layui-input-block">
                <input type="text" name="aliyun_ak" value="{{ g.site.aliyun_ak }}" placeholder="阿里云个人密钥的ID，支持有OSS管理权限的RAM账号" autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> SecretKey</label>
            <div class="layui-input-block">
                <input type="password" name="aliyun_sk" value="{{ g.site.aliyun_sk }}" placeholder="阿里云个人密钥的Secret，RAM需勾选编程访问" autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">存储根目录</label>
            <div class="layui-input-block">
                <input type="text" name="aliyun_basedir" value="{{ g.site.aliyun_basedir }}"
                    placeholder="图片存储到阿里云OSS的基础目录，默认是根目录" autocomplete="off" class="layui-input">
            </div>
        </div>
    </div>
</fieldset>
</div>
'''


def get_auth():
    ak = g.cfg.aliyun_ak
    sk = g.cfg.aliyun_sk
    return Auth(ak, sk)


def get_buckets(auth=None):
    if not auth:
        auth = get_auth()
    service = Service(auth, 'https://oss.aliyuncs.com')
    return {
        i.name: dict(
            name=i.name,
            endpoint=i.extranet_endpoint,
            location=i.location
        )
        for i in BucketIterator(service)
    }


def get_bucket_info(bucket, auth=None):
    buckets = get_buckets(auth)
    return buckets.get(bucket)


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
        dn = g.cfg.aliyun_dn
        bucket = g.cfg.aliyun_bucket
        ak = g.cfg.aliyun_ak
        sk = g.cfg.aliyun_sk
        aliyun_basedir = g.cfg.aliyun_basedir or ''
        if not dn or not bucket or not ak or not sk:
            res.update(msg="The aliyun parameter error")
            return res
        if isinstance(upload_path, string_types):
            if upload_path.startswith("/"):
                upload_path = upload_path.lstrip('/')
            if aliyun_basedir.startswith("/"):
                aliyun_basedir = aliyun_basedir.lstrip('/')
            filepath = join(aliyun_basedir, upload_path, filename)
            #: 使用阿里云云OSS官方SDK上传
            auth = get_auth()
            endpoint = g.cfg.aliyun_endpoint
            if not endpoint:
                info = get_bucket_info(bucket, auth)
                if info and isinstance(info, dict) and "endpoint" in info:
                    endpoint = info['endpoint']
                    set_site_config(dict(aliyun_endpoint=endpoint))
            obj = Bucket(auth, endpoint, bucket)
            result = obj.put_object(filepath, stream)
            if result.status == 200:
                res.update(
                    code=0,
                    etag=result.etag,
                    src=slash_join(dn, filepath),
                    basedir=aliyun_basedir,
                )
        else:
            res.update(msg="The upload_path type error")
    return res


def upimg_delete(sha, upload_path, filename, basedir, save_result):
    auth = get_auth()
    obj = Bucket(auth, g.cfg.aliyun_endpoint, g.cfg.aliyun_bucket)
    aliyun_basedir = g.cfg.aliyun_basedir or ''
    if aliyun_basedir.startswith("/"):
        aliyun_basedir = aliyun_basedir.lstrip('/')
    filepath = join(basedir or aliyun_basedir, upload_path, filename)
    obj.delete_object(filepath)
