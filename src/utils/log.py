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

    def __init__(self, logName, backupCount=10):
        self.logName = logName
        self.log_dir = join(
            dirname(dirname(abspath(__file__))), 'logs'
        )
        self.logFile = join(
            self.log_dir, '{0}.log'.format(self.logName)
        )
        self._levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        self._logfmt = '%Y-%m-%d %H:%M:%S'
        self._logger = logging.getLogger(self.logName)
        if not exists(self.log_dir):
            mkdir(self.log_dir)

        handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.logFile,
            backupCount=backupCount,
            when="midnight"
        )
        handler.suffix = "%Y%m%d"
        formatter = logging.Formatter(
            '[ %(levelname)s ] %(asctime)s %(filename)s:%(lineno)d %(message)s',
            datefmt=self._logfmt
        )
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)
        self._logger.setLevel(
            self._levels.get(GLOBAL.get('LogLevel', 'INFO').upper())
        )

    @property
    def getLogger(self):
        return self._logger
