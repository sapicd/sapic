# -*- coding: utf-8 -*-
"""Flask CLI commands (``flask sa ...``)."""

from __future__ import annotations

import click
from flask.cli import AppGroup
from werkzeug.security import generate_password_hash

from .basis.db import db
from .models import User
from .models.base import now
from .models.user import STATUS_NORMAL

sa_cli = AppGroup("sa", help="sapic administration commands")


@sa_cli.command("upgrade")
def upgrade_command():
    """Create or upgrade the database schema."""
    from .migrations import upgrade

    applied = upgrade()
    if applied:
        click.echo("applied migrations: %s" % ", ".join(map(str, applied)))
    else:
        click.echo("database is up to date")


@sa_cli.command("create-admin")
@click.option("-u", "--username", required=True, help="admin username")
@click.option("-p", "--password", required=True, help="admin password")
@click.option("-e", "--email", default=None, help="admin email")
def create_admin_command(username, password, email):
    """Create an administrator account."""
    from .migrations import upgrade

    if db.is_closed():
        db.connect()
    upgrade()
    username = username.strip().lower()
    if User.get_or_none(User.username == username):
        raise click.ClickException("user already exists: %s" % username)
    User.create(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        nickname=username,
        is_admin=True,
        status=STATUS_NORMAL,
        labels=[],
        created_at=now(),
        updated_at=now(),
    )
    click.echo("admin created: %s" % username)
