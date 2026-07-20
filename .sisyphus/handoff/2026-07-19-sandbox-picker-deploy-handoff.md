# Handoff: Sandbox Model-Picker — Bug Fixes, Deploy & Verification

**Date:** 2026-07-19 (session)
**Author:** Hermes Agent (orchestrator)
**Repo:** `/opt/flowmanner` (backend) · `/mnt/apps/Softwares2/sandboxd` (sandboxd control-plane) · `/home/glenn/f` (frontend, = `/home/glenn/FlowmapperV2-frontend`)
**Branches pushed:** `fix/run-service-short-uuid-prefix` (`0336c60a`), `feat/sandbox-model-picker-phase-a` (`0f798031`)
**Sandboxd commit:** `0143e68` (branch `fix/opencode-openrouter-upstream`)

---

## 1. TL;DR

Three independent deep-dives were dispatched to kanban workers against the
2026-07-19 sandbox-model-picker handoff. All three root causes are now
**fixed and verified live in production**:

- **Bug #1 — BYOK/OpenRouter routing fails in sandboxd.** Root cause in
  `sandboxd` `opencode.go`; key sync was correct, routing was hardcoded to Zen.
  Fixed in sandboxd source, rebuilt, deployed. **Live.**
- **Bug #2 — `GET /api/v2/runs/{id}` and `/events` return 500.** Real cause
  was a **UUID/DataError** from short run-ID prefixes (e.g. `d0a940a3`), not the
  serialization error the handoff guessed. Fixed + deployed. **Live (200).**
- **Secondary — non-owner run access returned 500 instead of 404.** Discovered
  during verification; was a **stale-image deploy** (local `RunNotFoundError(Exception)`
  shadowing the `AppError`-based one). Rebuilt backend with `--no-cache`,
  redeployed. **Live (404 for non-owner, 200 for owner).**

Both backend fixes and the Phase A sandbox-picker frontend feature were then
**deployed end-to-end** and verified live. Feature branches committed and pushed
to `origin` for review.

---

## 2. Cards & Status

| Card | Repo | Status | Outcome |
|------|------|--------|---------|
| `t_e6805262` | backend | blocked | Bug #1 root cause (read-only deep-dive) |
| `t_0492f544` | sandboxd | blocked | **Deployed & live** — openrouter routes correctly |
| `t_e3c1432d` | backend | blocked | **Deployed & live** — run GET 200 |
| `t_77b4865b` | backend | blocked | **Deployed & live** — non-owner now 404 |
| `t_23cbd609` | review | blocked | F1–F4 on routing — PASS (F4 flagged cross-card "contamination", see §6) |
| `t_89724c86` | review | blocked | F1–F4 on run/events+404 — PASS (0 contamination) |

All six cards are `blocked` (awaiting Glenn's review). No card was merged,
pushed-to-`main`/master, or deployed without the "deploy" go-ahead this session.

---

## 3. Bug #1 — BYOK / OpenRouter sandboxd routing (sandboxd)

**Root cause (verified in source, `sandboxd`):**
`control-plane/cmd/runtimed/opencode.go` `writeOpencodeProxyConfig()` hardcoded
`baseURL = base + "/opencode/" + zenUpstream()`, so any model — including
`openrouter/<slug>` — was routed through Zen. The OpenRouter BYOK key *was*
correctly synced into sandboxd (`v1_agents_connect.go` confirms the key lands in
the agent-auth store); the proxy config simply never *used* it for openrouter.

**Fix:** added `case strings.HasPrefix(model, "openrouter/"): upstream = "openrouter"; id = TrimPrefix(...)`.
Commit `0143e68` on branch `fix/opencode-openrouter-upstream`.
Regression test `TestWriteOpencodeProxyConfigOpenRouter` (`proxyconfig_test.go`) — 35 tests pass.

**Deploy:** built `sandboxd-control-plane:0.3.0` from a **clean context** (the 3
pre-existing dirty files from `fix/d2-v1-template-mislabel` were `git stash`'d so
they would NOT ship, then restored). Container `sandboxd-sandboxd-1` recreated,
health: `listening :9000` + `auth proxy :9100`, reconcile complete.
Rollback image: `sandboxd-control-plane:0.3.0-backup-20260719-222007`.

---

## 4. Bug #2 — run/events 500 (backend)

**Handoff guess (WRONG):** serialization error in the run envelope.
**Actual root cause (verified via live logs + repro):** `RunService.get()` passed
`run_id` straight to `Run.id == str(run_id)` on a `UUID` column. A short prefix
like `d0a940a3` raised a Postgres `DataError`, surfacing as HTTP 500. The run
`d0a940a3` belongs to `user_id=33` (Glenn), workspace `ab0e32b7-…`.

**Fix (`app/services/run_service.py`):** `get()` tries `UUID(run_id)` first; on
`ValueError` falls back to a `LIKE` prefix match on `cast(Run.id, String)`,
normalizes to the full UUID, and threads the canonical ID through `get_events` /
`replay` / `assertions`. Short prefixes now work across all run sub-endpoints.
Regression test `app/tests/test_run_uuid_resolution.py` — 3 tests (short-prefix
resolve, full-UUID path, not-found) + integration coverage.

**Deploy:** committed on `fix/run-service-short-uuid-prefix` (initial push was
**corrupted by a pre-commit hook stash/auto-fix rollback** — see §7). Corrected
commit `0336c60a`. Deployed via `deploy-backend.sh --skip-precheck` (no
`--migrate`; no schema change).

**Live verification:** `GET /api/v2/runs/d0a940a3` → **200** (owner, uid=33);
was 500.

---

## 5. Secondary — non-owner 500 instead of 404 (backend)

**Discovered while verifying Bug #2.** A non-owner request (tested with `sub=1`)
returned **500**, not 404. Worker `t_77b4865b` falsely claimed "the fix was
already in place." Independent verification proved otherwise:

- Host `run_service.py` correctly imports `RunNotFoundError` from
  `_blueprint_cqrs.errors` (an `AppError` subclass, `http_status=404`).
- But the **running container** had a STALE `run_service.py` containing a local
  `class RunNotFoundError(Exception)` that shadowed the import → generic handler → 500.

**Root cause was a stale-image deploy**, not missing code. The earlier
`deploy-backend.sh` had reused a cached build layer with the old file.

**Fix:** rebuilt backend image with `docker build --no-cache --target runtime`,
verified the new image has the correct `run_service.py` (local `Exception` class
count = 0), then `deploy-backend.sh --skip-precheck` to recreate containers.

**Live verification:** non-owner run GET → **404**, non-owner events GET → **404**
(both were 500); owner still **200**. 9 run tests pass.

---

## 6. Phase A sandbox-picker feature — end-to-end deploy

After the bug fixes, Glenn approved **full sandbox-picker feature deploy
(backend + frontend)**.

**Backend (`deploy-backend.sh --skip-precheck`):** full dirty tree
(`commands.py`, `adapters.py`, `node_executor.py`, `schemas/mission.py`,
`byok.py`, `sandboxd_client.py`, `run_service.py`, `test_run_uuid_resolution.py`,
`test_blueprint_run_api.py`, `flowmanner.yaml`). No `--migrate` (no schema
change; `guard-alembic-drift` clean). All health checks passed.

**Frontend (`deploy-frontend.sh --skip-precheck`, VPS):** built on VPS, container
recreated. Image build date `2026-07-19 21:06 UTC`. Verified on VPS that the
deployed bundle contains the picker: `useSandboxModels.ts`,
`mission-dashboard/page-client.tsx`, `blueprints/page-client.tsx` chunks present,
`glm-5` free-tier default compiled in. (The docker-layer `CACHED` line in the log
was a non-source layer; the source `COPY` invalidated the build and recompiled
correctly — confirmed by inspecting the VPS container, not trusting the log.)

**Live end-to-end:**
| Check | Result |
|-------|--------|
| backend `/health` | 200 |
| `GET /api/v1/byok/models` (owner) | 200 (the API the picker calls) |
| `GET /api/v2/blueprints` | 200 |
| `https://flowmanner.com/en/blueprints` | 200 |
| `https://flowmapper.com/en/mission-dashboard` | 200 |
| frontend bundle has picker chunks | confirmed on VPS |

---

## 7. Gotcha — pre-commit hook stash/auto-fix rollback (ACTION REQUIRED if committing again)

The repo's pre-commit hook **stashes all changes, applies `ruff`/`ruff-format`
auto-fixes, then restores the stash**. When an **unstaged** file co-exists with a
staged file the hook auto-fixes, the restore **conflicts and the hook rolls back
the auto-fixes AND aborts the commit** — silently dropping staged content.

**Symptoms seen this session:**
- `fix/run-service-short-uuid-prefix` was pushed with the UUID fix **missing**
  (the commit had been rolled back; only the working tree had the fix).
- Subsequent commits failed with `[WARNING] Stashed changes conflicted with hook
  auto-fixes... Rolling back fixes`.

**Workaround that worked:**
1. Run `ruff check --fix` + `ruff format` on the staged files **yourself** first.
2. `git checkout -- <unstaged-file>` (or `git stash push -- <file>`) so there are
   **no unstaged changes** at commit time.
3. Commit — hook then has nothing to auto-fix and nothing to conflict.
4. Restore the unstaged file afterward.

**Do NOT** rely on the branch push as proof the fix is in the commit — verify with
`git show <branch>:<path> | grep <marker>` before pushing.

---

## 8. Open items / for Glenn's review

1. **Reviewer cards `t_23cbd609` / `t_89724c86`** are `blocked` with F1–F4 PASS.
   `t_23cbd609`'s F4 flagged `run_service.py` + `test_run_uuid_resolution.py` as
   "contamination" of the Bug #1 card — this is a **false alarm**: those are the
   Bug #2 fix (separate card, separate branch, already deployed). The reviewer's
   suggestion to "reset run_service.py" would **undo the live Bug #2 fix** — do NOT.
2. **Cosmetic ruff nits:** `byok.py` + `sandboxd_client.py` have 3 × `RUF100`
   unused `noqa` (BLE001) directives. Pre-existing, not introduced by this work.
   Optional cleanup.
3. **Branches to merge/review:** `fix/run-service-short-uuid-prefix` (`0336c60a`),
   `feat/sandbox-model-picker-phase-a` (`0f798031`). Neither merged to `main`/master.
   Working tree still has `run_service.py` dirty (the fix) on `main` — matches
   deployed, correctly tracked on its own branch.
4. **Sandboxd:** other dev's 3 dirty files (`api.go`, `v1_agents_connect.go`,
   `proxy.go`) on `fix/d2-v1-template-mislabel` were preserved (stashed/restored
   around the openrouter build) — untouched, still in their working tree.

---

## 9. Rollback references

- Backend: `workflows-backend:restored-backup-<ts>` (multiple tagged this session).
- Sandboxd: `sandboxd-control-plane:0.3.0-backup-20260719-222007`.
- Frontend (VPS): `flowmanner-frontend:backup-current`.

---

## 10. Evidence artifacts

- `backend/.sisyphus/evidence/t_e6805262-root-cause.md` — Bug #1 root cause.
- `backend/.sisyphus/evidence/final-qa/f1-f4-byok-sandboxd-review.md` — routing review.
- `backend/.sisyphus/evidence/final-qa/f1-plan-compliance.md`,
  `f2-code-quality.md` — run/events review.
- `/tmp/run_service_fixed.py` — the correct deployed `run_service.py` (extracted
  from the live container; source of truth after the hook rollback).
- Live logs: `docker compose logs backend` (showed `RunNotFoundError` → 500 before
  the `--no-cache` redeploy; 404 after).
