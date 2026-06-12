"""Chaos test helper — acquires a lease then blocks (simulating a hung/crashed worker).

Usage::

    DATABASE_URL=postgresql+asyncpg://... python tests/_helpers/chaos_lease_holder.py <worker_id> <run_id> <ttl_seconds>

This script is spawned by the chaos tests to simulate a crashed worker.
It acquires a lease using the chunk-1 primitives, prints "OK" to stdout,
then blocks on stdin waiting for a signal.  The parent process sends
SIGKILL to simulate a hard crash.  The lease is left orphaned.

If ``DATABASE_URL`` is set in the environment, it overrides the default
from ``app.config`` — this allows the test host to point at ``localhost``
instead of the Docker-internal hostname.
"""

import asyncio
import os
import sys

# Ensure the backend package is importable.
sys.path.insert(0, ".")

# Override DATABASE_URL BEFORE importing app modules so the engine picks it up.
# The test host passes a DATABASE_URL with 'localhost' as hostname.
_env_db_url = os.environ.get("DATABASE_URL")
if _env_db_url:
    os.environ["DATABASE_URL"] = _env_db_url  # Ensure it's set for pydantic-settings

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.substrate.leases import try_claim_lease  # noqa: E402


async def main() -> None:
    worker_id = sys.argv[1]
    run_id = sys.argv[2]
    ttl_seconds = int(sys.argv[3])

    async with AsyncSessionLocal() as db:
        ok = await try_claim_lease(db, worker_id, run_id, ttl_seconds=ttl_seconds)
        await db.commit()

    if ok:
        print("OK", flush=True)
    else:
        print("FAIL", flush=True)
        sys.exit(1)

    # Block on stdin — the parent will send SIGKILL to simulate a crash.
    # This ensures the process is alive when killed (not just exited).
    sys.stdin.read()


if __name__ == "__main__":
    asyncio.run(main())
