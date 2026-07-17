#!/usr/bin/env python3
"""Seed initial changelog entries (R9 lightweight read-only changelog).

Idempotent: UPSERT by ``version`` label. Re-run safe. Mirrors the
``seed_marketplace.py`` / ``reload_builtin_templates.py`` entrypoint-hook
pattern. Best-effort: a DB error is logged and swallowed so it never blocks
container startup.

Run from the Docker entrypoint on boot and from ``deploy-backend.sh`` after a
deploy.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

APP_DIR = os.environ.get("APP_DIR", "/app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Curated initial entries derived from recent shipped phases (roadmap/git
# history). Keep titles terse; ``summary`` is the card blurb, ``body`` the
# detail. New shipped phases append here.
SEED_ENTRIES: list[dict] = [
    {
        "version": "R9",
        "title": "Marketplace seed, Changelog & Community decision",
        "summary": "Marketplace now ships with built-in templates + 200+ agent personas as free listings; a read-only changelog API lands; community module decision pending review.",
        "body": "The marketplace storefront is no longer empty: built-in mission templates and the in-repo agent persona library are seeded as price=0 'install' listings on every boot. A lightweight, read-only /api/v2/changelog surface provides release-notes credibility. The community module remains a pending human decision (build vs delete).",
        "category": "release",
        "is_featured": True,
        "released_at": "2026-07-17",
        "sort_order": 90,
    },
    {
        # Preserved from the legacy v1 changelog_entries row (id=1, version='0.2.0',
        # "Platform Hardening", published 2026-05-21). That orphaned table is dropped by
        # the 20260717b_drop_legacy_changelog migration; this re-seeds the one real
        # historical note under R9's UUID schema so it is not lost.
        "version": "0.2.0",
        "title": "Platform Hardening",
        "summary": "Phase 7-15 improvements: CI/CD pipeline, automated backups, Sentry error tracking, learning service, email delivery, full-text search, data export, feature flags, and developer experience improvements.",
        "body": "Phase 7-15 improvements: CI/CD pipeline, automated backups, Sentry error tracking, learning service, email delivery, full-text search, data export, feature flags, and developer experience improvements.",
        "category": "feature",
        "is_featured": False,
        "released_at": "2026-05-21",
        "sort_order": 60,
    },
    {
        "version": "T1",
        "title": "Blog + Roadmap read-only APIs",
        "summary": "Public blog/case-study and roadmap read surfaces shipped (DB-backed).",
        "body": "Introduced DB-backed blog_posts/blog_tags and roadmap_items tables with read-only v2 routers, mirroring the marketing-content intent of the frontend SDK.",
        "category": "release",
        "is_featured": False,
        "released_at": "2026-07-09",
        "sort_order": 80,
    },
    {
        "version": "Phase 10.1",
        "title": "Blueprint / Run endpoints",
        "summary": "Next-gen Blueprint + Run v2 endpoints for the workflow substrate.",
        "body": "Added /api/v2/blueprints and /api/v2/runs backed by the substrate execution engine; Mission remains the sole source of truth (dual-write removed 2026-07-07).",
        "category": "release",
        "is_featured": False,
        "released_at": "2026-07-01",
        "sort_order": 70,
    },
]


async def seed_changelog() -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.changelog_models import ChangelogEntry

    inserted = updated = 0
    async with AsyncSessionLocal() as db:
        for e in SEED_ENTRIES:
            existing = await db.scalar(select(ChangelogEntry).where(ChangelogEntry.version == e["version"]))
            released = datetime.fromisoformat(e["released_at"]).replace(tzinfo=UTC)
            if existing is None:
                db.add(
                    ChangelogEntry(
                        version=e["version"],
                        title=e["title"],
                        summary=e["summary"],
                        body=e["body"],
                        category=e["category"],
                        is_featured=e["is_featured"],
                        released_at=released,
                        sort_order=e["sort_order"],
                    )
                )
                inserted += 1
            else:
                existing.title = e["title"]
                existing.summary = e["summary"]
                existing.body = e["body"]
                existing.category = e["category"]
                existing.is_featured = e["is_featured"]
                existing.released_at = released
                existing.sort_order = e["sort_order"]
                updated += 1
        await db.commit()
        return {"inserted": inserted, "updated": updated, "total": len(SEED_ENTRIES)}


def main() -> int:
    try:
        result = asyncio.run(seed_changelog())
        print(
            f"[seed-changelog] OK: inserted={result['inserted']} "
            f"updated={result['updated']} (seed defines {result['total']})",
            file=sys.stderr,
        )
        return 0
    except Exception as exc:
        print(f"[seed-changelog] SKIPPED (error): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0  # never block container startup


if __name__ == "__main__":
    raise SystemExit(main())
