# -*- coding: utf-8 -*-
"""Database wiring.

Peewee is used with a ``DatabaseProxy`` so tests can swap in SQLite
without importing application code.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urlparse

from peewee import DatabaseProxy, MySQLDatabase, PostgresqlDatabase, SqliteDatabase

db = DatabaseProxy()


def create_database(url: str):
    """Create a Peewee database instance from a DSN.

    Supported schemes: ``postgresql`` / ``postgres``, ``mysql``, ``sqlite``.
    """
    if not url:
        raise RuntimeError("DATABASE_URL is required (config: sapic_db_url)")

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    query = dict(parse_qsl(parsed.query))

    if scheme in ("postgres", "postgresql", "pgsql"):
        #: ``requirements/base.txt`` only ships ``psycopg`` (v3), so pin the
        #: driver: Peewee would otherwise pick psycopg2 whenever some unrelated
        #: package happens to have installed it.
        return PostgresqlDatabase(
            parsed.path.lstrip("/"),
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            prefer_psycopg3=True,
            **query,
        )

    if scheme in ("mysql", "mysql+pymysql"):
        query.setdefault("charset", "utf8mb4")
        return MySQLDatabase(
            parsed.path.lstrip("/"),
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            **query,
        )

    if scheme.startswith("sqlite"):
        # sqlite:///relative.db and sqlite:////absolute/path.db
        path = parsed.path[1:] if parsed.path.startswith("/") else parsed.path
        database = SqliteDatabase(path or ":memory:", **query)
        database.pragma("foreign_keys", 1)
        return database

    raise RuntimeError("unsupported database scheme: %s" % scheme)


def init_app(app) -> None:
    """Bind database lifecycle to the Flask application."""
    db.initialize(create_database(app.config["DATABASE_URL"]))

    @app.before_request
    def _connect_db():
        if db.is_closed():
            db.connect()

    @app.teardown_appcontext
    def _close_db(exc):
        if db.is_closed():
            return
        # Keep SQLite in-memory databases open for the test process.
        if isinstance(db.obj, SqliteDatabase) and db.obj.database == ":memory:":
            return
        db.close()


def ping_database() -> bool:
    try:
        db.execute_sql("SELECT 1").fetchone()
        return True
    except Exception:
        return False
