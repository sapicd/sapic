# -*- coding: utf-8 -*-
"""
    utils.log
    ~~~~~~~~~

    Define logging base class.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

import logging
import logging.handlers
from os import mkdir
from os.path import join, dirname, abspath, exists
from config import GLOBAL


class Logger(object):

    def __init__(self, logname, backup_count=10):
        self.logname = logname
        self.log_dir = join(
            dirname(dirname(abspath(__file__))), 'logs'
        )
        self.log_file = join(
            self.log_dir, '{0}.log'.format(self.logname)
        )
        self._levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        self._logfmt = '%Y-%m-%d %H:%M:%S'
        self._logger = logging.getLogger(self.logname)
        if not exists(self.log_dir):
            mkdir(self.log_dir)

        LEVEL = GLOBAL.get('LogLevel', 'INFO').upper()
        if LEVEL == "DEBUG":
            LOGFMT = (
                '[ %(levelname)s ] %(threadName)s %(asctime)s'
                '%(filename)s:%(lineno)d %(message)s'
            )
        else:
            LOGFMT = (
                '[ %(levelname)s ] %(asctime)s'
                '%(filename)s:%(lineno)d %(message)s'
            )
        handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.log_file,
            backupCount=backup_count,
            when="midnight"
        )
        handler.suffix = "%Y%m%d"
        formatter = logging.Formatter(LOGFMT, datefmt=self._logfmt)
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)
        self._logger.setLevel(
            self._levels.get(LEVEL)
        )

    @property
    def getLogger(self):
        return self._logger
