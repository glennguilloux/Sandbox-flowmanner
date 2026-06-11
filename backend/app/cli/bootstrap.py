"""Deterministic bootstrap command — Phase 3.4.

A single, idempotent command that brings the system from an empty or
partially-populated state to fully operational.  Safe to run multiple
times (converges to the same state).

Steps:
1. Verify DB connectivity
2. Run pending Alembic migrations
3. Seed agent templates from disk (idempotent)
4. Import builtin tools into tools_catalog (idempotent upsert)
5. Import builtin capabilities into capabilities_catalog (idempotent upsert)
6. Import agent-to-tool bindings (idempotent upsert)
7. Seed topology snapshot (idempotent — skips if exists)
8. Rebuild Qdrant index from DB (idempotent)
9. Verify system health

Usage:
    python -m app.cli.bootstrap
    python -m app.cli.bootstrap --skip-migrations
    python -m app.cli.bootstrap --skip-qdrant
    python -m app.cli.bootstrap --dry-run
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bootstrap")


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class StepResult:
    name: str
    status: StepStatus = StepStatus.PENDING
    message: str = ""
    duration_ms: float = 0.0


@dataclass
class BootstrapReport:
    steps: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def all_ok(self) -> bool:
        return all(s.status in (StepStatus.OK, StepStatus.SKIPPED) for s in self.steps)

    def summary(self) -> str:
        lines = []
        for s in self.steps:
            icon = {
                "ok": "✅",
                "skipped": "⏭️",
                "failed": "❌",
                "running": "⏳",
                "pending": "⏸️",
            }
            lines.append(f"  {icon.get(s.status.value, '?')} {s.name} — {s.status.value} ({s.duration_ms:.0f}ms)")
            if s.message:
                lines.append(f"      {s.message}")
        lines.append(f"\n  Total: {self.total_duration_ms:.0f}ms — {'ALL OK' if self.all_ok else 'FAILURES DETECTED'}")
        return "\n".join(lines)


async def bootstrap(
    *,
    skip_migrations: bool = False,
    skip_qdrant: bool = False,
    dry_run: bool = False,
) -> BootstrapReport:
    """Run the full deterministic bootstrap sequence.

    Args:
        skip_migrations: Skip Alembic migration step.
        skip_qdrant: Skip Qdrant reindex step.
        dry_run: Report what would be done without making changes.

    Returns:
        BootstrapReport with per-step results.
    """
    report = BootstrapReport()
    start = time.monotonic()

    steps = [
        ("1. Verify DB connectivity", _step_verify_db),
        ("2. Run pending migrations", _step_migrations),
        ("3. Seed agent templates", _step_seed_agent_templates),
        ("4. Import builtin tools", _step_import_tools),
        ("5. Import builtin capabilities", _step_import_capabilities),
        ("6. Import agent-tool bindings", _step_import_bindings),
        ("7. Seed topology snapshot", _step_seed_topology),
        ("8. Rebuild Qdrant index", _step_rebuild_qdrant),
        ("9. Verify system health", _step_verify_health),
    ]

    for step_name, step_fn in steps:
        result = StepResult(name=step_name)
        report.steps.append(result)

        # Skip checks
        if skip_migrations and "migration" in step_name.lower():
            result.status = StepStatus.SKIPPED
            result.message = "Skipped (--skip-migrations)"
            continue
        if skip_qdrant and "qdrant" in step_name.lower():
            result.status = StepStatus.SKIPPED
            result.message = "Skipped (--skip-qdrant)"
            continue

        result.status = StepStatus.RUNNING
        step_start = time.monotonic()

        try:
            if dry_run:
                result.status = StepStatus.SKIPPED
                result.message = "Dry run — would execute"
            else:
                msg = await step_fn()
                result.status = StepStatus.OK
                result.message = msg
        except Exception as e:
            result.status = StepStatus.FAILED
            result.message = f"{type(e).__name__}: {e}"
            logger.error("Step '%s' failed: %s", step_name, e)
            # Stop on critical failures (DB, migrations)
            if "db" in step_name.lower() or "migration" in step_name.lower():
                break

        result.duration_ms = (time.monotonic() - step_start) * 1000

    report.total_duration_ms = (time.monotonic() - start) * 1000
    return report


# ── Step implementations ───────────────────────────────────────────


async def _step_verify_db() -> str:
    """Verify PostgreSQL is reachable and the database exists."""
    from sqlalchemy import text

    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1

        # Count key tables
        result = await session.execute(
            text(
                """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'public'
        """
            )
        )
        table_count = result.scalar()

    return f"DB connected, {table_count} tables found"


def _get_backend_root() -> str:
    """Return the absolute path to the backend root (where alembic.ini lives)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _step_migrations() -> str:
    """Run pending Alembic migrations."""
    import subprocess

    backend_root = _get_backend_root()
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=backend_root,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed: {proc.stderr.strip()}")

    output = proc.stdout.strip()
    if "upgrade" in output.lower() or "running" in output.lower():
        return f"Migrations applied: {output.splitlines()[-1]}"
    return "All migrations already applied (head is current)"


async def _step_seed_agent_templates() -> str:
    """Seed agent templates from disk (idempotent)."""
    from app.database import AsyncSessionLocal
    from app.services.agent_service import seed_agent_templates

    async with AsyncSessionLocal() as session:
        result = await seed_agent_templates(session)
        await session.commit()

    return f"{result['total']} total ({result['new']} new, {result['updated']} updated)"


async def _run_script(module_name: str) -> str:
    """Run a script from the scripts/ directory as a subprocess.

    Scripts live at <backend_root>/scripts/<module_name>.py and are executed
    directly by file path.  Each script already does its own ``sys.path``
    setup so it can import the ``app`` package.
    """
    import subprocess

    backend_root = _get_backend_root()
    script_path = os.path.join(backend_root, "scripts", f"{module_name}.py")
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")

    proc = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=backend_root,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"scripts/{module_name}.py failed (exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "ok"


async def _step_import_tools() -> str:
    """Import builtin tools into tools_catalog (idempotent upsert)."""
    return await _run_script("import_builtin_tools")


async def _step_import_capabilities() -> str:
    """Import builtin capabilities into capabilities_catalog (idempotent upsert)."""
    return await _run_script("import_builtin_capabilities")


async def _step_import_bindings() -> str:
    """Import agent-to-tool bindings from agent template definitions."""
    return await _run_script("import_bindings")


async def _step_seed_topology() -> str:
    """Seed topology snapshot (idempotent — skips if exists)."""
    return await _run_script("seed_topology")


async def _step_rebuild_qdrant() -> str:
    """Rebuild Qdrant search index from DB catalogs."""
    from app.database import AsyncSessionLocal
    from app.services.tool_discovery_service import get_discovery_service

    service = get_discovery_service()

    async with AsyncSessionLocal() as session:
        result = await service.reindex_from_db(session)

    indexed = result.get("total_indexed", 0)
    return f"{indexed} tools/capabilities indexed in Qdrant"


async def _step_verify_health() -> str:
    """Verify all subsystems are operational."""
    from sqlalchemy import text

    from app.database import AsyncSessionLocal

    checks = []

    # PostgreSQL
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks.append("PostgreSQL: ok")
    except Exception as e:
        checks.append(f"PostgreSQL: FAILED ({e})")

    # Redis
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks.append("Redis: ok")
    except Exception as e:
        checks.append(f"Redis: FAILED ({e})")

    # Qdrant
    try:
        import httpx

        from app.config import settings

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.QDRANT_URL}/healthz")
            if resp.status_code == 200:
                checks.append("Qdrant: ok")
            else:
                checks.append(f"Qdrant: FAILED (status {resp.status_code})")
    except Exception as e:
        checks.append(f"Qdrant: FAILED ({e})")

    # Catalog counts
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT count(*) FROM tools_catalog"))
            tools = result.scalar()
            result = await session.execute(text("SELECT count(*) FROM capabilities_catalog"))
            caps = result.scalar()
            result = await session.execute(text("SELECT count(*) FROM agent_templates"))
            templates = result.scalar()
        checks.append(f"Catalogs: {tools} tools, {caps} capabilities, {templates} templates")
    except Exception as e:
        checks.append(f"Catalogs: FAILED ({e})")

    failed = [c for c in checks if "FAILED" in c]
    if failed:
        raise RuntimeError(f"Health check failures: {'; '.join(failed)}")

    return " | ".join(checks)


# ── CLI entry point ────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Flowmanner deterministic bootstrap — brings the system to a fully operational state.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.cli.bootstrap                # Full bootstrap
  python -m app.cli.bootstrap --dry-run      # Report what would happen
  python -m app.cli.bootstrap --skip-qdrant  # Skip Qdrant reindex
        """,
    )
    parser.add_argument("--skip-migrations", action="store_true", help="Skip Alembic migration step")
    parser.add_argument("--skip-qdrant", action="store_true", help="Skip Qdrant reindex step")
    parser.add_argument("--dry-run", action="store_true", help="Report steps without executing")

    args = parser.parse_args()

    report = asyncio.run(
        bootstrap(
            skip_migrations=args.skip_migrations,
            skip_qdrant=args.skip_qdrant,
            dry_run=args.dry_run,
        )
    )

    print("\n" + "=" * 60)
    print("  FLOWMANNER BOOTSTRAP REPORT")
    print("=" * 60)
    print(report.summary())
    print("=" * 60 + "\n")

    sys.exit(0 if report.all_ok else 1)


if __name__ == "__main__":
    main()
