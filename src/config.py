# -*- coding: utf-8 -*-
"""
    config
    ~~~~~~~

    The program configuration file, the preferred configuration item,
    reads the system environment variable first.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from os.path import dirname, join
from utils._compat import Properties

envs = Properties(join(dirname(__file__), ".cfg"), from_env=True)


GLOBAL = {

    "ProcessName": "picbed",
    # 自定义进程名(setproctitle)

    "Host": envs.get("picbed_host", "127.0.0.1"),
    # 监听地址

    "Port": int(envs.get("picbed_port", 9514)),
    # 监听端口

    "LogLevel": envs.get("picbed_loglevel", "DEBUG"),
    # 应用日志记录级别, 依次为 DEBUG, INFO, WARNING, ERROR, CRITICAL.

    "HookReloadTime": int(envs.get("picbed_hookreloadtime", 600)),
    # 钩子管理器默认重载时间，单位：秒

    "SecretKey": envs.get(
        "picbed_secretkey", "BD1E2CF7DF9CD6971D641C115EE72871BEDA2806"
    ),
    # Web应用固定密钥
}


#: 存储核心数据，使用redis单实例，请开启AOF持久化!
REDIS = envs.get("picbed_redis_url")
# Redis数据库连接信息，格式:
# redis://[:password]@host:port/db
# host,port必填项,如有密码,记得密码前加冒号
#
# v1.6.0支持redis cluster集群连接，格式：
# rediscluster://host:port,host:port...


#: 存储一些非核心数据的相关设置
STORAGE = {

    "Method": envs.get("picbed_storage_method", "redis"),
    #: 存储方法，目前支持: local, redis(rediscluster)

    "LocalPath": envs.get("picbed_storage_local_path"),
    #: 当存储方法为local时此值有效，格式: path
    #: -- path总是建议为绝对目录，默认为: SysTempDir/picbed.dat

    "RedisURL": envs.get("picbed_storage_redis_url") or REDIS,
    #: 当存储方法为redis时此值有效，格式参考REDIS
    #: -- 仅使用redis单库的一个hash，默认为: picbed:dat
}
