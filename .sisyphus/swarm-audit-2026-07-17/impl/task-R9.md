# R9 — Marketplace seed/gate + Community decision + lightweight Changelog

**Context:** Swarm audit REPORT.md §4 R9 + PM ledger.
- `backend/app/api/v2/marketplace.py` is fully built but has **no seed supply** →
  empty storefront signals a ghost town.
- `backend/app/models/community_models.py` has a tested model but NO router/table
  bootstrap (docstring `:5` admits the router is missing) — dead weight or finish.
- `roadmap`/`changelog` were deleted in a prior pruning phase (VERIFIED); a
  lightweight read-only changelog is cheap credibility.

**Your task:**
1. Seed the marketplace: write a seed script (reuse the `docker-entrypoint.py:42`
   startup-hook pattern) that lists the built-in mission templates +
   personas as `price=0` "install" marketplace listings, so the catalog is never
   empty. OR, if monetization isn't ready, add a "coming soon" gate to the
   marketplace storefront (pick the seed approach; it's the higher-value one).
2. Add a lightweight read-only Changelog endpoint reusing the existing
   `backend/app/api/v2/roadmap.py` / `blog.py` read-only pattern (derive from
   deploy/PR history or a small `changelog` table — your call, keep it S-effort).
3. Community: DO NOT delete or build it silently. Produce a recommendation +
   a ready patch (either add `community.py` router + Alembic migration, OR delete
   the orphan `community_models.py` + test) and **block-for-review** for the human
   decision.

**Constraints:** Backend only. No frontend storefront work. Commit the marketplace
seed + changelog to this branch; for Community, emit the patch + recommendation and
block-for-review. Do NOT push, deploy, or merge.
