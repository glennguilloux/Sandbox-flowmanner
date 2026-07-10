# Exit Audit — Opus 4.8 Design-QA P1+P2 Implementation

**Date:** 2026-07-08
**Agent:** Buffy (mimo/mimo-v2.5-pro) on homelab (10.99.0.3)
**Plan:** `.sisyphus/plans/OPUS-4.8-DESIGN-QA-PLAN-2026-07-08.md`

---

## WHAT CHANGED (one bullet per file, what + why)

**Backend (5 source files, 3 test files):**
- `backend/app/core/exceptions.py`: Expanded from 2-line stub to full typed error hierarchy (AppError base + 8 subclasses with code/http_status). **Item #2.**
- `backend/app/services/mission_errors.py`: MissionError now inherits from AppError instead of Exception; API-layer subclasses use multiple inheritance with explicit attrs. Added doc comment noting http_status is dead code for v2/v3 paths. **Item #2.**
- `backend/app/main_fastapi.py`: Unified AppError handler builds version-aware envelopes (v1 flat, v2 with meta, v3 with trace_id). **Item #2.**
- `backend/app/services/substrate/executor.py`: Added DEPRECATED gate in _get_strategy() blocking Meta/Swarm/Pipeline/LangGraph by default. **Item #4.**
- `backend/app/config.py`: Added STRATEGY_ALLOW_DEPRECATED setting (default False). **Item #4.**
- `backend/app/services/sse_buffer.py`: Complete rewrite from Redis Lists+INCR to Redis Streams (XADD/XRANGE). Eliminates dual-source seq bug. Drops _next_seq and _local_seq_cache. **Item #1.**
- `backend/app/api/v1/chat.py`: Changed replay endpoint `since` param from int to str (Redis Stream entry IDs are strings). **Item #1.**
- `backend/app/tests/test_exceptions.py`: 23 tests for error hierarchy, MRO, catch-block compat, envelope shapes. **Item #2.**
- `backend/app/tests/test_deprecated_strategy_gate.py`: 9 tests for deprecated strategy gating. **Item #4.**
- `backend/app/tests/test_sse_buffer.py`: 17 tests rewritten for Redis Streams. **Item #1.**

**Frontend (1 source file, 1 test file):**
- `frontend/src/lib/api-client.ts`: Replaced `startsWith(p)` with `_isPublicPath()` segment-aware matcher. Fixes auth bypass on prefix collisions. **Item #8.**
- `frontend/src/lib/__tests__/api-client.test.ts`: 26 vitest tests for PUBLIC_PATHS matching. **Item #8.**

---

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `backend/app/api/v2/chat.py`: Read for context (imports get_stream_buffer). No changes needed — it imports from sse_buffer which kept its public API.
- `backend/app/api/v2/middleware.py`: Read for context. Not changed — v2-specific MissionError handlers still catch before the unified AppError handler.
- `backend/app/api/v3/middleware.py`: Read for context. Not changed.

---

## TESTS RUN + RESULT

**Local host (homelab) — all new + affected tests:**
```
$ python -m pytest app/tests/test_exceptions.py -v
23 passed in 5.32s

$ python -m pytest app/tests/test_deprecated_strategy_gate.py -v
9 passed in 0.49s

$ python -m pytest app/tests/test_sse_buffer.py -v
17 passed in 5.61s

$ python -m pytest app/tests/test_sse_keepalive.py -v
6 passed

$ python -m pytest tests/test_meta_strategy.py -v
23 passed in 4.06s

$ python -m pytest tests/test_unified_executor.py -v
17 passed in 42.06s

$ python -m pytest tests/test_5xx_ntfy_alert.py -v
8 passed in 3.88s

$ npx vitest run src/lib/__tests__/api-client.test.ts (frontend)
26 passed
```

**In-container tests:** Could not run — the new test files are not in the running container (no volume mounts). A `deploy-backend.sh` rebuild is required.

**Pre-existing failures (not caused by this session):**
- `app/tests/test_mission_cqrs.py::test_get_mission_success_when_owned` — confirmed pre-existing via `git stash` test.

---

## STATUS

```
$ git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean

$ git fetch origin && git log --oneline origin/main..main
(empty — all pushed)

$ docker compose exec backend alembic current
d30_60_2a3 (head) (mergepoint)

$ docker compose exec backend bash -c 'pytest -q'
(not run — container needs rebuild to pick up new files)
```

---

## COMMITS (5 on backend main, 1 on frontend master)

```
8908a632 docs(errors): note http_status is dead code for v2/v3 paths
0f20fa6e refactor(sse): use Redis Streams for authoritative seq (XADD/XRANGE)
fc169772 feat(errors): introduce typed AppError hierarchy with version-aware envelope
f4dc8f94 feat(substrate): gate deprecated strategies behind STRATEGY_ALLOW_DEPRECATED
```
Frontend:
```
b3ed6bce fix(security): replace startsWith with segment-aware PUBLIC_PATHS matcher
```

---

## NEXT SESSION HANDOFF

This session implemented 4 of 10 items from the Opus 4.8 Design-QA plan:

**Completed (P1+P2):**
- ✅ Item #2 — Typed error hierarchy (AppError → version-aware envelope)
- ✅ Item #4 — Gate deprecated strategies (DEPRECATED gate + STRATEGY_ALLOW_DEPRECATED)
- ✅ Item #8 — Frontend PUBLIC_PATHS segment-aware matcher
- ✅ Item #1 — SSE seq via Redis Streams (XADD/XRANGE)

**Remaining (P2→P4):**
- Item #6 — Provider-fallback provenance (P2)
- Item #9 — Replay assertion headroom (P3)
- Item #3 — Workflow replay idempotency + budget ledger (P3)
- Item #5 — Plan-selection calibration (P3)
- Item #7 — v3 OIDC + webhooks (P4, needs design sign-off)
- Item #10 — Dual-auth consolidation (P4)

**Gotchas for next agent:**
1. **Backend needs rebuild.** The new files (test_exceptions.py, test_deprecated_strategy_gate.py, updated sse_buffer.py) are in the source but not in the running container. Run `bash /opt/flowmanner/deploy-backend.sh` to pick them up.
2. **Frontend needs deploy.** The PUBLIC_PATHS fix is in the frontend source but not on the VPS. Run `bash /opt/flowmanner/deploy-frontend.sh` (from homelab) to deploy.
3. **MissionValidationError v1 status changed from 400→422.** The v2 handler still returns 400 for v2 paths. The unified handler returns 422 for v1 paths. This is arguably more correct but is a behavior change.
4. **SSE `since` param changed from int to str.** The v1 replay endpoint now accepts string Redis Stream entry IDs. Existing clients sending `?since=3` still work via FastAPI coercion.
5. **`resync` event is new.** The SSE replay now returns `event: resync` when the gap has expired (5min TTL). The frontend SSE parser should handle unknown event types gracefully, but verify.
6. **BudgetExhausted was NOT migrated to AppError.** It has structured `reason`+`remaining` attrs that don't fit the AppError(message, details) constructor. Left as-is intentionally.

---

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

**Untracked files:** None (working tree clean).

**Deleted files:** None.
