# Handoff — 2026-07-19 Frontend ↔ Backend API Contract + React Hook-Order Audit

**Author:** Hermes (agent) · **Reviewer/owner:** Glenn (Flowmanner principal)
**Date:** 2026-07-19
**Mode:** AUDIT + PATCH-PREP ONLY — per instruction, nothing was committed, deployed, or pushed.
This doc is the **findings + ready-to-apply fix plan**, not a merge record. The working trees are
UNCHANGED from their pre-audit state.

---

## §0 — Critical framing correction vs the brief's assumption

The brief was right that `/api/v1/plugins` 404s, but the **widespread bug is the INVERSE** of the
plugins example for most routers. The versioning middleware (`app/api/middleware/versioning.py`)
does **not** strip `/v1` from the path. Therefore:

- `/api/v1/<router>` only resolves for the **2 routers that bake `/v1` into their own prefix**
  (`usage.py` → `prefix="/v1/usage"`, `rag.py` → `prefix="/v1/rag"`).
- **Every other router** mounts at `/api/<prefix>` with **no `/v1` segment** (the v1 mount in
  `main_fastapi.py` is `app.include_router(api_v1_router)` — no `/v1` prefix).

The frontend has **many** hardcoded `/api/v1/<router>` calls that hit a literal path the router
never registered → `404`. The fix direction is **DROP `/v1`** (→ `/api/<router>...`), which is the
opposite of what plugins needed.

### Verification method (ground truth)
- Live `curl` against `https://flowmanner.com`. `401`/`405`/`422`/`200` = route matched and exists
  (the non-200 is method/auth, not path — proof the path resolved). `404` = path matches no mounted
  route = BUG.
- **Limiter control:** a nonexistent canary `/api/v1/zzz_nonexistent_abc` returned `404`, proving
  transient `429`s seen during the sweep were rate-limiting, not a global gate masking status. All
  cited 404s were re-confirmed after backoff.
- Every corrected (plain) path below was independently re-probed and returned `401`/correct method.

---

## §1 — Bug Class A: frontend → backend path mismatches (all `/api/v1/` calls that 404)

All status codes are live (`curl -s -o /dev/null -w "%{http_code}"`). "Verified" = the corrected
path was hit live and matched (401/405/422).

### 1.1 `src/lib/orchestration-api.ts` — `orchestration`
| Line | Current (404) | Corrected (verified) | Backend source |
|------|---------------|----------------------|----------------|
| 29 | `GET /api/v1/orchestration/stats` | `GET /api/orchestration/stats` | `app/api/v1/orchestration.py:18` `prefix="/orchestration"` |
| 33 | `GET /api/v1/orchestration/agents` | `GET /api/orchestration/agents` | same |
| 37 | `GET /api/v1/orchestration/agents/${id}` | `GET /api/orchestration/agents/${id}` | same |

Live: `/api/v1/orchestration/stats` → 404 ; `/api/orchestration/stats` → 401.

### 1.2 `src/lib/api/substrate.ts` — `missions` (substrate)
| Line | Current | Corrected | Note |
|------|---------|-----------|------|
| 58 | `GET /api/v1/missions/${id}/events` | `GET /api/missions/${id}/events` | verified 401 |
| 67 | `GET /api/v1/missions/${id}/replay-state` | `GET /api/missions/${id}/replay-state` | verified 401 |
| 117 | `GET /api/v1/missions/${id}/regression-compare` | ⚠️ **UNRESOLVED — see §3** | |
| 123 | `POST /api/v1/missions/${id}/freeze-baseline` | ⚠️ **UNRESOLVED — see §3** | |

Backend: `app/api/v1/substrate.py:35` `prefix="/missions"`; only defines `/{mission_id}/events`,
`/replay-state`, `/event/{sequence}`. `events`/`replay-state` are plain-`/api` mounted and verified.

### 1.3 `src/lib/workspace-api.ts` — `workspaces`
| Line | Current (404) | Corrected (verified) | Backend source |
|------|---------------|----------------------|----------------|
| 287 | `GET /api/v1/workspaces/${id}/overview` | `GET /api/workspaces/${id}/overview` | `app/api/v1/workspace.py:135` `prefix="/workspaces"` |
| 293 | `GET /api/v1/workspaces/${id}/settings` | `GET /api/workspaces/${id}/settings` | same |
| 296 | `PUT /api/v1/workspaces/${id}/settings` | `PUT /api/workspaces/${id}/settings` | same |

Live: `/api/v1/workspaces/<id>/overview` → 404 ; `/api/workspaces/<id>/overview` → 401.

### 1.4 `src/lib/cost-api.ts` — `costs`
| Line | Current (404) | Corrected (verified) | Note |
|------|---------------|----------------------|------|
| 145 | `GET /api/v1/costs/mission/${id}/steps` | `GET /api/costs/mission/${id}/steps` | L6 `/api/costs/dashboard` + L15 `/api/costs/mission/${id}` already correct — only these 2 lines broken |
| 160 | `GET /api/v1/costs/by-category` | `GET /api/costs/by-category` | |

Backend: `app/api/v1/cost_attribution.py:29` `prefix="/costs"`.

### 1.5 `src/components/mission-builder/FlowEditor.tsx:1028` — `graphs`
| Line | Current (404) | Corrected (verified) |
|------|---------------|----------------------|
| 1028 | `GET /api/v1/graphs/compare/${a}/${b}` | `GET /api/graphs/compare/${a}/${b}` |

Backend: `app/api/v1/graph.py:46` `prefix="/graphs"`. Live: `/api/v1/graphs/compare/aaa/bbb` → 404 ;
`/api/graphs/compare/aaa/bbb` → 401.

### 1.6 `src/lib/api/io.ts` — `chat` io routes
| Line | Current (404) | Corrected (verified) |
|------|---------------|----------------------|
| 63 | `POST /api/v1/chat/documents/parse` | `POST /api/chat/documents/parse` (→ 405 POST-only, route exists) |
| 71 | `POST /api/v1/chat/code/execute` | `POST /api/chat/code/execute` (→ 405, route exists) |

⚠️ **Misleading comments to fix while here:** L58 `/* POST /api/v1/chat/documents/parse ... */` and
L69 `/* ... run code in sandbox (v1 route; do NOT flip to v2) */`. The correct path is plain
`/api/chat/...` (v1 router, no `/v1` segment). The "v1 route" wording is wrong and will mislead the
next editor into re-adding `/v1`.

Backend: `app/api/v1/io.py:35` `prefix="/chat"`.

### 1.7 `src/lib/sandbox-api.ts` — `playground`
| Line | Current (404) | Corrected (verified) |
|------|---------------|----------------------|
| 25 | `POST /api/v1/playground/sandboxes` | `POST /api/playground/sandboxes` (→ 405, route exists) |
| 33 | `GET /api/v1/playground/sandboxes/${id}` | `GET /api/playground/sandboxes/${id}` |
| 41 | `POST /api/v1/playground/sandboxes/claim` | `POST /api/playground/sandboxes/claim` |
| 51 | `GET /api/v1/playground/sandboxes/${id}/files` | `GET /api/playground/sandboxes/${id}/files` |
| 61 | `GET /api/v1/playground/sandboxes/${id}/files/read` | `GET /api/playground/sandboxes/${id}/files/read` |

Backend: `app/api/v1/playground.py:20` `prefix="/playground"` (no `/v1`). Live:
`/api/v1/playground/sandboxes` → 404 ; `/api/playground/sandboxes` → 405 (POST-only).

### 1.8 `src/middleware.ts:117` — `observability`
| Line | Current (404) | Corrected (verified) |
|------|---------------|----------------------|
| 117 | `POST /api/v1/observability/auth-loop-alert` | `POST /api/observability/auth-loop-alert` (→ 422, route matched) |

Backend: `app/api/v1/observability.py:40` `@router.post("/observability/auth-loop-alert")` (router has
**no** prefix; mounted at `/api`).

---

## §2 — Routes that are CORRECT — DO NOT "fix" these

These use `/api/v1/...` and **correctly** resolve to `401` (backend bakes `/v1` into the prefix):

- `src/lib/usage-api.ts:35,39,43` — `/api/v1/usage/{summary,timeseries,breakdown}` ✅
  (`usage.py` `prefix="/v1/usage"`)
- `src/lib/billing-api.ts:43,53,64` — `/api/v1/usage/*` ✅ (same router)
- **SDK-generated services** (`src/lib/sdk/services/*`): all use plain `/api/<router>` (e.g.
  `OrchestrationService` → `/api/orchestration`). Confirmed correct against live routes — **not
  affected**. Do NOT regenerate openapi.json.

---

## §3 — Unresolvable (needs backend decision — NOT invented)

**`src/lib/api/substrate.ts:117`** (`regression-compare`) and **`:123`** (`freeze-baseline`):
even after dropping `/v1` (`/api/missions/<id>/regression-compare`, `/api/missions/<id>/freeze-baseline`)
both return **404** — these routes do **not** exist on the v1 substrate router. The real endpoints are
**v2**: `GET /api/v2/regression/<id>/compare` (verified 401) and
`POST /api/v2/regression/<id>/freeze-baseline` (verified 405 POST-only, route exists).

Two valid resolutions; pick one (flag for product/backend — agent must not guess):
- **(a)** Repoint the frontend at the v2 regression endpoints (`substrate.ts:117`→`GET /api/v2/regression/<id>/compare`,
  `:123`→`POST /api/v2/regression/<id>/freeze-baseline`), or
- **(b)** Add `regression-compare` / `freeze-baseline` routes to the v1 substrate router.

These 2 lines are **excluded** from the patch-prep plan below until resolved.

---

## §4 — Bug Class B: React hook-order (#310) crash audit

**Result: ZERO issues found.**

Method (not a regex heuristic — an actual TS AST scan):
- Wrote a recursive `ts.createSourceFile` + `forEachChild` walker over **all** `"use client"`
  components, hooks, and providers under `src/app`, `src/components`, `src/hooks`, `src/providers`.
- Detects a body-level early `return`/guard whose branch then calls a hook after it (the #310
  pattern); correctly ignores nested functions, arrow callbacks, and `return useQuery(...)` single
  liners.
- **Validator sanity check:** planted a buggy component (hook after `if (!x) return`) — the scanner
  flagged it at the exact line and did not flag the corrected version. Confirms the detector is not
  a false-negative machine.

The pattern was already remediated repo-wide: `plugins/page-client.tsx` (L451–456) and
`featured-carousel.tsx` (L22–27) carry explicit "hooks MUST be called before the early return"
comments, and every listing/table page manually inspected (blueprints, roadmap, team-management,
api-keys, CompareRuns, command-center-overview, profile, use-session-milestones) declares all hooks
at the top before any loading/empty/error guard.

**No patches needed for Class B.**

---

## §5 — Grouped fix plan (per-file, ready to apply)

> Drop the `/v1` segment in each path below. Each line is independently live-verified to resolve at
> the corrected path. Excludes the 2 held `substrate.ts` regression lines (§3) and leaves
> `usage-api.ts`/`billing-api.ts` untouched (§2).

| File | Lines | Change |
|------|-------|--------|
| `src/lib/orchestration-api.ts` | 29, 33, 37 | `/api/v1/orchestration` → `/api/orchestration` |
| `src/lib/api/substrate.ts` | 58, 67 | `/api/v1/missions` → `/api/missions` (events, replay-state only) |
| `src/lib/workspace-api.ts` | 287, 293, 296 | `/api/v1/workspaces` → `/api/workspaces` |
| `src/lib/cost-api.ts` | 145, 160 | `/api/v1/costs` → `/api/costs` |
| `src/components/mission-builder/FlowEditor.tsx` | 1028 | `/api/v1/graphs` → `/api/graphs` |
| `src/lib/api/io.ts` | 63, 71 (also fix comments L58, L69) | `/api/v1/chat` → `/api/chat` |
| `src/lib/sandbox-api.ts` | 25, 33, 41, 51, 61 | `/api/v1/playground` → `/api/playground` |
| `src/middleware.ts` | 117 | `/api/v1/observability` → `/api/observability` |

**Typecheck gate after applying:** `cd frontend && npx tsc --noEmit -p tsconfig.json` (must exit 0).

---

## §6 — Final state (byte-level)

| Repo | Branch | HEAD (pre-audit, unchanged) | Working tree |
|------|--------|------------------------------|--------------|
| backend | `main` | `b37f4f9d` (from prior handoff) | untouched |
| frontend | `master` | `da91a505` (from prior handoff) | **UNCHANGED — no files written, no commits** |

- This audit is **read-only** against both repos. No deploy, no push, no commit.
- Live evidence for every 404/401 pair is recorded in §1 (re-probed post-rate-limit).

**Open threads (require human/backend decision, not agent-guessable):**
1. §3 — `substrate.ts:117/123` regression-compare / freeze-baseline: repoint to v2 OR add v1 routes.
2. §2 — confirm `rag.py` (`/v1/rag`) is intentionally `/v1`-prefixed; if it's meant to be plain,
   that's a backend inconsistency to fix on the backend side (frontend SDK already uses `/api/rag`).
