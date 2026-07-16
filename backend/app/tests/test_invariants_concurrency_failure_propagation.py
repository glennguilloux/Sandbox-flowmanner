"""
Invariant-proof tests for the HARD GATE — Concurrency & Failure Propagation
(see backend/AGENTS.md, section "HARD GATE — Concurrency & Failure Propagation").

These are ONE-ASSERTION proofs of each invariant's *shape*. They prove the
required pattern is enforceable. Remediation of the real production sites that
currently violate the gate is tracked separately (see the AGENTS.md section's
self-critique table).
"""

from __future__ import annotations

import pytest
from sqlalchemy import column, create_engine, select, table, text

# backend is Postgres; SKIP LOCKED only compiles under the pg dialect
_PG = create_engine("postgresql://")


# ── Invariant 1: deadlock-proof lock ordering ──────────────────────────────
# Mirrors the required `batch_abort` lock (app/api/_mission_cqrs/commands.py L862/L875).
# Uses a lightweight `mission` table construct so the test stays DB-free;
# `mission.id` below stands in for the real `Mission.id` ORM column.

MISSION = table("mission", column("id"))


def build_batch_abort_lock(str_ids: list[str]):
    """Canonical deadlock-proof lock: sorted ids + ORDER BY PK + SKIP LOCKED + lock_timeout."""
    ids = sorted(str_ids)
    lock_timeout_stmt = text("SET LOCAL lock_timeout='2s'")
    select_stmt = select(MISSION).where(MISSION.c.id.in_(ids)).order_by(MISSION.c.id).with_for_update(skip_locked=True)
    return ids, lock_timeout_stmt, select_stmt


def test_invariant1_lock_ordering_is_deadlock_proof():
    ids, lock_timeout_stmt, select_stmt = build_batch_abort_lock(
        ["3", "1", "2"]  # deliberately unsorted to prove the sort happens
    )

    # 1) ids are acquired in a deterministic global order
    assert ids == ["1", "2", "3"]

    # 2) lock_timeout is set on the session before locks are taken
    assert "SET LOCAL lock_timeout='2s'" in str(lock_timeout_stmt)

    # 3) the SELECT compiles to ORDER BY PK + FOR UPDATE SKIP LOCKED (pg dialect)
    compiled = str(select_stmt.compile(dialect=_PG.dialect, compile_kwargs={"literal_binds": True}))
    assert "ORDER BY mission.id" in compiled
    assert "FOR UPDATE" in compiled
    assert "SKIP LOCKED" in compiled


# ── Invariant 2: LLM/model-routing failure propagation ─────────────────────
# Representative caller pattern (mirrors substrate/node_executor.py L559,
# llm_executor.py L121, mission_planner.py L883).


def representative_caller(route_response: dict) -> dict:
    """A caller that MUST NOT convert success=False into success=True."""
    if not route_response.get("success"):
        return {"success": False, "error": route_response.get("error", "routing failed")}
    return {"success": True, "output": route_response.get("response", "")}


def test_invariant2_success_false_must_propagate_as_error():
    bad_response = {"success": False, "error": "provider 5xx", "response": ""}

    result = representative_caller(bad_response)

    # A False success is an ERROR — never an empty-string success=True.
    assert result["success"] is False
    assert "error" in result
    assert result.get("success") is not True


def test_invariant2_success_true_yields_output():
    good_response = {"success": True, "response": "plan json", "error": None}

    result = representative_caller(good_response)

    assert result["success"] is True
    assert result["output"] == "plan json"
