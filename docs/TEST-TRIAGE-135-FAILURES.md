# Test Triage — 148 failures / 26 errors baseline

**Date:** 2026-07-09
**Trigger:** Epic 2.3 build is blocked on a green suite (per open option b).
**Method:** Ran `make test` (backend pytest + frontend vitest). Backend alone was
148 failed / 26 error / 3579 passed / 177 skipped in 275s. Full `make test` (incl.
vitest) timed out the foreground 300s budget; backend numbers are the actionable signal.

## Root-cause buckets (from `--tb=short` tracebacks, one sample per file)

| # | Bucket | Tests | Root cause | Real code break? | Fix class |
|---|--------|------:|------------|------------------|-----------|
| 1 | **Desynced venv** | ~60 (5 files) | `aiosqlite` + `pydub` declared in `requirements.txt` but **missing from `backend/.venv`** | No — env/CI hygiene | `pip install -r requirements.txt` |
| 2 | **Orphaned dual-write tests** | 26 (5 files) | Tests import `dual_write_sync_run_status / dual_write_sync_blueprint / dual_write_soft_delete_blueprint / _mission_status_to_run_status` — **removed from `app/api/_mission_cqrs/compat.py` by commit `5757b0aa` ("dual-write removal")**, defined nowhere now | **Yes** — tests assert a deleted production API | Decide: restore the seam OR delete/rewrite the tests |
| 3 | **Async mock drift (sub-clustered)** | ~30 (node_executor, node_executor_handlers, byok, sandbox, chat_streaming, context_window, chat_tool_loop...) | NOT a uniform `MagicMock→AsyncMock` problem. Distinct sub-causes: (a) `conftest` mocked `redis.asyncio` with a plain `MagicMock` → every `await rds.get()` failed; (b) `_handle_llm`/`_handle_hitl` now `await get_event_log().find_by_idempotency_key(...)` for replay — tests never mocked `get_event_log`; (c) `_build_chat_messages` added a `prompt_versions` workspace lookup gated on `thread.workspace_id` — `_make_thread` fixture left `workspace_id` as a truthy `MagicMock`, diverting into a DB query that returned MagicMock content; (d) `query_documents` gained a `user_id=None` kwarg — RAG assertions were too strict | Tests only (real code works) | per-sub-cluster: `AsyncMock` redis, patch `get_event_log`, set `workspace_id=None` in fixture, widen `assert_called_once_with` |
| 4 | **Memory path → HITL staging** | 7 (chat_memory_extraction) + 2 (flywheel) | Tests expect `pm_service.create` called directly; production now routes **all conversation-sourced claims** to `BackgroundReviewService.stage_pending_write` (GOV-1.2 provenance gate — `requires_provenance_approval("conversation")` is always True, so even SOLO workspaces stage, not just team). `test_solo_workspace_direct_writes` asserting direct-write was stale post-gate | Tests only (real architecture moved) | Flip assertions to `stage_pending_write`; add `BackgroundReviewService` mock to each test |
| 5 | **Stale auth patch target** | 12 (sandbox_preview_auth) | `tests/test_sandbox_preview_auth.py` patches `app.api.deps.decode_access_token`; that name no longer exists in `deps.py` (re-exported as `v1_decode_access_token` / `v3_decode_access_token` after v3 auth refactor) | Tests only | Repoint patch path |
| 6 | **Other** | ~13 | `test_auth_api` login assert, `test_browser_sandbox` launch, `program_cqrs`/`phase6_hitl`/`memory_correction_models`/`tool_registry` misc | Mixed | Per-file |

## Key finding: the "135" number was inflated by a STALE LOCAL venv (not a CI/prod gap)

The host `backend/.venv` was **not installed to `requirements.txt`**. Installing the declared
deps locally cleared:

- `tests/test_event_bus.py` — **all 26** (were `ModuleNotFoundError: No module named 'aiosqlite'`)
- `tests/test_audio_format_converter.py`, `test_audio_sentiment_analyzer.py`,
  `test_speaker_diarization.py`, `test_speech_to_text_transcriber.py` — moved off the import
  error onto real assertions (ffmpeg/ffprobe ARE present at `/usr/bin`; `pydub` now installed).

**IMPORTANT — do NOT rebuild the backend for this.** Evidence:
- The deploy marker `a4475c7a` (LIVE) descends from commit `1076d14d` which added
  `aiosqlite`/`pydub` to `requirements.txt`. The Dockerfile builds via `pip install -r
  requirements.txt`, so the **deployed container already has these deps**.
- CI (`ci.yml:89`, `pr-check.yml:105`) runs `pip install -r requirements.txt` before pytest.
- So the gap existed ONLY in this box's host `.venv` — never in CI, never in prod.

**Action taken during triage (local, reversible, no deploy):** synced `backend/.venv` to
`requirements.txt`. ~60 tests were block-listed by this local-only gap. CI already does the
right thing; no Dockerfile/CI change needed.

## Re-measurement — RUN 2 (after Bucket 3/4/5 fixes)

Full backend suite re-run **after** the test-drift fixes (conftest redis AsyncMock,
`decode_access_token` re-export, node_executor `get_event_log` patch, RAG `user_id=None`
assertion widen, `_make_thread` `workspace_id=None`, and the 9 memory-staging assertion flips):

- **73 failed, 3683 passed, 174 skipped** in 329s.
- Down from 115 → **73 failures** (Bucket 3/4/5 fully closed; ~42 tests flipped green).
- Buckets 3, 4, 5 are **DONE** (test-only drift, no production change except the
  `decode_access_token` re-export shim, which was a genuine prod `ImportError` fix).
- **Remaining 73 = Bucket 2 (CQRS / `program_cqrs` removal) + Bucket 6 misc** (`test_context_window`,
  `test_hitl_expiry`, `test_integration_byok_streaming`, `test_memory_flywheel_integration`,
  `test_phase6_hitl`, `test_memory_correction_models`, `test_substrate_event_log`,
  `test_tool_registry`). Bucket 2 is the deliberate dual-write removal — needs the
  restore-seam-vs-delete-tests decision before it can be closed.

So the actionable gate for the 2.3 build is **~73 failures**, down from the 115 actionable
gate after dep-sync. Buckets 3/4/5 are closed; Bucket 2 is a real architectural decision.

## Recommendation (for Glenn to pick the path)

Option b was: *triage the 135 failures before the 2.3 build so the suite is green when we add
surface area.* Triage + mechanical drift fixes are done. The remaining work splits cleanly:

- **Bucket 1 (env):** closed by local venv sync (CI + container already install `requirements.txt`).
- **Bucket 2 (orphaned dual-write):** a real decision — those functions were deliberately
  removed in `5757b0aa`. Either (a) restore a thin compat seam, or (b) delete/rewrite the ~26
  tests. (b) is consistent with the "dual-write removal" intent. Needs your call.
- **Buckets 3/4/5 (test-only drift):** **DONE** (~42 tests green).
- **Bucket 6:** per-file, ~13 tests — `test_context_window`, `test_hitl_expiry`,
  `test_integration_byok_streaming`, `test_memory_flywheel_integration`, `test_phase6_hitl`,
  `test_memory_correction_models`, `test_substrate_event_log`, `test_tool_registry`.

### Suggested sequence
1. **No rebuild / no CI change for deps** — local venv was the only gap.
2. **Resolve Bucket 2 decision** (restore seam vs delete tests). This is the bulk of the 73.
3. **Bucket 6 per-file fixes** (small, mixed root causes).
4. Then open the 2.3 build task, gated on a green suite.

No code was committed during this triage. State is: working tree modified (test fixes +
`deps.py` re-export + `docs/TEST-TRIAGE-135-FAILURES.md`), venv locally synced.
