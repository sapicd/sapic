# -*- coding: utf-8 -*-
"""
    cli
    ~~~

    Cli Entrance

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import json
import click
from flask.cli import AppGroup
from redis.exceptions import RedisError
from werkzeug.security import generate_password_hash
from libs.storage import get_storage
from .tool import rsp, get_current_timestamp, create_redis_engine, is_true, \
    parse_ua
from .web import check_username, _pip_install


def echo(msg, color=None):
    click.echo(click.style(msg, fg=color))


def exec_createuser(username, password, **kwargs):
    """创建账号"""
    ak = rsp("accounts")
    username = username.lower()
    if check_username(username):
        if not password or len(password) < 6:
            echo("密码最少6位", "yellow")
        else:
            rc = create_redis_engine()
            if rc.sismember(ak, username):
                echo("用户名已存在", "red")
            else:
                is_admin = kwargs.pop("is_admin", 0)
                uk = rsp("account", username)
                pipe = rc.pipeline()
                pipe.sadd(ak, username)
                if kwargs:
                    pipe.hmset(uk, kwargs)
                pipe.hmset(uk, dict(
                    username=username,
                    password=generate_password_hash(password),
                    is_admin=1 if is_true(is_admin) else 0,
                    ctime=get_current_timestamp(),
                    status=1,
                ))
                try:
                    pipe.execute()
                except RedisError as e:
                    echo(e, "red")
                else:
                    echo("注册成功！", "green")
                finally:
                    rc.connection_pool.disconnect()
    else:
        echo("用户名不合法或不允许注册", "yellow")


sa_cli = AppGroup(
    'sa',
    help='Administrator commands',
    context_settings={'help_option_names': ['-h', '--help']},
)


@sa_cli.command()
@click.option('--username', '-u', type=str, required=True, help=u'用户名')
@click.option('--password', '-p', type=str, required=True, help=u'用户密码')
@click.option('--isAdmin/--no-isAdmin', default=False,
              help=u'是否为管理员', show_default=True)
@click.option('--avatar', '-a', type=str, default='', help=u'头像地址')
@click.option('--nickname', '-n', type=str, default='', help=u'昵称')
def create(username, password, isadmin, avatar, nickname):
    """创建账号"""
    exec_createuser(
        username,
        password,
        is_admin=isadmin,
        avatar=avatar,
        nickname=nickname,
    )


@sa_cli.command()
@click.option('--HookLoadTime/--no-HookLoadTime', default=False,
              help=u'删除钩子加载时间', show_default=True)
@click.option('--HookThirds/--no-HookThirds', default=False,
              help=u'删除已加载的第三方钩子', show_default=True)
@click.option('--InvalidKey/--no-InvalidKey', default=False,
              help=u'删除无效的Redis键', show_default=True)
def clean(hookloadtime, hookthirds, invalidkey):
    """清理系统"""
    if hookloadtime:
        s = get_storage()
        del s['hookloadtime']
    if hookthirds:
        s = get_storage()
        del s['hookthirds']
    if invalidkey:
        rc = create_redis_engine()
        ius = rc.keys(rsp("index", "user", "*"))
        pipe = rc.pipeline()
        for uk in ius:
            us = rc.smembers(uk)
            for sha in us:
                if not rc.exists(rsp("image", sha)):
                    pipe.srem(uk, sha)
        try:
            pipe.execute()
        except RedisError:
            pass


@sa_cli.command()
@click.confirmation_option(prompt=u'确定要升级更新吗？')
@click.argument('v2v', type=click.Choice(['1.6-1.7', '1.7-1.8']))
def upgrade(v2v):
    """版本升级助手"""
    #: 处理更新版本时数据迁移、数据结构变更、其他修改
    rc = create_redis_engine()

    if v2v == "1.6-1.7":
        #: 安装模块
        try:
            from user_agents import parse
        except ImportError:
            _pip_install("user_agents>=2.0")
        #: 更新数据
        pipe = rc.pipeline()
        #: 添加用户status
        for u in rc.smembers(rsp("accounts")):
            pipe.hmget(rsp("account", u), "username", "status")
        usrdat = pipe.execute()
        for i in usrdat:
            if i[1] is None:
                pipe.hset(rsp("account", i[0]), "status", 1)
        pipe.execute()
        #: 调整linktoken字段
        rls = rc.keys(rsp("report", "linktokens", "*"))
        for k in rls:
            data = rc.lrange(k, 0, -1)
            new = []
            is_update = False
            for d in data:
                d = json.loads(d)
                if "uap" not in d:
                    is_update = True
                    d["uap"] = parse_ua(d["agent"])
                new.append(json.dumps(d))
            if is_update:
                pipe.delete(k)
                pipe.rpush(k, *new)
        pipe.execute()
        #: 调整img详情字段
        uporigins = ("homepage", "cli", "userscript", "uploader.js")
        for sha in rc.smembers(rsp("index", "global")):
            pipe.hmget(rsp("image", sha), "sha", "agent")
        ukdat = pipe.execute()
        for i in ukdat:
            agent = i[1]
            if agent:
                if agent.split("/")[0] in uporigins:
                    o = agent
                else:
                    o = "UA: %s" % agent
                pipe.hdel(rsp("image", i[0]), "agent")
                pipe.hset(rsp("image", i[0]), "origin", o)
        pipe.execute()

    elif v2v == "1.7-1.8":
        #: 安装模块
        try:
            from bleach import clean
        except ImportError:
            _pip_install("bleach>2.0.0")
        try:
            import semver
        except ImportError:
            _pip_install("semver>=2.9.1,<3")
        #: 清除已删除的图片key
        dk = rsp("index", "deleted")
        if rc.exists(dk):
            pipe = rc.pipeline()
            for sha in rc.smembers(dk):
                pipe.delete(rsp("image", sha))
            pipe.delete(dk)
            pipe.execute()
