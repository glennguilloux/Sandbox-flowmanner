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
        "mission_runs",
        "onboarding_state",
        "substrate_worker_leases",  # raw-SQL CRUD in services/substrate/leases.py
    }
)

# Tables whose DROP is explicitly permitted (hand-authored reviewed migrations
# only). Empty by default: autogenerate must NEVER emit DROP TABLE for live
# tables.
#
# Validation note (2026-07-18): the handoff sketch suggested
# ``getattr(object, "drop", False)`` to detect drop candidates, but the
# actually-installed Alembic (1.13.1) passes NO ``object.drop`` attribute for
# table drops.  Inspecting ``alembic/autogenerate/compare.py::_compare_tables``
# shows a DROP candidate is signalled by ``reflected=True`` (table came from the
# DB) AND ``compare_to is None`` (no model-defined table to compare against).
# That signal is used below.  When ``reflected=False`` the table is
# model-defined and autogenerate wants to CREATE it, so the allow-list does not
# apply.
_DROP_TABLE_ALLOWLIST = frozenset(
    {
        # Tables reviewed and approved for DROP via a hand-authored migration.
        "p1_probe",  # orphan diagnostic table; reviewed 2026-07-18 (a1p1probe00)
    }
)


def include_object(object, name, type_, reflected, compare_to):
    # Always suppress raw-SQL tables (both create and drop directions).
    if type_ == "table" and name in _RAW_SQL_TABLES:
        return False
    # A table DROP candidate is a table present in the DB (reflected=True)
    # with no model-defined counterpart (compare_to is None).  Never let
    # autogenerate drop such a table unless it is on the explicit allow-list.
    if type_ == "table" and reflected and compare_to is None:
        return name in _DROP_TABLE_ALLOWLIST
    return True


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """Suppress type-change ALTERs that are purely cosmetic.

    Returns False (= "types are the same, no ALTER needed") when the
    types are cosmetically different but map to the same PostgreSQL type
    (TIMESTAMP/DATETIME, DOUBLE/FLOAT, BIGINT/INTEGER, BYTEA/BLOB).

    Returns True (= "types differ, generate ALTER") for all genuine
    mismatches — including FK-bound columns.  FK-bound ALTERs require
    ``postgresql_using`` and must be reviewed by a human, but suppressing
    them silently caused 14 drift items to accumulate undetected
    (fixed in commit 4555295, 2026-06-25).
    """
    ins = str(inspected_type).upper().strip()
    meta = str(metadata_type).upper().strip()
    if ins == meta:
        return False

    # Cosmetic equivalence groups — types that PostgreSQL treats as identical
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
        compare_type=compare_type,
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
