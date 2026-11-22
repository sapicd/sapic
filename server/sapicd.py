# -*- coding: utf-8 -*-
"""Gunicorn config for the container (``gunicorn -c sapicd.py sapic:create_app()``).

Gunicorn treats every public name in this module as a config key, so helpers
and imported modules must use underscore aliases (same convention as openhub's
``hub.py``). Keep the file at ``server/`` next to the app: supervisor chdirs
there before starting gunicorn.
"""

import os as _os

from sapic.basis.conf import load_config as _load_config

_config = _load_config()

#: nginx 反代到这里；SAPIC_HTTP_PORT 是 nginx 的对外端口，两者不能混用。
bind = _os.environ.get("SAPIC_GUNICORN_BIND", "127.0.0.1:9514")
#: 进程数来自 sapic.basis.conf（sapic_workers / server/.cfg 的 WORKERS），已校验 >= 1。
workers = _config["WORKERS"]
worker_class = "gevent"
worker_connections = 1000
max_requests = 10000
#: setproctitle（prod.txt）装上后，ps 里是 `gunicorn: master [sapic]` / `worker [sapic]`。
proc_name = "sapic"
#: supervisor 需要前台进程，交给它来收 SIGTERM 并有序停 worker。
daemon = False
loglevel = _config["LOG_LEVEL"].lower()
accesslog = None
errorlog = "-"
timeout = 60
if _os.path.isdir("/dev/shm"):
    worker_tmp_dir = "/dev/shm"
