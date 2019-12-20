#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    cli
    ~~~

    Cli Entrance

    :copyright: (c) 2020 by staugur.
    :license: MIT, see LICENSE for more details.
"""

import sys
import getpass
from redis.exceptions import RedisError
from utils.tool import rsp, get_current_timestamp, create_redis_engine
from utils.web import check_username
from utils._compat import raw_input
from werkzeug.security import generate_password_hash


def echo(msg, color=None):
    if color == "green":
        print('\033[92m{}\033[0m'.format(msg))
    elif color == "blue":
        print('\033[94m{}\033[0m'.format(msg))
    elif color == "yellow":
        print('\033[93m{}\033[0m'.format(msg))
    elif color == "red":
        print('\033[91m{}\033[0m'.format(msg))
    else:
        print(msg)


def exec_createSuperuser():
    """创建管理员账号"""
    ak = rsp("account")
    try:
        echo("请根据提示输入信息以创建管理员账号", "blue")
        username = raw_input("请输入管理员用户名：")
        password = getpass.getpass("请输入管理员密码：")
        repasswd = getpass.getpass("请确认管理员密码：")
    except KeyboardInterrupt:
        sys.stdout.write('\n')
        exit(1)
    else:
        if check_username(username):
            if not password or len(password) < 6:
                echo("密码最少6位", "yellow")
            elif password != repasswd:
                echo("两次密码不一致", "yellow")
            else:
                rc = create_redis_engine()
                if rc.sismember(ak, username):
                    echo("用户名已存在", "red")
                else:
                    pipe = rc.pipeline()
                    pipe.sadd(ak, username)
                    pipe.hmset(rsp("user", username), dict(
                        username=username,
                        password=generate_password_hash(password),
                        is_admin=1,
                        ctime=get_current_timestamp()
                    ))
                    try:
                        pipe.execute()
                    except RedisError as e:
                        echo(e.message, "red")
                    else:
                        echo(
                            "注册成功，账号是<%s>，密码是<%s>，请妥善保管！"
                            % (username, password),
                            "green"
                        )
                    finally:
                        rc.connection_pool.disconnect()
        else:
            echo("用户名不合法或不允许注册", "yellow")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-sa", "--createSuperuser", help=u"创建管理员用户",
                        default=False, action='store_true')
    args = parser.parse_args()
    createSuperuser = args.createSuperuser
    if createSuperuser:
        exec_createSuperuser()
    else:
        parser.print_help()
