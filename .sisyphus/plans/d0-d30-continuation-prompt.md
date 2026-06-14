# End-of-Galaxy D0–30 Continuation Prompt

> **Paste this verbatim into a fresh Hermes session to start executing the "end of the Galaxy" D0–30 work.**

---

## Context: what you are picking up

The Mission Programs plan is **complete and committed** (17/17 tasks, F1–F4 all APPROVE, 176 tests passing, backend + frontend deployed). Repo: `glennguilloux/flowmanner` on GitHub, branches `main` (backend) and `master` (frontend).

The user is now starting the **next strategic initiative**: turning FlowManner into "the platform where any LLM has every capability realisable" — the **End-of-the-Galaxy** plan.

The full strategic plan is at:
- `/opt/flowmanner/.sisyphus/plans/galaxy-end-of-galaxy.md` (415 lines, just committed as `cac1481`)
- `/opt/flowmanner/.sisyphus/evidence/flowmanner-galaxy-taxonomy.html` (11-layer inventory diagram)

**Read both files first** before doing anything. They contain the strategic framing, the verified existing seams, the 30/60/90 day build order, and a Decision Matrix (Appendix G) for handling future ambiguities.

## 5 decisions the user already locked in (DO NOT re-ask)

1. **Rollout shape**: staged 0→1→2→3 (internal dogfood → 10 trusted pilots → 100 beta → GA), behind feature flags, with explicit release gates (correction rate, no privacy incidents, no prompt-injection, ToT inside budget, quality improvement, integration reliability).
2. **Memory retention**: per-claim TTL, never forever unless explicit. Inferred prefs = 12mo w/ decay. Mission observations = 90-180d. Sensitive = opt-in only w/ short TTL. Workspace facts = while workspace exists.
3. **World model scope**: per-user + workspace, 4 explicit scopes (`personal` / `workspace` / `program` / `private`), no cross-tenant. Enforced at DB query layer.
4. **Public SDK license**: Apache 2.0 for Python/TS SDK + CLI; MIT for example apps; hosted server components get separate commercial license if needed.
5. **Zapier**: DEFERRED LAST. Do not start Zapier work until D90 or later.

## D0–30 starting slice: PERSONAL MEMORY MVP

Per the sequence in the plan (reasoning → memory → integrations), the first shippable slice is **personal memory**. Read the D0–30 specs in `galaxy-end-of-galaxy.md` for the full spec.

**Goal**: FlowManner has persistent identity. The LLM remembers user preferences, projects, tools across sessions, and that memory shapes future plans.

**What's already in place (verified)**:
- `app/services/memory_service.py` — episodic memory
- `app/services/memory_bridge/memory_service.py` — `store`, `recall`, `forget`, `update_importance`, `consolidate`
- `app/services/memory_bridge/memory_bridge.py` — `store_with_sync`, `recall_with_context`, `inject_context`, `share_memory`
- `app/services/learning_service.py` — `inject_into_planner_context`, `record_execution`
- `app/services/mission_program_service.py` — `consolidate_learning` (just shipped) — **wire personal memory INTO this**

**What to build** (D0–30):
- New tables: `personal_memory_claims`, `personal_memory_entities`, `personal_memory_relations`, `personal_memory_sources`, `personal_memory_user_actions`
- New files:
  - `app/services/personal_memory_service.py` — extract / recall / forget / update_importance
  - `app/services/personal_memory_extractor.py` — async LLM extraction (cheap model, e.g. DeepSeek-Flash or local Qwen-0.5B)
  - `app/api/v2/personal_memory.py` — POST /recall, GET /inspector, PATCH /claims/{id}, DELETE /claims/{id}, POST /forget
  - `app/components/memory-inspector/` — web UI tree view
  - `tests/test_personal_memory_*.py` — full TDD
- Wire-up:
  - `mission_planner.py:_build_plan_prompt` — append "PERSONAL MEMORY CONTEXT" section (DATA ONLY wrapped) after the existing LEARNING CONTEXT
  - `mission_program_service.py:consolidate_learning` — extend merge step to include user personal claims, with `user_notes` isolation preserved

## Critical UX requirement: MEMORY CORRECTION

Without this, long-term memory becomes creepy and gets disabled en masse. Required:
- Inline `[memory]` citations in every LLM response ("I remembered X (sourced from mission #482, claim #14)")
- One-click "Forget this" / "Edit this" / "Why did you think this?" right in the chat UI
- "Pause memory extraction for this conversation" toggle
- Daily digest: "Here's what I learned about you this week. Correct anything wrong."
- Memory Inspector web UI: tree view of all claims + provenance + delete buttons

## How to execute

Use **`delegate_task`** with `load_skills=["flowmanner"]` and `run_in_background=false`. Same pattern as the Mission Programs plan.

**Per-task workflow**:
1. RED: write failing test first
2. GREEN: minimal implementation
3. REFACTOR: extract, document
4. Run `pytest` in host venv with `DATABASE_URL="postgresql+asyncpg://flowmanner:5f206a...0efc@127.0.0.1:5432/flowmanner"`
5. Commit with `PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "..."`
6. Move to next task

**Each task should take ~30-60 minutes**. Don't try to do too much in one task — keep them TDD-sized.

**Tight context to give each subagent** (include in every `delegate_task`):
- Working directory: `/opt/flowmanner` (homelab)
- File paths to reference (existing seams above)
- TDD contract: failing test FIRST, then implementation
- Commit message format: `feat(memory): <description>`
- Use the `flowmanner` skill for project conventions

## Environment quick-check (run this first)

```bash
cd /opt/flowmanner
docker compose ps backend
curl -s http://127.0.0.1:8000/api/health | head -c 200
docker compose exec -T backend alembic current
git log --oneline | head -3
DATABASE_URL="postgresql+asyncpg://flowmanner:5f206a...0efc@127.0.0.1:5432/flowmanner" /opt/flowmanner/backend/.venv/bin/python -m pytest tests/test_mission_program_models.py -v 2>&1 | tail -5
```

If those work, the environment is healthy and you can start dispatching.

## Suggested first 6 tasks for D0–30

1. **T18: `personal_memory_claims` schema + Alembic migration + tests** (the foundation)
2. **T19: `PersonalMemoryService` CRUD + recall/forget** (the workhorse)
3. **T20: `PersonalMemoryExtractor` async LLM extraction** (the feed)
4. **T21: Wire personal memory into `MissionPlanner._build_plan_prompt`** (the use)
5. **T22: Wire personal memory into `MissionProgramService.consolidate_learning`** (the cross-pollination)
6. **T23: v2 `/personal_memory` router + Memory Inspector API** (the API surface)

Then D30–60 picks up with the memory correction UX, the critic agent, and the Slack/Notion integration. The plan in `galaxy-end-of-galaxy.md` has the full D30–60 and D60–90 specs.

## Don't

- Don't re-ask the 5 decisions — they're locked in
- Don't re-read the entire `galaxy-end-of-galaxy.md` every time — load it once at session start
- Don't skip TDD — every backend task starts with a failing test
- Don't try to do all of D0–30 in one shot — one task per `delegate_task`
- Don't use `docker cp` (per AGENTS.md) — always rebuild
- Don't push without committing first (use `PRE_COMMIT_ALLOW_NO_CONFIG=1`)
- Don't use `f"..."` in `logger.*()` calls (project rule)

## When in doubt

- Read `/opt/flowmanner/.sisyphus/plans/galaxy-end-of-galaxy.md` (it has the answers)
- Check `app/services/AGENTS.md` for service-layer conventions
- Check `app/api/AGENTS.md` for API conventions
- Check `app/services/substrate/AGENTS.md` for execution conventions

The user values: **action over analysis, TDD, terse reports, evidence capture to `.sisyphus/evidence/`**, regular commits, and clean shutdowns (defer the hard questions to the next session when context gets full).

Ship it.
