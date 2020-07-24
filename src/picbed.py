# picbed gunicorn config

from os.path import abspath, dirname, join, exists
from os import getenv, mkdir
from multiprocessing import cpu_count
from config import GLOBAL

IS_RUN = True if getenv("picbed_isrun") == "true" else False
LOGSDIR = join(dirname(abspath(__file__)), "logs")
if not exists(LOGSDIR):
    mkdir(LOGSDIR)

bind = "{}:{}".format(GLOBAL['Host'], GLOBAL['Port'])
proc_name = GLOBAL['ProcessName']
workers = cpu_count() * 2 + 1
worker_class = "gevent"
threads = 10

if IS_RUN:
    daemon = False

else:
    daemon = True
    pidfile = join(LOGSDIR, "{}.pid".format(proc_name))
    loglevel = 'info'
    errorlog = join(LOGSDIR, "gunicorn.log")
    accesslog = None
