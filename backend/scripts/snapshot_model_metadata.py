#!/usr/bin/env python3
"""Snapshot SQLAlchemy metadata for migration validation.

Usage:
    python /app/scripts/snapshot_model_metadata.py > /app/scripts/model_snapshot.json
"""

import json
import os
import sys
from datetime import UTC, datetime

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.models import Base


def _get_alembic_version() -> str:
    return os.environ.get("ALEMBIC_VERSION", "")


def _get_generated_at() -> str:
    override = os.environ.get("SNAPSHOT_GENERATED_AT")
    if override:
        return override

    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is not None:
        generated_at = datetime.fromtimestamp(int(source_date_epoch), UTC).replace(microsecond=0)
        return generated_at.isoformat().replace("+00:00", "Z")

    return "1970-01-01T00:00:00Z"


def _column_types(table):
    return {
        column.name: str(column.type)
        for column in sorted(table.columns, key=lambda column: column.name)
    }


def _index_names(table):
    return sorted(index.name for index in table.indexes if index.name)


def _unique_constraint_columns(constraint):
    return sorted(column.name for column in constraint.columns)


def _unique_constraints(table):
    return sorted(
        (
            _unique_constraint_columns(constraint)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ),
        key=lambda columns: columns,
    )


def _foreign_key_target_fullname(foreign_key):
    return getattr(foreign_key.column, "fullname", foreign_key.target_fullname)


def _foreign_keys(table):
    return sorted(
        (
            [foreign_key.parent.name, _foreign_key_target_fullname(foreign_key)]
            for foreign_key in table.foreign_keys
        ),
        key=lambda foreign_key: (foreign_key[0], foreign_key[1]),
    )


def _table_snapshot(table):
    return {
        "name": table.name,
        "columns": _column_types(table),
        "indexes": _index_names(table),
        "unique_constraints": _unique_constraints(table),
        "foreign_keys": _foreign_keys(table),
    }


def build_snapshot(metadata) -> dict:
    tables = sorted(
        (_table_snapshot(table) for table in metadata.sorted_tables),
        key=lambda table: table["name"],
    )
    return {
        "generated_at": _get_generated_at(),
        "alembic_version": _get_alembic_version(),
        "model_count": len(tables),
        "tables": tables,
    }


def main() -> None:
    print(json.dumps(build_snapshot(Base.metadata), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
