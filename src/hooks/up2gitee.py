# -*- coding: utf-8 -*-
"""
    up2gitee
    ~~~~~~~~

    Save uploaded pictures in gitee.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.1.0'
__author__ = 'staugur <staugur@saintic.com>'
__hookname__ = 'up2gitee'
__description__ = '将图片保存到Gitee'
__state__ = 'disabled'
__catalog__ = 'upload'

import requests
from flask import g
from posixpath import join
from base64 import b64encode
from utils.tool import slash_join, try_request
from utils._compat import string_types


intpl_localhooksetting = '''
<div class="layui-col-xs12 layui-col-sm12 layui-col-md6">
<fieldset class="layui-elem-field layui-field-title">
    <legend>Gitee版本库（{% if "up2gitee" in g.site.upload_includes %}使用中{% else %}未使用{% endif %}）</legend>
    <div class="layui-field-box">
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 私人令牌</label>
            <div class="layui-input-block">
                <input type="text" name="gitee_token" value="{{ g.site.gitee_token }}" placeholder="Gitee私人令牌（projects权限）"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 仓库名</label>
            <div class="layui-input-block">
                <input type="text" name="gitee_repo" value="{{ g.site.gitee_repo }}" placeholder="公开仓库，格式：用户名/仓库名"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">分支</label>
            <div class="layui-input-block">
                <input type="text" name="gitee_branch" value="{{ g.site.gitee_branch }}" placeholder="仓库分支，留空则使用仓库默认分支"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">存储根目录</label>
            <div class="layui-input-block">
                <input type="text" name="gitee_basedir" value="{{ g.site.gitee_basedir }}"
                    placeholder="图片存储到仓库的基础目录，默认是根目录" autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">自定义域名</label>
            <div class="layui-input-block">
                <input type="url" name="gitee_dn" value="{{ g.site.gitee_dn }}" placeholder="访问仓库的域名"
                    autocomplete="off" class="layui-input">
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
        token = g.cfg.gitee_token
        repo = g.cfg.gitee_repo
        branch = g.cfg.gitee_branch
        dn = g.cfg.gitee_dn
        gitee_basedir = g.cfg.gitee_basedir or '/'
        if not token or not repo or "/" not in repo:
            res.update(msg="The gitee parameter error")
            return res
        if isinstance(upload_path, string_types):
            if upload_path.startswith("/"):
                upload_path = upload_path.lstrip('/')
            if gitee_basedir.startswith("/"):
                gitee_basedir = gitee_basedir.lstrip('/')
            saveto = join(gitee_basedir, upload_path)
            filepath = join(saveto, filename)
            #: 通过API上传图片
            data = dict(
                message="Create %s by picbed" % filepath,
                content=b64encode(stream).decode("utf-8"),
                access_token=token,
            )
            if branch:
                data["branch"] = branch
            headers = {
                "User-Agent": "picbed-up2gitee/%s" % __version__,
            }
            try:
                r = try_request(
                    "https://gitee.com/api/v5/repos/%s/contents/%s" % (
                        repo, filepath
                    ),
                    data=data,
                    headers=headers,
                    timeout=30,
                    method="post"
                )
            except requests.exceptions.RequestException as e:
                res.update(msg=e)
            else:
                result = r.json()
                if r.status_code == 201:
                    content = result["content"]
                    src = content["download_url"]
                    if dn:
                        src = slash_join(dn, filepath)
                    res.update(
                        code=0,
                        src=src,
                        basedir=gitee_basedir,
                        branch=branch,
                        size=content["size"],
                        content_sha=content["sha"],
                        download_url=content["download_url"],
                        repo=repo,
                    )
                else:
                    res.update(
                        code=r.status_code,
                        msg=result.get("message", "").replace(
                            '"', '\''
                        ).replace('\n\n', ' ').replace('\n', '').replace(
                            '\\', ''
                        ),
                    )
        else:
            res.update(msg="The upload_path type error")
    return res


def upimg_delete(sha, upload_path, filename, basedir, save_result):
    content_sha = save_result["content_sha"]
    #: 图片保存时所在的branch
    branch = save_result["branch"]
    repo = save_result["repo"]
    if content_sha:
        token = g.cfg.gitee_token
        gitee_basedir = g.cfg.gitee_basedir or '/'
        if gitee_basedir.startswith("/"):
            gitee_basedir = gitee_basedir.lstrip('/')
        filepath = join(basedir or gitee_basedir, upload_path, filename)
        params = dict(
            message="Delete %s by picbed" % filepath,
            sha=content_sha,
            access_token=token,
        )
        if branch:
            params["branch"] = branch
        headers = {
            "User-Agent": "picbed-up2gitee/%s" % __version__,
        }
        try_request(
            "https://gitee.com/api/v5/repos/%s/contents/%s" % (
                repo, filepath
            ),
            params=params,
            headers=headers,
            timeout=10,
            method="delete",
        )
