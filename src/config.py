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
from utils._compat import Properties, is_true

envs = Properties(join(dirname(__file__), ".cfg"), from_env=True)


GLOBAL = {
    "ProcessName": "sapic",
    # 自定义进程名(setproctitle)
    "Host": envs.get("sapic_host", "0.0.0.0"),
    # 监听地址
    "Port": int(envs.get("sapic_port", 9514)),
    # 监听端口
    "LogLevel": envs.get("sapic_loglevel", "DEBUG"),
    # 应用日志记录级别, 依次为 DEBUG, INFO, WARNING, ERROR, CRITICAL.
    "HookReloadTime": int(envs.get("sapic_hookreloadtime", 600)),
    # 钩子管理器默认重载时间，单位：秒
    "SecretKey": envs.get(
        "sapic_secretkey",
        "BD1E2CF7DF9CD6971D641C115EE72871BEDA2806",
    ),
    # Web应用固定密钥
    "MaxUpload": int(envs.get("sapic_maxupload", 20)),
    # 上传最大容量限制，单位MB
    "ProxyFix": is_true(envs.get("sapic_proxyfix")),
    # 信任代理标头
    "AllowTags": envs.get("sapic_allowtags", ""),
    # 站点设置部分参数额外允许的HTML标签的属性
    "AllowStyles": envs.get("sapic_allowstyles", ""),
    # 站点设置部分参数额外允许的HTML标签的样式
    "HookPkgStorageDir": "",
    # 第三方扩展包持久化目录
}


#: 存储核心数据，使用redis单实例，请开启AOF持久化!
REDIS = envs.get("sapic_redis_url")
# Redis数据库连接信息，格式:
# redis://[:password]@host:port/db
# host,port必填项,如有密码,记得密码前加冒号


if __name__ == "__main__":
    from json import dumps

    print(
        dumps(
            {
                "global": GLOBAL,
                "redis": REDIS,
            },
            indent=4,
        )
    )
