# picbed gunicorn config

from os.path import abspath, dirname, join
from os import getenv
from multiprocessing import cpu_count
from config import GLOBAL

bind = "{}:{}".format(GLOBAL['Host'], GLOBAL['Port'])

backlog = 2048

proc_name = GLOBAL['ProcessName']

daemon = False if getenv("picbed_nodaemon") in ("true", "True", True) else True

workers = cpu_count() * 2 + 1

worker_class = "gevent"

threads = 10

pidfile = join(dirname(abspath(__file__)), "logs", "{}.pid".format(proc_name))

loglevel = 'info'

errorlog = join(dirname(abspath(__file__)), "logs", "gunicorn.log")

accesslog = None
