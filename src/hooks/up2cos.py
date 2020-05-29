# -*- coding: utf-8 -*-
"""
    up2cos
    ~~~~~~

    Save uploaded pictures in Tencent.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.1.2'
__author__ = 'staugur <staugur@saintic.com>'
__hookname__ = 'up2cos'
__description__ = '将图片保存到腾讯云'
__state__ = 'disabled'
__catalog__ = 'upload'

from flask import g
from posixpath import join
from utils._compat import string_types
from utils.web import set_site_config
from utils.tool import slash_join
from qcloud_cos import CosConfig, CosS3Client


intpl_hooksetting = '''
<fieldset class="layui-elem-field">
    <legend>腾讯云对象存储COS（{% if "up2cos" in g.site.upload_includes %}使用中{% else %}未使用{% endif %}）</legend>
    <div class="layui-field-box">
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 加速域名</label>
            <div class="layui-input-block">
                <input type="url" name="tencent_dn" value="{{ g.site.tencent_dn }}" placeholder="COS服务绑定的加速域名"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> Bucket</label>
            <div class="layui-input-block">
                <input type="text" name="tencent_bucket" value="{{ g.site.tencent_bucket }}" placeholder="COS服务的存储桶名称，例如test-123456789"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> SecretId</label>
            <div class="layui-input-block">
                <input type="text" name="tencent_sid" value="{{ g.site.tencent_sid }}" placeholder="腾讯云个API密钥的SecretId，可以使用RAM用户的密钥"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> SecretKey</label>
            <div class="layui-input-block">
                <input type="password" name="tencent_skey" value="{{ g.site.tencent_skey }}" placeholder="腾讯云API密钥的SecretKey，如果使用RAM请确保有COS管理权限"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">存储根目录</label>
            <div class="layui-input-block">
                <input type="text" name="tencent_basedir" value="{{ g.site.tencent_basedir }}"
                    placeholder="图片存储到腾讯云COS的基础目录，默认是：/（存放到根目录）" autocomplete="off" class="layui-input">
            </div>
        </div>
    </div>
</fieldset>
'''


def get_config(region='ap-beijing'):
    sid = g.cfg.tencent_sid
    skey = g.cfg.tencent_skey
    region = g.cfg.tencent_region or region
    return CosConfig(
        Region=region,
        SecretId=sid,
        SecretKey=skey
    )


def get_buckets(config=None):
    if not config:
        config = get_config()
    client = CosS3Client(config)
    resp = client.list_buckets()
    return {i['Name']: i for i in resp['Buckets']['Bucket']}


def get_bucket_info(bucket, config=None):
    buckets = get_buckets(config)
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
        dn = g.cfg.tencent_dn
        bucket = g.cfg.tencent_bucket
        sid = g.cfg.tencent_sid
        skey = g.cfg.tencent_skey
        tencent_basedir = g.cfg.tencent_basedir or ''
        if not dn or not bucket or not sid or not skey:
            res.update(msg="The tencent parameter error")
            return res
        if isinstance(upload_path, string_types):
            if upload_path.startswith("/"):
                upload_path = upload_path.lstrip('/')
            filepath = join(tencent_basedir, upload_path, filename)
            #: 使用腾讯云云COS官方SDK上传
            config = get_config()
            region = g.cfg.tencent_region
            if not region:
                info = get_bucket_info(bucket, config)
                if info and isinstance(info, dict) and "Location" in info:
                    region = info['Location']
                    config = get_config(region)
                    set_site_config(dict(tencent_region=region))
            client = CosS3Client(config)
            result = client.put_object(
                Bucket=bucket,
                Key=filepath,
                Body=stream,
                EnableMD5=False
            )
            ETag = result['ETag'].replace('"', '')
            if ETag:
                res.update(
                    code=0,
                    etag=ETag,
                    src=slash_join(dn, filepath),
                    basedir=tencent_basedir,
                )
        else:
            res.update(msg="The upload_path type error")
    return res


def upimg_delete(sha, upload_path, filename, basedir, save_result):
    tencent_basedir = g.cfg.tencent_basedir or ''
    filepath = join(basedir or tencent_basedir, upload_path, filename)
    client = CosS3Client(get_config())
    client.delete_object(
        Bucket=g.cfg.tencent_bucket,
        Key=filepath
    )
