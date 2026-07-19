"""Model-drift guardrail: every ORM model must be registered on Base.metadata.

This is the belt-and-suspenders companion to ``scripts/guard_alembic_drift.py``
(the DROP-TABLE allow-list guard). That script needs a live Docker/DB to run
and therefore SKIPS in CI; this pytest runs with no DB and directly asserts the
model/Base.metadata contract:

    If an ORM model defines ``__tablename__`` but is never imported by
    ``app.models`` (so it never registers on ``Base.metadata``), Alembic
    autogenerate sees it as "table missing from metadata" and would emit a
    ``DROP TABLE`` against live data. This test catches exactly that class of
    drift at import-collection time, before any migration is generated.

Run from the backend dir:
    PYTHONPATH=. python -m pytest app/tests/test_models_registered.py -q

The expected count is the *live* ``Base.metadata.tables`` size. It is derived
from ``Base`` (the single DeclarativeBase in app/models/__init__.py), which is
the authoritative set Alembic compares against. Counts of ``__tablename__``
in app/models/*.py under-count because some models are registered from
app/services/auth_service.py (RefreshToken) and app/governance/workflow_config
(2 tables), all pulled in by app/models/__init__.py.

Verified count: 162 (2026-07-19, via ``len(Base.metadata.tables)``).
"""

from __future__ import annotations

# Importing the models package registers every model onto Base.metadata.
import app.models
from app.models import Base


def test_all_models_registered_with_base():
    """Assert every ORM table is reachable from Base.metadata.

    An orphaned model (defined but never imported by app.models) would not
    appear here and would be DROPPED on the next autogenerate against live
    data. If you legitimately add a table, bump EXPECTED_TABLE_COUNT after
    confirming the new table is registered and has a reviewed migration.
    """
    EXPECTED_TABLE_COUNT = 162  # verified 2026-07-19 via len(Base.metadata.tables)
    actual = len(Base.metadata.tables)
    assert actual == EXPECTED_TABLE_COUNT, (
        f"model/Base.metadata drift: {actual} tables registered, "
        f"expected {EXPECTED_TABLE_COUNT}. "
        "An ORM model is orphaned from Base.metadata (would DROP TABLE on live "
        "data) — or a table was added/removed without updating this guard. "
        "Inspect app/models/__init__.py imports and alembic/versions."
    )
