# -*- coding: utf-8 -*-
"""Site-level key/value settings (replaces v1 ``picbed:dat/siteconfig``)."""

from __future__ import annotations

from peewee import AutoField, CharField, IntegerField

from .base import BaseModel, JSONTextField, now


class Setting(BaseModel):
    id = AutoField()
    key = CharField(max_length=64, unique=True)
    value = JSONTextField(null=True)
    updated_at = IntegerField(default=now)

    class Meta:
        table_name = "settings"
