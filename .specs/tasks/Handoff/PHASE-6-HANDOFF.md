# Phase 6 — Evals + Prompt Versioning — Handoff

**Status:** Backend complete ✅ | Frontend complete ✅ | Build verified ✅ | Tests pass ✅ | Backend committed/pushed ✅ | Frontend UNCOMMITTED ⚠️
**Date:** 2026-07-05
**Commits:** Backend `cc2c3946` (single Phase 6 commit); Frontend: uncommitted working tree
**Spec:** `.specs/tasks/draft/phase-6-evals-prompt-versioning.md`
**Ref-proto:** `.specs/REFERENCE-PROTOTYPE.md`

---

## What was done

### Backend (committed to `/opt/flowmanner`)

| File | Action | Details |
|------|--------|---------|
| `backend/app/models/prompt_version_models.py` | NEW | `PromptVersion` model scoped to `workspace_id`, with `name/content/version/is_active/created_by`, unique `(workspace_id, name, version)`. |
| `backend/alembic/versions/20260706_prompt_versions.py` | NEW | Migration: creates `prompt_versions`, `eval_suites`, `eval_runs` tables. |
| `backend/app/api/v2/prompts.py` | NEW | Prompt CRUD: list, create, get, activate, soft-delete. |
| `backend/app/api/v2/eval_runs.py` | NEW | Eval run read API: list runs, get per-case details. |
| `backend/app/api/v2/__init__.py` | Modified | Registered `prompts` + `eval_runs` routers. |
| `backend/app/services/chat_service.py` | Modified | `_build_chat_messages()` loads active `prompt_versions` entry when `thread.workspace_id` exists; falls back to inline thread metadata system prompt. |
| `backend/app/tasks/celery_app.py` | Modified | Registered `eval_run` task module. |
| `backend/app/tasks/eval_run.py` | NEW | `run_eval_suite` Celery task reusing existing `evaluation/` LLM-as-judge. Records per-case scores + aggregate scores. |
| `backend/tests/test_prompt_versions.py` | NEW | 12 tests. |
| `backend/tests/test_eval_run_task.py` | NEW | 6 tests. |

### Frontend (committed to `/home/glenn/FlowmannerV2-frontend`, still in working tree)

| File | Action | Details |
|------|--------|---------|
| `src/components/chat/ChatSettings.tsx` | Modified | Prompt version dropdown + "Save as new version" + activate flow. |
| `src/components/dashboard/ReliabilityTab.tsx` | NEW (untracked) | Eval-run dashboard: recharts score-history chart, summary cards, runs table, per-case drill-down, polling every 15s. |
| `src/components/settings/EvalSuiteManager.tsx` | NEW (untracked) | Eval run manager: list runs by model/dataset_id/status/score. |

---

## Architecture decisions made

1. **Prompt versions are per-workspace.** `prompt_versions.workspace_id` provides scoping. Lookup chain in `_build_chat_messages()` is: active `prompt_versions` entry → thread `metadata_.get("system_prompt")` → default string. This is backwards-compatible: workspaces with no prompt versions continue using inline/system settings.
2. **Soft delete, not hard delete.** Incorrectly, `<|reserved_201087|>` is never removed. `DELETE /prompts/{id}` sets `is_active=False`; `activate` uses an upsert pattern to set one active per `(workspace_id, name)`.
3. **`eval_runs` APIs are read-only.** The spec’s “run eval suite” flow is async via Celery. The frontend polls the same `/api/v2/evals/runs` surface the dashboard surfaces; no separate create-run endpoint is exposed in this commit beyond internal Celery dispatch.
4. **Celery reuses `evaluation/` judge.** `eval_run.py` imports from `app.services.evaluation` rather than introducing a second scorer, consistent with the spec and existing `services/AGENTS.md`.
5. **Frontend events use `Header: Authorization: Bearer ...`.** `getAuthToken()` result is passed verbatim. This matches existing frontend authenticated fetch patterns and avoids opinionated header shimming.

---

## What was NOT done (deferred)

| Item | Reason |
|------|--------|
| Wire `prompt_version_id` into `agent_definitions/` | Spec draft deferred it; requires ADR and config-schema audit. |
| Separate “create eval suite” UI + form | `EvalSuiteManager.tsx` only lists/runs shows runs; suite creation/test-case editor deferred. |
| Remove `swr` usage audit after dep | `pnpm build` passes, but removal was from owning package.json drift and may need per-file audit before deploy. |
| In-container migration + service verification | Backend docker service is not running on this host. Apply migration at deploy time with `alembic upgrade head`. |

---

## Verification steps for next agent

```bash
# Backend (already passing)
cd /opt/flowmanner
python3 -m pytest backend/tests/test_prompt_versions.py backend/tests/test_eval_run_task.py -q
# → 18 passed

docker compose up -d --no-deps --force-recreate backend celery-worker celery-beat
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
# → head_20260706_prompt_versions

# Frontend (commit+push first)
cd /home/glenn/FlowmannerV2-frontend
git add src/components/chat/ChatSettings.tsx src/components/dashboard/ReliabilityTab.tsx src/components/settings/EvalSuiteManager.tsx
git commit -m "feat(phase-6): prompt version dropdown, ReliabilityTab, EvalSuiteManager"
git push origin master
pnpm build
# → Client build succeeded
pnpm test -- --run
# → 929 passed
```

---

## Gotchas

- **Frontend working tree is dirty.** DeepSeek left other pre-existing modifications in the frontend repo. Do NOT bundle them into the Phase 6 commit; separate review is required.
- **Migration is unverified in live DB.** `alembic current` in-container could not be verified because the backend container is not running. Apply after redeploy.
- **`swr` was removed from `package.json` but may still be imported.** Build passes, but the next agent should grep for `from "swr"` / `import swr` before finalizing package.json changes.
- **`ReliabilityTab.tsx` and `EvalSuiteManager.tsx` are new untracked files.** They are not in git yet — ensure they are added, not overwritten by `git clean` or similar.
- **`pnpm lint` was not run.** Only build + tests were verified. Run `pnpm lint` before deployment to surface any style issues introduced by Phase 6.

---

## Key files for context

| File | Why it matters |
|------|----------------|
| `backend/app/services/chat_service.py` | Prompt-version lookup chain for message building |
| `backend/app/api/v2/prompts.py` | Prompt CRUD + activate/rollback behavior |
| `backend/app/tasks/eval_run.py` | Async eval runner reusing `evaluation/` |
| `backend/alembic/versions/20260706_prompt_versions.py` | Schema for `prompt_versions`, `eval_suites`, `eval_runs` |
| `src/components/chat/ChatSettings.tsx` | Version dropdown + save flow |
| `src/components/dashboard/ReliabilityTab.tsx` | Eval-result dashboard tab |
| `src/components/settings/EvalSuiteManager.tsx` | Eval run list/management |
