"""Retroactive memory store sweep runner — GOV-1.3c.

One-time historical poison sweep over the existing durable memory stores
(``personal_memory_claims`` + ``memory_entries``), surfacing hits into the
HITL inbox for human review (GOV-1.1 drain). Run AFTER the GOV-1.1 build is
deployed and verified. This clears the historical exposure window that
1.3a's write-time scan does not cover.

Usage:
    cd /opt/flowmanner
    # Safe preview — scan + report, create nothing, annotate nothing:
    docker compose exec backend python scripts/retroactive_memory_sweep.py --dry-run
    # Real run — route flagged rows to the inbox:
    docker compose exec backend python scripts/retroactive_memory_sweep.py
    # Scope to one workspace + smaller batches:
    docker compose exec backend python scripts/retroactive_memory_sweep.py \
        --workspace <ws-uuid> --batch-size 100

Idempotent: re-running does not duplicate inbox items — already-surfaced
rows carry a ``retro_sweep_flagged`` marker and are skipped.

IMPORTANT: this runner only touches the live DB; it does not deploy anything.
Glenn reviews the report and decides what to approve/delete via the inbox.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.database import AsyncSessionLocal
from app.services.memory.retroactive_memory_sweep import retroactive_memory_sweep

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("retroactive_memory_sweep")


async def _run(workspace_id: str | None, batch_size: int, dry_run: bool) -> int:
    async with AsyncSessionLocal() as db:
        findings = await retroactive_memory_sweep(
            db,
            workspace_id=workspace_id,
            batch_size=batch_size,
            dry_run=dry_run,
        )
    logger.info(
        "SUMMARY scanned=%d flagged=%d routed=%d already_flagged=%d severity_high=%d",
        findings.total_scanned,
        findings.total_flagged,
        findings.routed_items,
        findings.skipped_already_flagged,
        findings.severity_high,
    )
    return 0 if findings.total_scanned >= 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="GOV-1.3c retroactive memory store poison sweep")
    parser.add_argument("--workspace", default=None, help="Scope sweep to one workspace_id")
    parser.add_argument("--batch-size", type=int, default=200, help="Rows per query page (default 200)")
    parser.add_argument("--dry-run", action="store_true", help="Scan + report only; create no inbox items")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN — no inbox items will be created, no rows annotated")

    try:
        return asyncio.run(_run(args.workspace, args.batch_size, args.dry_run))
    except KeyboardInterrupt:  # pragma: no cover
        logger.warning("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
