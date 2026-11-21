# -*- coding: utf-8 -*-
"""Application logging.

The line shape is shared with the other services so one collector can parse all
of them::

    [ INFO ] 2026-11-21 09:09:41 images.py:735 fetched 12 bytes

Inside a request the request id is inserted right before the message
(``... images.py:735 rid=a1b2c3d4 ...``), so a 500 shown in the browser can be
found in ``sys.log``; records outside a request carry no extra token.

``<LOG_DIR>/sys.log`` holds that output; standard error keeps getting the same
records too, so ``docker logs`` and ``journalctl`` still work. There is no access
log: nothing in the stack keeps one by default (gunicorn does not, and nginx is
switched off in the image). Files rotate at midnight and the last
``vars.LOG_FILE_BACKUPS`` days are kept.
"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from os import makedirs
from os.path import join

from flask import Flask, g, has_request_context

from .vars import LOG_FILE_BACKUPS, LOG_FILE_SUFFIX

SYS_LOG_FILE = "sys.log"

#: Shared with the other services; ``%(rid)s`` is ``"rid=xxxx "`` or empty.
LOG_FORMAT = "[ %(levelname)s ] %(asctime)s %(filename)s:%(lineno)d %(rid)s%(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

#: Handler installed by the previous ``create_log()`` (tests build many apps).
_installed: logging.Handler | None = None


class _RequestIdFilter(logging.Filter):
    """Insert the request id in front of the message, empty outside a request."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = getattr(g, "request_id", "") if has_request_context() else ""
        record.rid = "rid=%s " % rid if rid else ""
        return True


def _formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)


def create_log(
    level: str = "INFO",
    directory: str = "",
    filename: str = SYS_LOG_FILE,
) -> logging.Logger:
    """Attach the application log handler to the root logger and return it.

    ``directory`` empty leaves the file handler off (standard error only). A
    directory that cannot be created or written downgrades to standard error as
    well: a read-only deployment must not fail to boot over logs. ``level``
    filters the handler; the application logger keeps the level Flask set, so
    noisy third-party DEBUG records stay out of the file.
    """
    global _installed

    logger = logging.getLogger()
    if _installed is not None:
        logger.removeHandler(_installed)
        _installed.close()
        _installed = None
    if not directory:
        return logger

    try:
        makedirs(directory, exist_ok=True)
        handler = TimedRotatingFileHandler(
            join(directory, filename),
            when="midnight",
            backupCount=LOG_FILE_BACKUPS,
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("file logging disabled: %s", exc)
        return logger

    handler.suffix = LOG_FILE_SUFFIX
    #: 级别只卡 handler：root 的级别保持不动，否则第三方库（peewee 的 SQL）会灌进来。
    handler.setLevel(_LEVELS.get(str(level).upper(), logging.INFO))
    handler.setFormatter(_formatter())
    handler.addFilter(_RequestIdFilter())
    _installed = handler
    logger.addHandler(handler)
    return logger


def init_app(app: Flask) -> None:
    """Wire the logger from ``LOG_LEVEL`` / ``LOG_DIR``."""
    create_log(
        level=str(app.config.get("LOG_LEVEL", "INFO")),
        directory=str(app.config.get("LOG_DIR") or ""),
    )
