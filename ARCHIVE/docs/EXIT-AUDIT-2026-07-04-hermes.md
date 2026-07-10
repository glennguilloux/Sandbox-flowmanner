# EXIT AUDIT — 2026-07-04 (Hermes session)

## WHAT CHANGED (one bullet per file, what + why):

**Backend (`/opt/flowmanner/`):**
- `backend/requirements.txt`: Loosened `openai==1.68.2` → `>=1.68.2,<3.0` and `tiktoken==0.5.2` → `>=0.5.2,<1.0` to resolve pip ResolutionImpossible caused by DeepSeek's langchain range upgrade in commit `e6d6d19b`.
- `backend/alembic/versions/20260704_byok_per_key_salt.py`: Fixed migration to use `SECRET_KEY` (same source as `encryption.py`) instead of `AES_ENCRYPTION_KEY` (nonexistent env var). All 9 BYOK keys now successfully re-encrypted.
- `AGENTS.md`: Trimmed 9-line verbose sandbox resolution to 2 one-liners. Removed stale `q2-q3-agentic-workflow.md` ref (file gone), replaced with `frontend-wiring-roadmap.md`. Removed Jaeger from architecture diagram (dropped in commit `6aed50c`).
- `docs/archive/`: Moved 15 stale docs (June exit audits, sandbox docs, handoffs, LEGACY.md, portfolio/professionalization plans).

**New files created this session:**
- `.sisyphus/plans/flowmanner-roadmap-2026-Q3Q4.md`: 204-line strategic roadmap (6 phases, ~9 weeks with parallelism).
- `docs/EXIT-AUDIT-2026-07-04-hermes.md`: This file.

**Commits this session (3):**
- `4973a0c0` — fix: loosen openai+tiktoken pins to resolve langchain-openai dependency conflict
- `45bc06d0` — fix(byok): use SECRET_KEY not AES_ENCRYPTION_KEY in re-encryption migration
- (docs/archival + AGENTS.md trim — committed separately or in next commit)

## WHAT DID NOT CHANGE BUT WAS TOUCHED:
- None.

## TESTS RUN + RESULT:

```
cd /opt/flowmanner/backend && python -m pytest \
  app/tests/test_byok.py app/tests/test_byok_api.py \
  tests/test_backfill_idempotency_b1.py tests/test_phase104_dropped_table_b2.py \
  tests/test_compat_progress_no_mission_task_b3.py tests/test_dual_write_failure_logged_at_warning_b4.py \
  tests/test_execute_async_no_silent_fallback_b5.py tests/test_classify_route_workflow.py \
  tests/test_assertion_engine.py tests/test_baseline_extractor.py \
  tests/test_sentry_integration.py tests/test_audio_format_converter.py \
  -q --tb=no
→ 103 passed, 4 skipped, 1 warning in 11.21s
```

Frontend TypeScript:
```
cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit
→ PASS (no errors)
```

## === STATUS ===

### □ git status
```
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

### □ git fetch origin && git log --oneline origin/main..main
```
(empty — all pushed)
```

### □ docker compose exec backend alembic current
```
byok_per_key_salt_001 (head)
```

### □ Backend health
```
HTTP 200
```

### □ docker compose ps
```
NAME                STATUS
backend             Up 3 minutes (healthy)
celery-beat         Up 3 minutes (healthy)
celery-worker       Up 3 minutes (healthy)
searxng             Up 9 hours (healthy)
workflow-postgres   Up 9 hours (healthy)
workflow-rabbitmq   Up 9 hours (healthy)
workflow-redis      Up 9 hours (healthy)
workflows-static    Up 9 hours (healthy)
```

## === NEXT SESSION HANDOFF ===

This session started as a documentation cleanup ("double check + archive old docs"), then Glenn asked for a brainstorm + roadmap. I wrote a 6-phase Q3/Q4 roadmap at `.sisyphus/plans/flowmanner-roadmap-2026-Q3Q4.md`. DeepSeek then executed Phases 1-4 (pruning ~20K LOC) and Parts of 3/5/6 from the roadmap, but left two broken commits:

1. **`requirements.txt` dependency conflict** (commit `e6d6d19b` upgraded langchain ranges but left openai/tiktoken pinned). Fixed in `4973a0c0`.
2. **BYOK migration using wrong encryption key** (commit `c0851d9b` used `AES_ENCRYPTION_KEY` env var which doesn't exist; the encryption module uses `SECRET_KEY`). Fixed in `45bc06d0`. Migration re-run successfully: 9/9 keys re-encrypted.

**Backend is deployed and healthy** (rebuilt image with both fixes, migration applied). Frontend has 57 dirty files + 6 untracked — these are DeepSeek's Phase 3 (fetch migration) changes that were committed in `2c89b44` but the working tree has additional uncommitted modifications. **Frontend was NOT deployed this session** (Glenn deployed it separately and confirmed "frontend & Backend Deployed was ok!").

**Next steps:**
- The frontend dirty tree needs triage — 57 modified files is a lot. Some may be DeepSeek's uncommitted Phase 3 work. Run `git diff --stat` in the frontend repo to assess.
- Roadmap Phases 5 (product depth: templates, eval dashboard, mission timeline) and 6 (hardening: DB indexes, cache monitoring, k6 tests) remain. Phase 3 (frontend standardization) is partially done by DeepSeek.
- The `docs/ROADMAP-Q3-Q4-2026.md` is DeepSeek's copy of my roadmap — consider consolidating to one canonical location.

## === FILES THIS AGENT DID NOT TOUCH BUT EXIST ===

**Frontend (`/home/glenn/FlowmannerV2-frontend/`):**
- 57 modified files (M) — DeepSeek's Phase 3 fetch migration changes, committed in `2c89b44` but tree has additional uncommitted modifications
- 6 untracked files (??): `e2e/chat-tool-calling.spec.ts`, `e2e/dashboard-data.spec.ts`, `e2e/mission-execute.spec.ts`, `plans/phase3-exit-audit-handoff.md`, `src/hooks/__tests__/use-personal-memory.test.tsx`, `src/lib/server-fetch.ts`

**Backend (`/opt/flowmanner/`):**
- No untracked files. Working tree clean.

## === END ===
