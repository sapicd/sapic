# -*- coding: utf-8 -*-
"""
    config
    ~~~~~~~

    The program configuration file, the preferred configuration item,
    reads the system environment variable first.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from os import getenv, environ
from os.path import isfile, dirname, join
from utils._compat import iteritems, Properties

#: TODO modify environ, memory oom
ENV = join(dirname(__file__), ".cfg")
if isfile(ENV):
    envs = Properties(ENV).getProperties()
    if envs and isinstance(envs, dict):
        for k, v in iteritems(envs):
            if k and v:
                environ[k] = v

GLOBAL = {

    "ProcessName": "picbed",
    # 自定义进程名.

    "Host": getenv("picbed_host", "127.0.0.1"),
    # 监听地址

    "Port": int(getenv("picbed_port", 9514)),
    # 监听端口

    "LogLevel": getenv("picbed_loglevel", "DEBUG"),
    # 应用日志记录级别, 依次为 DEBUG, INFO, WARNING, ERROR, CRITICAL.

    "HookReloadTime": int(getenv("picbed_hookreloadtime", 600)),
    # 钩子管理器默认重载时间，单位：秒

    "SecretKey": getenv("picbed_secretkey"),
    # Web应用密钥，默认随机。如果设置，那么登录态cookie在重启应用后仍有效。
}


#: 存储上传图片的数据，使用redis单实例，请开启持久化!
REDIS = getenv("picbed_redis_url")
# Redis数据库连接信息，格式:
# redis://[:password]@host:port/db
# host,port必填项,如有密码,记得密码前加冒号


#: 存储一些非核心数据的相关设置
STORAGE = {

    "Method": getenv("picbed_storage_method", "redis"),
    #: 存储方法，目前支持: local, redis

    "LocalPath": getenv("picbed_storage_local_path"),
    #: 当存储方法为local时此值有效，格式: path
    #: -- path总是建议为绝对目录，默认为: SysTempDir/picbed.dat

    "RedisURL": getenv("picbed_storage_redis_url") or REDIS,
    #: 当存储方法为redis时此值有效，格式参考REDIS
    #: -- 仅使用redis单库的一个hash，默认为: picbed:dat
}
