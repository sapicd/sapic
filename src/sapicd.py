# picbed gunicorn config

from os.path import abspath, dirname, join, exists, isdir
from os import getenv, mkdir
from multiprocessing import cpu_count
from config import GLOBAL


def delete_hookloadtime():
    from libs.storage import get_storage
    s = get_storage()
    del s['hookloadtime']


IS_RUN = True if getenv("picbed_isrun") == "true" else False
CPU_COUNT = int(getenv("picbed_cpucount") or (cpu_count() * 2 + 1))

LOGSDIR = join(dirname(abspath(__file__)), "logs")
if not exists(LOGSDIR):
    mkdir(LOGSDIR)

bind = "{}:{}".format(GLOBAL['Host'], GLOBAL['Port'])
proc_name = GLOBAL['ProcessName']
workers = CPU_COUNT
worker_class = "gevent"
worker_connections = 1000
max_requests = 10000
if isdir("/dev/shm"):
    worker_tmp_dir = "/dev/shm"

if IS_RUN:
    daemon = False

else:
    daemon = True
    pidfile = join(LOGSDIR, "{}.pid".format(proc_name))
    loglevel = 'info'
    errorlog = join(LOGSDIR, "gunicorn.log")
    accesslog = None


def on_reload(svr):
    delete_hookloadtime()


def on_exit(svr):
    delete_hookloadtime()
