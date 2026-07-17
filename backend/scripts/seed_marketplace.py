#!/usr/bin/env python3
"""Seed the marketplace catalog from built-in templates + in-repo personas.

R9 (swarm audit REPORT.md §4): ``backend/app/api/v2/marketplace.py`` is fully
built but has no seed supply — an empty storefront signals a ghost town. This
script lists the built-in mission templates + the 200+ in-repo agent
persona definitions as ``price=0`` "install" marketplace listings so the
catalog is never empty.

Intended to run from the Docker entrypoint on every container boot
(self-healing: the storefront always matches the image's baked supply) and
from ``deploy-backend.sh`` after a deploy. Mirrors the
``reload_builtin_templates.py`` startup-hook pattern.

Seed is IDEMPOTENT and reconciling:
  - UPSERT by deterministic ``artifact_id`` key (``seed:template:<name>`` /
    ``seed:persona:<domain>/<slug>``): UPDATE existing seed rows, INSERT new
    ones.
  - DELETE seed rows whose source no longer exists (removed template/persona).
So after boot/deploy the catalog's seeded section == the baked supply,
without losing user-created listings or per-listing install counts.

Best-effort: any DB error is logged and swallowed so a transient DB outage at
boot NEVER blocks container startup (the entrypoint still execs uvicorn
afterwards).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

APP_DIR = os.environ.get("APP_DIR", "/app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _item_id_template(name: str) -> str:
    """Deterministic marketplace item_id for a built-in mission template."""
    return f"seed:template:{name}"


def _item_id_persona(domain: str, slug: str) -> str:
    """Deterministic marketplace item_id for an in-repo agent persona."""
    return f"seed:persona:{domain}/{slug}"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse simple ``key: value`` frontmatter (no PyYAML dependency).

    Copied from ``app/api/v1/agent_personalities.py`` so this script has no
    extra import surface.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    _, fm_block, body = parts
    meta: dict[str, str] = {}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body.strip()


async def seed_marketplace() -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.mission_advanced_models import MissionTemplate
    from app.models.models import MarketplaceListingModel

    # Resolve the agent_definitions directory relative to the backend app,
    # matching agent_personalities.py's resolution.
    defs_dir = Path(__file__).resolve().parent.parent / "app" / "agent_definitions"

    inserted = updated = deleted = 0
    seen_item_ids: set[str] = set()

    async with AsyncSessionLocal() as db:
        # ── 1. Built-in mission templates ─────────────────────────────
        builtins = (
            (
                await db.execute(
                    select(MissionTemplate).where(MissionTemplate.is_builtin.is_(True))
                )
            )
            .scalars()
            .all()
        )
        for tpl in builtins:
            item_id = f"seed:template:{tpl.name}"
            seen_item_ids.add(item_id)
            existing = (
                await db.scalar(
                    select(MarketplaceListingModel).where(MarketplaceListingModel.artifact_id == item_id)
                )
            )
            if existing is None:
                db.add(
                    MarketplaceListingModel(
                        name=tpl.name,
                        description=tpl.description or "",
                        owner_id="system",
                        listing_type="template",
                        artifact_type="mission_template",
                        artifact_id=str(tpl.id),
                        price=0.0,
                        is_published=True,
                        status="published",
                        version="1.0.0",
                        category_id=tpl.category or "general",
                        tags="[]",
                        published_at=datetime.now(UTC),
                    )
                )
                inserted += 1
            else:
                existing.name = tpl.name
                existing.description = tpl.description or ""
                existing.category_id = tpl.category or "general"
                existing.status = "published"
                existing.is_published = True
                updated += 1

        # ── 2. In-repo agent persona definitions ─────────────────────
        if defs_dir.is_dir():
            for md in sorted(defs_dir.rglob("*.md")):
                domain_dir = md.parent.name
                slug = md.stem
                item_id = f"seed:persona:{domain_dir}/{slug}"
                seen_item_ids.add(item_id)
                try:
                    text = md.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    logger.warning("Could not read persona %s", md)
                    continue
                meta, body = _parse_frontmatter(text)
                name = meta.get("name", slug.replace("-", " ").title())
                description = meta.get("description", "")
                if not description and body:
                    description = body[:280]
                category = domain_dir.replace("_", "-")
                existing = (
                    await db.scalar(
                        select(MarketplaceListingModel).where(
                            MarketplaceListingModel.artifact_id == item_id
                        )
                    )
                )
                if existing is None:
                    db.add(
                        MarketplaceListingModel(
                            name=name,
                            description=description,
                            owner_id="system",
                            listing_type="agent",
                            artifact_type="agent_persona",
                            artifact_id=item_id,
                            price=0.0,
                            is_published=True,
                            status="published",
                            version="1.0.0",
                            category_id=category,
                            tags="[]",
                            published_at=datetime.now(UTC),
                        )
                    )
                    inserted += 1
                else:
                    existing.name = name
                    existing.description = description
                    existing.category_id = category
                    existing.status = "published"
                    existing.is_published = True
                    updated += 1

        # ── 3. Drop seed rows whose source is gone ───────────────────
        seed_rows = (
            (await db.execute(select(MarketplaceListingModel).where(MarketplaceListingModel.artifact_id.like("seed:%"))))
            .scalars()
            .all()
        )
        for row in seed_rows:
            if row.artifact_id not in seen_item_ids:
                await db.delete(row)
                deleted += 1

        await db.commit()
        return {
            "inserted": inserted,
            "updated": updated,
            "deleted": deleted,
            "templates": len(builtins),
        }


def main() -> int:
    try:
        result = asyncio.run(seed_marketplace())
        print(
            f"[seed-marketplace] OK: inserted={result['inserted']} "
            f"updated={result['updated']} deleted={result['deleted']} "
            f"(builtin templates={result['templates']})",
            file=sys.stderr,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[seed-marketplace] SKIPPED (error): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0  # never block container startup


if __name__ == "__main__":
    raise SystemExit(main())
