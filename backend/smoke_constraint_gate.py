"""End-to-end smoke test for the Epic 4.1b constraint gate.

Runs against the LIVE backend DB + the REAL NodeExecutor._handle_tool
dispatch path (real code_executor handler). Only the capability engine is
patched (so the gate — not OCap — decides). Exercises BLOCK, ESCALATE,
and ALLOW (real tool execution) with a real constraint claim inserted
into the live personal_memory_claims table.

Self-cleaning: clears any prior smoke-test claims at start and in a
finally block, so crashed runs don't leave orphan constraints behind.

Usage:
    DATABASE_URL=... .venv/bin/python smoke_constraint_gate.py
"""

from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.models.personal_memory_models import PersonalMemoryClaim
from app.services.substrate.executor import UnifiedExecutor
from app.services.substrate.node_executor import NodeExecutor
from app.services.substrate.workflow_models import (
    NodeType,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

SUBJECT = "No code execution in this workspace (SMOKE-TEST)"
DUMMY_UUID = "00000000-0000-0000-0000-000000000001"


def _claim(claim_id: uuid.UUID, user_id: int, workspace_id: str, action: str) -> PersonalMemoryClaim:
    return PersonalMemoryClaim(
        id=claim_id,
        user_id=user_id,
        workspace_id=workspace_id,
        subject=SUBJECT,
        predicate="prohibits",
        object={
            "target_tools": ["code_executor"],
            "action": action,
            "reason": "smoke-test constraint",
        },
        claim_type="constraint",
        scope="workspace",
        source_type="user_explicit",
        sensitivity="normal",
    )


async def _clear(db, workspace_id: str) -> None:
    await db.execute(
        text(
            "DELETE FROM personal_memory_claims "
            "WHERE workspace_id = :ws AND claim_type = 'constraint' "
            "AND object->>'reason' = 'smoke-test constraint'"
        ).bindparams(ws=workspace_id)
    )
    await db.commit()


async def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set")
        return 2

    claim_id = uuid.uuid4()

    async with AsyncSessionLocal() as db:
        wid = (await db.execute(text("SELECT id FROM workspaces LIMIT 1"))).scalar_one_or_none()
        if not wid:
            print("ERROR: no workspace in DB to scope the smoke test to")
            return 2
        workspace_id = str(wid)
        uid = (await db.execute(text("SELECT id FROM users LIMIT 1"))).scalar_one_or_none()
        user_id = int(uid) if uid else 1
        print(f"[setup] workspace_id={workspace_id} user_id={user_id} claim_id={claim_id}")

        # Clear any orphan smoke-test claims from prior runs.
        await _clear(db, workspace_id)

        workflow = Workflow(
            id=DUMMY_UUID,
            type=WorkflowType.SOLO,
            title="smoke",
            user_id=DUMMY_UUID,  # patched capability engine ignores it
            workspace_id=workspace_id,
        )
        node = WorkflowNode(
            id="00000000-0000-0000-0000-000000000002",
            type=NodeType.TOOL_CALL,
            config={"tool_name": "code_executor", "params": {"code": 'print("hello-from-tool")'}},
        )

        # Patch ONLY the capability engine so the gate decides, not OCap.
        from app.services.capability_engine import get_capability_engine

        ce = get_capability_engine()
        ce.verify_and_require = lambda *a, **k: None  # type: ignore[assignment]
        ce.issue = lambda *a, **k: object()  # type: ignore[assignment]

        executor = UnifiedExecutor()
        results: dict[str, bool] = {}

        try:

            async def run_case(action: str, expect_key: str) -> bool:
                # Reset to exactly one claim with this action.
                await _clear(db, workspace_id)
                db.add(_claim(claim_id, user_id, workspace_id, action))
                await db.commit()
                # Fresh NodeExecutor per case → fresh PreToolConstraints (no stale cache).
                node_exec = NodeExecutor(executor)
                verdict = await node_exec._handle_tool(db, node, {}, workflow.budget, "run-smoke", workflow)
                print(f"  [{action:8}] -> {verdict}")
                return expect_key in verdict

            print("[1] BLOCK case")
            results["block"] = await run_case("block", "constraint_blocked")
            print(f"    BLOCK enforced: {results['block']}")

            print("[2] ESCALATE case")
            results["escalate"] = await run_case("escalate", "constraint_escalate")
            print(f"    ESCALATE enforced: {results['escalate']}")

            print("[3] ALLOW case (no constraint) — real code_executor must run")
            await _clear(db, workspace_id)
            await db.commit()
            node_exec = NodeExecutor(executor)
            allow_res = await node_exec._handle_tool(db, node, {}, workflow.budget, "run-smoke", workflow)
            print(f"  [allow] -> {allow_res}")
            results["allow"] = bool(allow_res.get("success")) and "hello-from-tool" in str(allow_res.get("output", ""))
            print(f"    real tool executed: {results['allow']}")
        finally:
            await _clear(db, workspace_id)
            print("[cleanup] removed smoke-test claims")

    passed = all(results.values())
    print("\nRESULT:", "PASS" if passed else "FAIL", dict(results))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
