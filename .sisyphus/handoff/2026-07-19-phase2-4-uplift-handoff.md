# Handoff — 2026-07-19 Phase 2-4 Frontend Uplift + Phase 1 Backend Fix

**Author:** Hermes (agent, orchestrator) · **Owner:** Glenn (Flowmanner principal)
**Date:** 2026-07-19
**Mode:** Remediation complete — code on isolated worktrees/branches. **NO deploy performed** (pending Glenn approval).

## Delivered branches / commits

| Phase | Repo | Branch | Commit | Evidence |
|-------|------|--------|--------|----------|
| 0 — frontend /v1 drop | frontend | `wt/remediation-fe-phase0-2026-07-19` | `44a624e5` | 23 path literals dropped + substrate→v2 repoint; grep shows zero residual plain-router `/v1` |
| 1 — backend /v1 strip + contract test | backend | `wt/remediation-be-phase1-2026-07-19` | `69666c88` | middleware rewrite + 2 test files; `79 passed, 6 skipped`; RED→GREEN proven |
| 2 — 6 section uplifts | frontend | `wt/remediation-fe-phase2-<section>-2026-07-19` | (1 commit each) | missions-graphs 364+, chat-rag 308+, plugins-orchestration 475+, workspaces-costs 370+, playground-auth 146+, integrations-hitl 408+ insertions |
| 3 — cross-cutting | frontend | `wt/remediation-fe-phase34-2026-07-19` | `84f6c219` | merges all 6 P2 branches (clean); tsc 0; api-client 29 pass; api-contract 1 pass |
| 4 — verify + handoff | this doc | — | — | below |

The Phase 3/4 branch (`wt/remediation-fe-phase34-2026-07-19`) is the **integration branch**: it contains Phase 0 + all 6 Phase-2 sections + Phase-3 hardening, merged and type-checked. It is the branch to deploy from (after Glenn's approval).

## Verification evidence

- **Frontend tsc:** `npx tsc --noEmit -p tsconfig.json` → exit 0 (on the integration branch).
- **Frontend tests:** `api-client.test.ts` 29 passed; `api-contract.test.ts` 1 passed (fails build on any `/api/v1/<plain>` regression).
- **Backend tests:** `app/tests/test_versioning_v1_strip.py` + `app/tests/test_frontend_backend_contract.py` → 79 passed, 6 skipped.
- **Backend RED→GREEN:** with the middleware rewrite disabled, `test_v1_prefixed_plain_router_resolves_to_unprefixed_mount` FAILS (404); restored, passes.
- **Live curl (pre-fix, from audit):** `/api/v1/workspaces/<id>/overview` → 404; `/api/workspaces/<id>/overview` → 401 (resolved). Mirrored across all 23 Phase-0 lines.

## Root-cause fix (the 10× lever)

The 404 class was a **broken API-versioning contract**, not 9 typos:
- ~50 routers mount at `/api/<prefix>` (no `/v1`); only `usage` and `rag` bake `/v1` into their own prefix.
- The versioning middleware negotiated v1/v2/v3 but never rewrote the path, so `/api/v1/<router>` 404'd.
- **Fix:** middleware now rewrites `/api/v1/<x>` → `/api/<x>` (in-place `scope["path"]` mutation) for plain routers, leaving `/api/v2/*`, `/api/v3/*`, `/api/v1/usage/*`, `/api/v1/rag/*` untouched. The contract tests make re-introduction architecturally impossible.

## Decisions / deviations (escalated or resolved)

1. **`rag` prefix NOT normalized** (plan §3 Layer 2.2 said `/v1/rag` → `/rag`). `app/api/AGENTS.md` (2026-07-19) explicitly states `/api/v1/rag` is **intentionally deprecated** and "MUST NOT be removed or have its behavior changed without an explicit new decision." Followed the AGENTS.md rule; middleware leaves `/api/v1/rag` alone.
2. **`substrate.ts:117/123`** repointed to v2 (`/api/v2/regression/<id>/compare`, `/api/v2/regression/<id>/freeze-baseline`) — the plan's preferred resolution; the v2 endpoints are live-verified.
3. **openapi.json NEVER regenerated** (forbidden — deletes ~40 SDK files). Typed-client item relies on the existing generated `src/lib/sdk/`.

## Open threads (NOT fake-completed — need follow-up)

- **Worker-completion bug:** kanban workers dispatched via the gateway dispatcher exit cleanly (rc=0) without calling `kanban_complete` → every worker blocked after 3 protocol-violation strikes. Phase 1, Phase 3, and Phase 4 were executed **directly by the orchestrator** instead. Recommend investigating the worker profile's kanban tool availability / completion handshake before relying on kanban workers again.
- **a11y/i18n full pass (P3.4):** only the error-UX infrastructure was added; a full keyboard/ARIA/next-intl audit across all 12 sections was NOT done.
- **`formatApiError` rollout (P3.3):** applied at one representative site (workspace-settings-panel). The remaining ~50 catch sites still use ad-hoc `e.message` — should be migrated to `formatApiError` for consistent trace_id surfacing.
- **Pre-existing unrelated contract gaps** (separate bug class, not the `/v1` alias): the backend contract test pins them open in `MISSING_BACKEND_ROUTE` (e.g. `/api/invitations/...`, `/api/files/{id}/shares`, `/api/notifications/{id}/read`). These need their own remediation pass — out of Phase-1 scope.

## Deploy (REQUIRES Glenn approval — NOT executed)

Frontend (from `wt/remediation-fe-phase34-2026-07-19`, after merge to master):
```
bash /opt/flowmanner/deploy-frontend.sh --skip-precheck
```
Backend (from `wt/remediation-be-phase1-2026-07-19`, after merge to main):
```
bash /opt/flowmanner/deploy-backend.sh
```
Verify by checking the VPS container was **recreated** (`docker compose ps frontend` shows a NEW "Created" time), not just a public 200.
