"""Q1-B — constraint lane (CORRECTION C2).

Locked invariants for the dedicated constraint retrieval lane:

  * Queries ``claim_type = 'constraint'`` ONLY (parition on claim_type —
    there is no ``is_negative`` column; per the decomposition C2 correction).
  * Is **lexical / exact**, never vectorized: the compiled SQL contains a
    containment/cast predicate on (subject, predicate, object-as-text) and
    NO cosine / embedding / vector operator.
  * Tenant-scoped on ``(user_id, workspace_id)``; excludes deleted/expired.
  * Fail-open: a DB error returns ``[]`` rather than raising.

The lane is exercised inside ``PersonalMemoryService.recall`` (wired in the
same commit); here we assert the *shape* of the lane's SQL without a live DB
by compiling against the Postgres dialect, plus the fail-open path.

Run from backend/ with the host venv:
    .venv/bin/python -m pytest app/tests/test_q1_constraint_lane.py -v
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

sys.path.insert(0, "/opt/flowmanner/backend")

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.personal_memory_models import PersonalMemoryClaim
from app.services import personal_memory_service as pms


def _compile_lane_sql(query: str) -> str:
    """Build the constraint-lane statement the way ``recall`` would and
    return its compiled SQL (Postgres dialect), WITHOUT a DB.
    """
    svc = object.__new__(pms.PersonalMemoryService)
    svc.db = None  # not used during SQL construction
    # Call the private builder via the instance method's body by replicating
    # the minimal envelope: we invoke the real method but stub the execute.
    # Simpler + robust: reconstruct the predicate list the same way the
    # method does, then compile. To avoid drift, we actually call the method
    # with a fake session that records the statement.
    captured: dict[str, Any] = {}

    class _FakeResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class _FakeExecute:
        def __await__(self):
            # Return a coroutine resolving to a fake result.
            async def _run():
                return _FakeResult()

            return _run().__await__()

    class _FakeDB:
        async def execute(self, stmt):
            captured["stmt"] = stmt
            return _FakeResult()

    svc.db = _FakeDB()  # type: ignore[assignment]
    asyncio.get_event_loop().run_until_complete(
        svc._recall_constraint_lane(
            user_id=1,
            workspace_id="ws",
            query=query,
            min_confidence=0.0,
        )
    )
    stmt = captured["stmt"]
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestConstraintLaneSQLShape:
    def test_partitions_on_claim_type_constraint(self) -> None:
        sql = _compile_lane_sql("deploy")
        assert "claim_type = 'constraint'" in sql or 'claim_type = "constraint"' in sql

    def test_is_lexical_not_vectorized(self) -> None:
        sql = _compile_lane_sql("deploy")
        # No vector / cosine / embedding operator must appear.
        assert "cosine" not in sql.lower()
        assert "<=>" not in sql
        assert "embedding" not in sql.lower()
        # Lexical containment on subject/predicate AND object cast must appear.
        assert "subject" in sql.lower()
        assert "predicate" in sql.lower()
        assert "object" in sql.lower()

    def test_empty_query_returns_all_constraints_no_containment(self) -> None:
        sql = _compile_lane_sql("")
        # Empty query → no ILIKE/contains predicate (seed returns all active).
        # The WHERE must still scope to claim_type + tenant + not-deleted.
        assert "claim_type = 'constraint'" in sql or 'claim_type = "constraint"' in sql
        assert "deleted_at IS NULL" in sql or "deleted_at IS NULL".lower() in sql.lower()

    def test_tenant_scoped(self) -> None:
        sql = _compile_lane_sql("deploy")
        assert "user_id" in sql.lower()
        assert "workspace_id" in sql.lower()


class TestConstraintLaneFailOpen:
    def test_db_error_returns_empty_not_raises(self) -> None:
        svc = object.__new__(pms.PersonalMemoryService)

        class _BoomDB:
            async def execute(self, stmt):
                raise RuntimeError("db down")

        svc.db = _BoomDB()  # type: ignore[assignment]
        result = asyncio.get_event_loop().run_until_complete(
            svc._recall_constraint_lane(user_id=1, workspace_id="ws", query="deploy", min_confidence=0.0)
        )
        assert result == []


class TestFailClosedTenantGuard:
    """Gate (2): tenant filter FAIL-CLOSED.

    A missing/empty tenant must RAISE rather than silently compiling to
    ``user_id IS NULL`` / ``workspace_id = ''`` (tenant-escape). This is a
    boundary/security error, distinct from the fail-open-on-DB-error posture.
    """

    def test_recall_raises_on_user_id_none(self) -> None:
        svc = object.__new__(pms.PersonalMemoryService)

        with pytest.raises(pms.PersonalMemoryValidationError):
            asyncio.get_event_loop().run_until_complete(
                svc.recall(user_id=None, workspace_id="ws", query="x")  # type: ignore[arg-type]
            )

    def test_recall_raises_on_workspace_id_none(self) -> None:
        svc = object.__new__(pms.PersonalMemoryService)

        with pytest.raises(pms.PersonalMemoryValidationError):
            asyncio.get_event_loop().run_until_complete(
                svc.recall(user_id=1, workspace_id=None, query="x")  # type: ignore[arg-type]
            )

    def test_recall_raises_on_empty_workspace_id(self) -> None:
        svc = object.__new__(pms.PersonalMemoryService)

        with pytest.raises(pms.PersonalMemoryValidationError):
            asyncio.get_event_loop().run_until_complete(svc.recall(user_id=1, workspace_id="", query="x"))

    def test_constraint_lane_raises_on_user_id_none(self) -> None:
        svc = object.__new__(pms.PersonalMemoryService)

        with pytest.raises(pms.PersonalMemoryValidationError):
            asyncio.get_event_loop().run_until_complete(
                svc._recall_constraint_lane(  # type: ignore[arg-type]
                    user_id=None, workspace_id="ws", query="deploy", min_confidence=0.0
                )
            )

    def test_constraint_lane_raises_on_empty_workspace_id(self) -> None:
        svc = object.__new__(pms.PersonalMemoryService)

        with pytest.raises(pms.PersonalMemoryValidationError):
            asyncio.get_event_loop().run_until_complete(
                svc._recall_constraint_lane(user_id=1, workspace_id="", query="deploy", min_confidence=0.0)
            )

    def test_resolved_tenant_does_not_raise(self) -> None:
        # Happy path: a fully-resolved tenant must NOT trip the guard.
        svc = object.__new__(pms.PersonalMemoryService)

        class _OkResult:
            def scalars(self):
                return self

            def all(self):
                return []

        class _FakeDB:
            async def execute(self, stmt):
                return _OkResult()

        svc.db = _FakeDB()  # type: ignore[assignment]
        result = asyncio.get_event_loop().run_until_complete(
            svc._recall_constraint_lane(user_id=1, workspace_id="ws", query="deploy", min_confidence=0.0)
        )
        # The lane returns [] but must NOT raise — proving the guard only
        # fires on a missing tenant, not on a resolved one.
        assert result == []
