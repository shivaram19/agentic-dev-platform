"""
Agentic Development Platform - Alembic environment script.

This script is the integration point between SQLAlchemy and Alembic. It:

- imports the ORM models,
- configures the `async_session` and `async_engine` used by the app,
- wires the target metadata to Alembic’s migration context,
- and configures logging and transaction handling.

It is expected to live in the project root near `alembic.ini`.
"""
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlalchemy.ext.asyncio import AsyncEngine
from alembic import context

# This project’s ORM metadata
from core.models.task_model import Task
from core.models.session_model import Session

# This is the Alembic Config object, which already has the `alembic.ini` values.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model’s `Base.metadata` or declarative registry here.
# For a real system, you’d have a central `Base` or `registry`.
target_metadata = None

# Collect all tables so that Alembic can see them.
import sqlalchemy.orm as orm

# Use a simple approach: attach all tables from Task and Session.
task_metadata = Task.metadata
session_metadata = Session.metadata

# In a real project you’d merge into a single `Base.metadata`.
from sqlalchemy.schema import MetaData

combined_metadata = MetaData()
for meta in [task_metadata, session_metadata]:
    for table in meta.tables.values():
        combined_metadata._add_table(table.name, table.schema, table)

target_metadata = combined_metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this mode, we create an Engine and associate a connection with the context.
    """
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        # Default: create a synchronous engine from the INI URL.
        # This is mainly for safety because Alembic does not yet support async‑only.
        url = config.get_main_option("sqlalchemy.url")
        connectable = create_engine(
            url,
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# Run the appropriate mode based on the command line.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
