"""SQLite engine + session factory for Origin.

The DB file lives at `${ORIGIN_DB_PATH}` (default `/app/.data/origin/origin.db`
in containers, `./.data/origin/origin.db` locally). The init container creates
the parent directory; SQLAlchemy creates the file on first connect.

WAL mode + foreign-key enforcement are enabled via a connect-time PRAGMA hook
so concurrent reads don't block writes and ON DELETE CASCADE actually fires.

`DATABASE_URL` is honored as a test override (typically
`sqlite:///:memory:` in conftest.py).
"""

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _default_db_path() -> Path:
    """Default SQLite file location.

    In containers, `/app/.data/origin/origin.db`. Locally (no `/app`), fall
    back to `./.data/origin/origin.db` relative to the working directory.
    """
    container_default = Path("/app/.data/origin/origin.db")
    if container_default.parent.exists():
        return container_default
    return Path.cwd() / ".data" / "origin" / "origin.db"


def build_database_url() -> str:
    """Build the SQLAlchemy connection URL for Origin's SQLite DB.

    Honors `DATABASE_URL` if set (test override). Otherwise composes from
    `ORIGIN_DB_PATH` env var, falling back to a sensible default.
    """
    override = os.getenv("DATABASE_URL")
    if override:
        return override

    db_path_env = os.getenv("ORIGIN_DB_PATH")
    db_path = Path(db_path_env) if db_path_env else _default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


def _is_in_memory(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or url.startswith("sqlite:///:memory:")


def init_engine(url: str | None = None) -> Engine:
    """Build the global SQLAlchemy engine. Idempotent."""
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine

    resolved = url or build_database_url()
    kwargs: dict = {"future": True}

    if _is_sqlite(resolved):
        # FastAPI uses multiple threads; SQLite's default thread-check is too strict.
        kwargs["connect_args"] = {"check_same_thread": False}
        # In-memory DBs need a shared cache across connections (used by tests).
        if _is_in_memory(resolved):
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True

    _engine = create_engine(resolved, **kwargs)

    if _is_sqlite(resolved):
        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _conn_record) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            if not _is_in_memory(resolved):
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Engine not initialized — call init_engine() at startup.")
    return _engine


def SessionLocal() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Session factory not initialized — call init_engine() at startup.")
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a Session, closes it on request exit.

    Name kept for compatibility with callers that depend on this symbol; the
    underlying engine is now SQLite.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
