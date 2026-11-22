# -*- coding: utf-8 -*-
"""Flask CLI commands (``flask sa ...``)."""

from __future__ import annotations

from datetime import datetime, timedelta

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
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


@sa_cli.command("purge-expired")
@click.option("-n", "--limit", default=1000, show_default=True, help="max images per run")
def purge_expired_command(limit):
    """Delete images whose expiry has passed (files and metadata)."""
    from .libs.images import purge_expired

    if db.is_closed():
        db.connect()
    removed = purge_expired(limit)
    click.echo("purged expired images: %d" % removed)


@sa_cli.command("scheduler")
@click.option("--once", is_flag=True, help="run every job once and exit")
@with_appcontext
def scheduler_command(once):
    """Run expiry purge, moderation scan and demo rotation (foreground).

    The web workers start the same schedule themselves unless
    ``sapic_scheduler=0``; use this command when you prefer a dedicated
    process (systemd / a second container). Both sides take the same file lock,
    so only one of them leads.
    """
    from apscheduler.schedulers.blocking import BlockingScheduler

    from .libs.scheduler import (
        acquire_lock,
        job_specs,
        release_lock,
        run_demo_rotate,
        run_purge,
        run_review,
    )

    app = current_app._get_current_object()
    if db.is_closed():
        db.connect()

    if once:
        reviewed = run_review(app)
        removed = run_purge(app)
        rotated = run_demo_rotate(app, force=True)
        click.echo(
            "reviewed %(scanned)d image(s): %(passed)d passed, %(blocked)d blocked, "
            "%(failed)d to retry; purged %(removed)d expired; demo %(demo)s"
            % dict(reviewed, removed=removed, demo=rotated.get("reason", "skipped"))
        )
        return

    if not acquire_lock():
        raise click.ClickException(
            "another scheduler is running (data/scheduler.lock); "
            "set sapic_scheduler=0 on the web workers first"
        )
    scheduler = BlockingScheduler()
    specs = job_specs(app)
    for job_id, func, interval, delay in specs:
        scheduler.add_job(
            func,
            "interval",
            seconds=interval,
            args=[app],
            id=job_id,
            coalesce=True,
            max_instances=1,
            next_run_time=datetime.now() + timedelta(seconds=delay),
        )
    click.echo(
        "scheduler running: %s (ctrl-c to stop)"
        % ", ".join("%s every %ss" % (job_id, interval) for job_id, _f, interval, _d in specs)
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        release_lock()


@sa_cli.command("review-pending")
@click.option("-n", "--limit", default=50, show_default=True, help="max images per run")
@with_appcontext
def review_pending_command(limit):
    """Judge unreviewed images with the enabled moderator hooks.

    Designed for cron: every run claims a small batch, so a slow moderation API
    never competes with uploads. A ``block`` verdict only hides the image; an
    administrator approves or purges it from the admin API.
    """
    from .libs.review import moderator_names, review_pending

    if db.is_closed():
        db.connect()
    if not moderator_names():
        click.echo("no enabled moderator hook, nothing to review")
        return
    counts = review_pending(limit)
    click.echo(
        "reviewed %(scanned)d image(s): %(passed)d passed, %(blocked)d blocked, "
        "%(failed)d to retry" % counts
    )


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
