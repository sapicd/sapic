# -*- coding: utf-8 -*-
"""Shared model primitives.

Deliberately portable between PostgreSQL and MySQL:

- JSON is stored in ``TEXT`` (no JSONB / MySQL JSON dependency).
- Timestamps are stored as Unix seconds (no timezone semantics).
"""

from __future__ import annotations

import json
import time

from peewee import Model, TextField

from ..extensions import db


def now() -> int:
    """Current Unix timestamp in seconds."""
    return int(time.time())


class JSONTextField(TextField):
    """Store Python objects as compact JSON text."""

    def db_value(self, value):
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def python_value(self, value):
        if value is None or value == "":
            return None
        return json.loads(value)


class BaseModel(Model):
    class Meta:
        database = db
