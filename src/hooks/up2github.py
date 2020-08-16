# -*- coding: utf-8 -*-
"""
    up2github
    ~~~~~~~~~

    Save uploaded pictures in github.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = '0.1.1'
__author__ = 'staugur <staugur@saintic.com>'
__hookname__ = 'up2github'
__description__ = '将图片保存到GitHub'
__state__ = 'disabled'
__catalog__ = 'upload'

import json
import requests
from flask import g
from posixpath import join
from base64 import b64encode
from utils.tool import slash_join, is_true
from utils.web import try_proxy_request
from utils._compat import string_types


intpl_localhooksetting = '''
<div class="layui-col-xs12 layui-col-sm12 layui-col-md6">
<fieldset class="layui-elem-field layui-field-title">
    <legend>GitHub版本库（{% if "up2github" in g.site.upload_includes %}使用中{% else %}未使用{% endif %}）</legend>
    <div class="layui-field-box">
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> Token</label>
            <div class="layui-input-block">
                <input type="text" name="github_token" value="{{ g.site.github_token }}" placeholder="GitHub personal access tokens(repo scopes)"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label"><b style="color: red;">*</b> 仓库名</label>
            <div class="layui-input-block">
                <input type="text" name="github_repo" value="{{ g.site.github_repo }}" placeholder="公开仓库，格式：用户名/仓库名"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">分支</label>
            <div class="layui-input-block">
                <input type="text" name="github_branch" value="{{ g.site.github_branch }}" placeholder="仓库分支，留空则使用仓库默认分支"
                    autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <label class="layui-form-label">存储根目录</label>
            <div class="layui-input-block">
                <input type="text" name="github_basedir" value="{{ g.site.github_basedir }}"
                    placeholder="图片存储到仓库的基础目录，默认是根目录" autocomplete="off" class="layui-input">
            </div>
        </div>
        <div class="layui-form-item">
            <div class="layui-inline" style="margin-bottom:0px">
                <label class="layui-form-label">自定义域名</label>
                <div class="layui-input-inline">
                    <input type="url" name="github_dn" value="{{ g.site.github_dn }}" placeholder="访问仓库的域名或使用JsDelivr"
                        autocomplete="off" class="layui-input" {% if is_true(g.site.github_jsdelivr) %}disabled="disabled" class="layui-disabled"{% endif %}>
                </div>
            </div>
            <div class="layui-inline">
                <div class="layui-input-inline" style="width:auto">
                    <input type="checkbox" name="github_jsdelivr" title="JsDelivr" lay-filter="jsdelivr"
                        {% if is_true(g.site.github_jsdelivr) %}checked="checked" {% endif %} autocomplete="off"
                        value="1">
                </div>
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
        token = g.cfg.github_token
        repo = g.cfg.github_repo
        branch = g.cfg.github_branch
        dn = g.cfg.github_dn
        github_basedir = g.cfg.github_basedir or '/'
        if not token or not repo or "/" not in repo:
            res.update(msg="The github parameter error")
            return res
        if isinstance(upload_path, string_types):
            if upload_path.startswith("/"):
                upload_path = upload_path.lstrip('/')
            if github_basedir.startswith("/"):
                github_basedir = github_basedir.lstrip('/')
            saveto = join(github_basedir, upload_path)
            filepath = join(saveto, filename)
            #: 通过API上传图片
            data = dict(
                message="Create %s by picbed" % filepath,
                content=b64encode(stream).decode("utf-8"),
            )
            if branch:
                data["branch"] = branch
            headers = {
                "User-Agent": "picbed-up2github/%s" % __version__,
                "Authorization": "token %s" % token
            }
            try:
                r = try_proxy_request(
                    "https://api.github.com/repos/%s/contents/%s" % (
                        repo, filepath
                    ),
                    data=json.dumps(data),
                    headers=headers,
                    timeout=30,
                    method="put"
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
                    elif is_true(g.cfg.github_jsdelivr):
                        src = slash_join(
                            "https://cdn.jsdelivr.net/gh/",
                            repo,
                            filepath
                        )
                    res.update(
                        code=0,
                        src=src,
                        basedir=github_basedir,
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
        token = g.cfg.github_token
        github_basedir = g.cfg.github_basedir or '/'
        if github_basedir.startswith("/"):
            github_basedir = github_basedir.lstrip('/')
        filepath = join(basedir or github_basedir, upload_path, filename)
        data = dict(
            message="Delete %s by picbed" % filepath,
            sha=content_sha,
        )
        if branch:
            data["branch"] = branch
        headers = {
            "User-Agent": "picbed-up2github/%s" % __version__,
            "Authorization": "token %s" % token
        }
        try_proxy_request(
            "https://api.github.com/repos/%s/contents/%s" % (
                repo, filepath
            ),
            data=json.dumps(data),
            headers=headers,
            timeout=10,
            method="delete",
        )
