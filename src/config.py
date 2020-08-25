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

    "MaxUpload": int(envs.get("picbed_maxupload", 20)),
    # 上传最大尺寸，单位MB
}


#: 存储核心数据，使用redis单实例，请开启AOF持久化!
REDIS = envs.get("picbed_redis_url")
# Redis数据库连接信息，格式:
# redis://[:password]@host:port/db
# host,port必填项,如有密码,记得密码前加冒号
#
# v1.6.0支持redis cluster集群连接，格式：
# rediscluster://host:port,host:port...


if __name__ == "__main__":
    from json import dumps
    print(dumps(
        {
            "global": GLOBAL,
            "redis": REDIS,
        },
        indent=4
    ))
