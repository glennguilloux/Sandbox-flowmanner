# Dual-Write Decision — Executed

**Date:** 2026-07-04
**Status:** ✅ EXECUTED — 2026-07-07

Dual-write code fully removed from `backend/app/`. Dead scripts deleted. Mission is canonical; Blueprint+Run retained as read model.

## Context

The Blueprint+Run model was introduced as a v2 alternative to the Mission model. A dual-write layer was implemented to keep both in sync. Glenn said "DeepSeek started too early" on the dual-write, indicating it was premature.

## Options

### (a) Mission canonical, Blueprint+Run optional (RECOMMENDED)

- Keep Mission as the working production model (all 14 commands + 14 queries via `_mission_cqrs`)
- Remove the dual-write layer (stop writing to Blueprint+Run on every mission mutation)
- Keep Blueprint+Run tables as a **read model** — they can be populated lazily or on-demand for v2 API consumers
- The v2 `/api/v2/blueprints` endpoints continue to work via a read-through adapter

**Why this is correct:**
1. Mission is battle-tested — it's been in production for months with full CQRS coverage
2. Blueprint+Run was designed for a future that hasn't shipped yet (v2 API, per-step observability)
3. The dual-write adds complexity without immediate value — every mission mutation pays the cost of writing to 2 extra tables
4. Removing the dual-write reduces write latency and eliminates sync consistency bugs
5. Blueprint+Run can be reintroduced as a first-class model when v2 API adoption justifies it

### (b) Blueprint+Run canonical, Mission becomes a view

- Make Blueprint+Run the source of truth
- Mission becomes a read-only projection
- Requires migrating all 14 CQRS command handlers to write to Blueprint+Run
- Requires migrating all frontend code from Mission endpoints to v2 Blueprint endpoints

**Why this is NOT recommended now:**
1. The v2 API surface is incomplete — only a subset of Mission functionality is replicated
2. The frontend exclusively uses v1 Mission endpoints
3. Migrating all CQRS handlers is a multi-week effort with high regression risk
4. No clear user-facing benefit in the near term

## Recommendation

**Go with (a).** Remove the dual-write, keep Mission canonical, preserve Blueprint+Run as a read model. This:
- Reduces complexity immediately
- Eliminates write-path latency overhead
- Preserves the option to promote Blueprint+Run later
- Aligns with the current production reality

## Implementation — Completed ✅

1. ✅ All `dual_write` calls removed from `_mission_cqrs/commands.py`
2. ✅ `DualWriteService` deleted (zero references remain in `backend/app/`)
3. ⏳ Lazy population path for Blueprint+Run — deferred to v2 API adoption phase
4. ✅ Blueprint+Run migration files preserved (tables not dropped)
5. ✅ v2 endpoints read from Blueprint+Run via existing adapter

## Files changed

- `backend/app/api/_mission_cqrs/commands.py` — dual-write calls removed
- `backend/app/services/dual_write_service.py` — deleted
- `backend/scripts/backfill_dual_write.py` — deleted (2026-07-07)
- `backend/scripts/prove_dual_write_complete.py` — deleted (2026-07-07)
- `backend/scripts/renumber_dual_write_blueprints.py` — deleted (2026-07-07)
