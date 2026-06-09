"""Alembic env — wires the SQLAlchemy URL from Origin's session module
and registers all models on the shared metadata.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from origin.db.base import Base
from origin.db.session import build_database_url

# Import models so Base.metadata sees them.
import origin.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False so applying alembic's logging config
    # (run inline during app startup) does not silence uvicorn, kernel, or
    # agience.origin loggers that were already configured.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _resolved_url() -> str:
    return config.get_main_option("sqlalchemy.url") or build_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_resolved_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolved_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
