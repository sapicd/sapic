# -*- coding: utf-8 -*-
"""File logging.

``<LOG_DIR>/sys.log`` receives everything the application logs; standard error
keeps getting the same output, so ``docker logs`` and ``journalctl`` still work.
Request records are not written here: nothing in the stack keeps an access log
by default (gunicorn does not, and nginx is switched off in the image).

Files rotate in place (see ``vars.LOG_FILE_MAX_BYTES``). With several gunicorn
workers each process rotates on its own, so a worker may recreate the file right
after another one moved it; keep the directory on a volume with logrotate when
that matters.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from os import makedirs
from os.path import join

from flask import Flask

from .vars import LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES

SYS_LOG_FILE = "sys.log"

_SYS_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

#: Handler installed by the previous ``create_app()`` (tests build many apps).
_installed: RotatingFileHandler | None = None


def _handler(directory: str, filename: str, level: int) -> RotatingFileHandler:
    makedirs(directory, exist_ok=True)
    handler = RotatingFileHandler(
        join(directory, filename),
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_SYS_FORMAT))
    return handler


def init_app(app: Flask) -> None:
    """Attach the application log; ``LOG_DIR`` empty disables file logging.

    A directory that cannot be created or written only downgrades logging to
    standard error: a read-only deployment must not fail to boot over logs.
    """
    global _installed

    directory = str(app.config.get("LOG_DIR") or "")
    if not directory:
        return

    level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")))
    root = logging.getLogger()
    try:
        handler = _handler(directory, SYS_LOG_FILE, level)
    except OSError as exc:
        logging.getLogger(__name__).warning("file logging disabled: %s", exc)
        return

    if _installed is not None:
        root.removeHandler(_installed)
        _installed.close()
    _installed = handler
    root.addHandler(handler)
