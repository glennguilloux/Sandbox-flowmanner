"""Alembic env.py — async migration runner."""

import asyncio
from logging.config import fileConfig

from alembic import context
from app.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.models import Base

target_metadata = Base.metadata

# Tables queried via raw SQL but have no ORM models — autogenerate must
# not emit DROP TABLE for these.
_RAW_SQL_TABLES = frozenset(
    {
        "agent_template_versions",
        "changelog_entries",
        "mission_runs",
        "onboarding_state",
    }
)


def include_object(object, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in _RAW_SQL_TABLES)


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """Suppress type-change ALTERs that would break FK constraints or are cosmetic.

    Returns False (= "types are the same, no ALTER needed") when:
    1. The metadata column has a ForeignKey — the DB is the truth for FK-bound
       columns, and changing types would break existing FK constraints.
    2. The types are cosmetically different but map to the same PostgreSQL type
       (TIMESTAMP/DATETIME, DOUBLE/FLOAT, BIGINT/INTEGER).
    """
    # FK-bound columns: never change type — the DB is the truth.
    if metadata_column.foreign_keys:
        return False

    ins = str(inspected_type).upper().strip()
    meta = str(metadata_type).upper().strip()
    if ins == meta:
        return False

    # Cosmetic equivalence groups
    _groups = (
        {"TIMESTAMP", "TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP WITH TIME ZONE", "DATETIME"},
        {"DOUBLE PRECISION", "FLOAT", "FLOAT8", "DOUBLE"},
        {"BIGINT", "INTEGER", "INT8", "INT4"},
        {"BYTEA", "BLOB"},
    )
    return all(not (ins in g and meta in g) for g in _groups)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (async entry point)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
