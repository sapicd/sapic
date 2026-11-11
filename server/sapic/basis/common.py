# -*- coding: utf-8 -*-
"""Generic helpers shared by every layer (no business knowledge)."""

from __future__ import annotations

from os import getenv

from .vars import ENV_NAME, TRUE_VALUES

#: Values of ``FLASK_ENV`` / ``sapic_env`` treated as development.
_DEV_VALUES = ("dev", "development")


def as_bool(value) -> bool:
    """Parse a truthy config value."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in TRUE_VALUES


def as_int(value, default: int) -> int:
    """Parse an int config value with fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_dev() -> bool:
    """Detect the development environment.

    Reads ``FLASK_ENV`` first, then the ``sapic_env`` override; anything else
    (including an unset variable) is treated as production.
    """
    value = getenv("FLASK_ENV") or getenv(ENV_NAME) or ""
    return value.strip().lower() in _DEV_VALUES
