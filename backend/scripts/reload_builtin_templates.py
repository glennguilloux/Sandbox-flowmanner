#!/usr/bin/env python3
"""Reload built-in mission templates from the baked seed file.

Intended to run (a) from the Docker entrypoint on every container boot
(self-healing: the gallery always matches the image's seed file) and
(b) from deploy-backend.sh after a deploy.

Why this exists:
  seed_templates.seed() is IDEMPOTENT — it skips the whole insert if any
  built-in rows already exist. That means a rebuilt image never updates the
  live gallery, and the DB silently drifts from the file forever (observed:
  DB had 10 built-ins while the file defined 47).

This script does a CORRECT reconcile instead:
  - UPSERT by name: UPDATE existing built-in rows (preserves usage_count),
    INSERT new ones.
  - DELETE built-in rows whose name is no longer in the seed file
    (removed templates).
So after boot/deploy the gallery == the seed file, idempotently and
without losing per-template usage stats.

Best-effort: any DB error is logged and swallowed so a transient DB
outage at boot NEVER blocks container startup (the entrypoint still execs
uvicorn afterwards).
"""

from __future__ import annotations

import asyncio
import os
import sys

# The baked seed file lives at /app/seed_templates.py (copied by the Dockerfile
# for A2, and by deploy-backend.sh's reload step for A). That is the ONLY
# authoritative seed path — do NOT also search /tmp, or a stray
# /tmp/seed_templates.py would shadow the real one.
APP_DIR = os.environ.get("APP_DIR", "/app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


async def reload_builtin_templates() -> dict:
    # Imported lazily so a failure here is catchable, not a hard crash.
    from sqlalchemy import select

    import seed_templates
    from app.database import AsyncSessionLocal
    from app.models.mission_advanced_models import MissionTemplate

    async with AsyncSessionLocal() as db:
        existing = {
            r.name: r
            for r in (await db.execute(select(MissionTemplate).where(MissionTemplate.is_builtin.is_(True))))
            .scalars()
            .all()
        }
        file_names = {t["name"] for t in seed_templates.TEMPLATES}

        inserted = updated = deleted = 0
        for tpl in seed_templates.TEMPLATES:
            rec = existing.pop(tpl["name"], None)
            if rec is None:
                db.add(
                    MissionTemplate(
                        id=__import__("uuid").uuid4(),
                        user_id=1,
                        name=tpl["name"],
                        description=tpl["description"],
                        category=tpl["category"],
                        icon=tpl["icon"],
                        is_public=True,
                        is_builtin=True,
                        mission_type=None,
                        priority=tpl["priority"],
                        default_plan=tpl["default_plan"],
                        default_tasks=None,
                        default_constraints=None,
                        tags=None,
                        usage_count=0,
                    )
                )
                inserted += 1
            else:
                rec.description = tpl["description"]
                rec.category = tpl["category"]
                rec.icon = tpl["icon"]
                rec.priority = tpl["priority"]
                rec.default_plan = tpl["default_plan"]
                updated += 1

        # Any built-in left in `existing` is no longer in the seed file.
        for stale in existing.values():
            await db.delete(stale)
            deleted += 1

        await db.commit()
        return {
            "inserted": inserted,
            "updated": updated,
            "deleted": deleted,
            "total_file": len(seed_templates.TEMPLATES),
        }


def main() -> int:
    try:
        result = asyncio.run(reload_builtin_templates())
        print(
            f"[reload-builtin] OK: inserted={result['inserted']} "
            f"updated={result['updated']} deleted={result['deleted']} "
            f"(file defines {result['total_file']})",
            file=sys.stderr,
        )
        return 0
    except Exception as exc:
        print(f"[reload-builtin] SKIPPED (error): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0  # never block container startup


if __name__ == "__main__":
    raise SystemExit(main())
