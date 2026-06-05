#!/usr/bin/env python3
"""Disaster Recovery Acceptance Test (Phase 1.5).

Validates that if Postgres survives, the platform can be fully reconstructed.

Run inside the backend container:
    docker compose cp backend/tests/test_disaster_recovery.py backend:/app/dr_test.py
    docker compose exec backend python /app/dr_test.py

Or run via pytest (DB-dependent tests auto-skip when DB is unreachable):
    python -m pytest tests/test_disaster_recovery.py -v -s
"""

from __future__ import annotations

import asyncio
import socket
import sys
from datetime import datetime, timezone


# ── Helpers ────────────────────────────────────────────────────────────


def db_reachable() -> bool:
    """Check DB reachability via TCP socket (no event loop needed)."""
    try:
        sock = socket.create_connection(("workflow-postgres", 5432), timeout=3)
        sock.close()
        return True
    except OSError:
        return False


async def table_count(table: str) -> int:
    """Return row count for a table, or -1 if unreachable."""
    from sqlalchemy import text
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text(f"SELECT count(*) FROM {table}")
            )
            return result.scalar() or 0
        except Exception:
            return -1


async def table_exists(table: str) -> bool:
    """Check whether a table exists in the current database."""
    from sqlalchemy import text
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :name"
            ),
            {"name": table},
        )
        return result.fetchone() is not None


# ── Test Runner ────────────────────────────────────────────────────────


class DRTestRunner:
    """Runs all disaster recovery checks in a single event loop."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.details: list[str] = []

    def ok(self, name: str, msg: str = ""):
        self.passed += 1
        self.details.append(f"  ✅ {name}" + (f" — {msg}" if msg else ""))

    def fail(self, name: str, msg: str):
        self.failed += 1
        self.details.append(f"  ❌ {name} — {msg}")

    def skip(self, name: str, msg: str):
        self.skipped += 1
        self.details.append(f"  ⏭️  {name} — {msg}")

    # ── 1. Schema Verification ────────────────────────────────────

    async def check_schemas(self):
        tables = [
            "tools_catalog", "tool_versions",
            "capabilities_catalog", "capability_versions",
            "memory_entries", "materialization_state",
            "topology_snapshots", "topology_nodes", "topology_edges",
            "agent_template_versions",
        ]
        for table in tables:
            exists = await table_exists(table)
            if exists:
                self.ok(f"Schema: {table}")
            else:
                self.fail(f"Schema: {table}", "table does not exist")

    # ── 2. Data Population ────────────────────────────────────────

    async def check_data_population(self):
        checks = {
            "tools_catalog": (1, "Run import_builtin_tools.py to populate"),
            "capabilities_catalog": (1, "Run import_builtin_capabilities.py to populate"),
            "agent_templates": (10, "Should have been seeded at startup"),
            "agent_template_versions": (1, "Run import_agent_templates.py to populate"),
        }
        for table, (min_count, note) in checks.items():
            count = await table_count(table)
            if count < 0:
                self.skip(f"Data: {table}", "table not found")
            elif count >= min_count:
                self.ok(f"Data: {table}", f"{count} rows")
            else:
                self.fail(f"Data: {table}", f"{count} rows (need {min_count}+). {note}")

    # ── 3. Hydration Pipeline ─────────────────────────────────────

    async def check_tool_hydration(self):
        """Simulate _hydrate_tools_from_db."""
        count = await table_count("tools_catalog")
        if count < 1:
            self.skip("Hydration: tools", "tools_catalog is empty")
            return

        from app.lifespan import _hydrate_tools_from_db, _resolve_handler_ref
        from app.tools.base import get_tool_registry
        import app.tools.base as base_mod

        old_registry = base_mod._tool_registry
        base_mod._tool_registry = None
        try:
            result = await _hydrate_tools_from_db()
            if result:
                registry = get_tool_registry()
                tools = registry.list_all()
                self.ok("Hydration: tools", f"{len(tools)} tools hydrated from DB")
            else:
                self.fail("Hydration: tools", "hydration returned False despite data in DB")
        except Exception as e:
            self.fail("Hydration: tools", str(e))
        finally:
            base_mod._tool_registry = old_registry

    async def check_capability_hydration(self):
        """Simulate _hydrate_capabilities_from_db."""
        count = await table_count("capabilities_catalog")
        if count < 1:
            self.skip("Hydration: capabilities", "capabilities_catalog is empty")
            return

        from app.lifespan import _hydrate_capabilities_from_db
        from app.services.nexus.capability_registry import get_capability_registry
        import app.services.nexus.capability_registry as cap_mod

        old_registry = cap_mod._capability_registry
        cap_mod._capability_registry = None
        try:
            result = await _hydrate_capabilities_from_db()
            if result:
                registry = get_capability_registry()
                caps = registry.list_all()
                self.ok("Hydration: capabilities", f"{len(caps)} capabilities hydrated from DB")
            else:
                self.fail("Hydration: capabilities", "hydration returned False despite data in DB")
        except Exception as e:
            self.fail("Hydration: capabilities", str(e))
        finally:
            cap_mod._capability_registry = old_registry

    def check_handler_resolution(self):
        """Test _resolve_handler_ref."""
        from app.lifespan import _resolve_handler_ref

        cls = _resolve_handler_ref("app.tools.browser_ping.BrowserPingTool")
        if cls is not None and cls.__name__ == "BrowserPingTool":
            self.ok("Handler resolution", "BrowserPingTool resolved")
        else:
            self.fail("Handler resolution", "could not resolve BrowserPingTool")

        cls = _resolve_handler_ref("app.tools.nonexistent.Foo")
        if cls is None:
            self.ok("Handler resolution (unknown)", "correctly returned None")
        else:
            self.fail("Handler resolution (unknown)", "should have returned None")

    # ── 4. Memory Service ─────────────────────────────────────────

    async def check_memory_service(self):
        """Verify MemoryService works with mocked session."""
        from unittest.mock import AsyncMock, MagicMock
        from app.services.memory_service import MemoryService

        # Agent memory store
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        svc = MemoryService(db=mock_session)
        result = await svc.store(
            agent_id="dr-test",
            content="This memory survived the disaster",
            memory_type="episodic",
            importance=0.99,
        )
        if result and result["content"] == "This memory survived the disaster":
            self.ok("Memory: agent store", "store succeeded")
        else:
            self.fail("Memory: agent store", "store returned unexpected result")

        # KV store
        mock_session2 = AsyncMock()
        mock_session2.add = MagicMock()
        mock_session2.flush = AsyncMock()
        mock_session2.execute = AsyncMock()

        svc2 = MemoryService(db=mock_session2)
        result2 = await svc2.store(key="dr:test", value={"status": "alive"})
        if result2 is True:
            self.ok("Memory: KV store", "store succeeded")
        else:
            self.fail("Memory: KV store", "store returned False")

    # ── 5. Topology & Materialization Models ──────────────────────

    def check_topology_models(self):
        from app.models.topology_models import TopologySnapshot, TopologyNode, TopologyEdge
        if (TopologySnapshot.__tablename__ == "topology_snapshots"
                and TopologyNode.__tablename__ == "topology_nodes"
                and TopologyEdge.__tablename__ == "topology_edges"):
            self.ok("Models: topology", "3 models importable")
        else:
            self.fail("Models: topology", "unexpected table names")

    def check_materialization_model(self):
        from app.models.materialization_models import MaterializationState
        if MaterializationState.__tablename__ == "materialization_state":
            self.ok("Models: materialization", "importable")
        else:
            self.fail("Models: materialization", "unexpected table name")

    # ── 6. Reconstruction Report ──────────────────────────────────

    async def print_report(self):
        tables = {
            "tools_catalog": "tools",
            "tool_versions": "tool versions",
            "capabilities_catalog": "capabilities",
            "capability_versions": "capability versions",
            "agent_templates": "agent templates",
            "agent_template_versions": "template versions",
            "memory_entries": "memories",
            "materialization_state": "materialization states",
            "topology_snapshots": "topology snapshots",
            "topology_nodes": "topology nodes",
            "topology_edges": "topology edges",
        }

        report = {}
        for table, label in tables.items():
            report[label] = await table_count(table)

        print("\n" + "=" * 60)
        print("  DISASTER RECOVERY RECONSTRUCTION REPORT")
        print("=" * 60)
        print(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
        print("-" * 60)
        for label, count in report.items():
            icon = "✅" if count > 0 else "⚠️"
            print(f"  {icon} {label:.<40} {count:>6}")
        print("-" * 60)
        tools = report.get("tools", 0)
        caps = report.get("capabilities", 0)
        tpls = report.get("agent templates", 0)
        print(f"  Reconstruction: {tools} tools, {caps} capabilities, {tpls} templates")
        print("=" * 60)

    # ── Run All ───────────────────────────────────────────────────

    async def run_all(self):
        print("\n🔍 Disaster Recovery Acceptance Test (Phase 1.5)")
        print("=" * 60)

        if not db_reachable():
            print("⏭️  Database not reachable — skipping all tests")
            print("   Run inside the backend container: docker compose exec backend python /app/dr_test.py")
            return

        print("\n1. Schema Verification")
        await self.check_schemas()

        print("\n2. Data Population")
        await self.check_data_population()

        print("\n3. Hydration Pipeline")
        await self.check_tool_hydration()
        await self.check_capability_hydration()
        self.check_handler_resolution()

        print("\n4. Memory Service")
        await self.check_memory_service()

        print("\n5. Models")
        self.check_topology_models()
        self.check_materialization_model()

        print("\n6. Reconstruction Report")
        await self.print_report()

        # Summary
        print(f"\n{'=' * 60}")
        print(f"  RESULTS: {self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        print(f"{'=' * 60}")
        for d in self.details:
            print(d)
        print()

        if self.failed > 0:
            print(f"❌ DISASTER RECOVERY TEST FAILED ({self.failed} failures)")
            sys.exit(1)
        else:
            print("✅ DISASTER RECOVERY TEST PASSED")
            sys.exit(0)


# ── Pytest wrappers (for running via pytest) ───────────────────────

try:
    import pytest

    @pytest.fixture(scope="session")
    def _db_check():
        if not db_reachable():
            pytest.skip("DB not reachable — run inside backend container")

    class TestDisasterRecovery:
        """Disaster recovery — runs the acceptance suite."""

        @pytest.mark.asyncio
        async def test_full_dr_suite(self, _db_check):
            runner = DRTestRunner()
            await runner.run_all()
            assert runner.failed == 0, (
                f"Disaster recovery had {runner.failed} failures"
            )

except ImportError:
    pass


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(DRTestRunner().run_all())
