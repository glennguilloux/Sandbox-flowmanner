# Exit Audit — Opus 4.8 Design-QA: Item #6 Provider-Fallback Provenance

**Date:** 2026-07-08
**Agent:** Buffy (mimo/mimo-v2.5-pro) on homelab (10.99.0.3)
**Plan:** `.sisyphus/plans/OPUS-4.8-DESIGN-QA-PLAN-2026-07-08.md`
**Continued from:** `.sisyphus/handoffs/exit-audit-2026-07-08-opus-4.8-design-qa-p1-p2.md`

---

## WHAT CHANGED (one bullet per file, what + why)

**Backend (4 source files, 2 test files, 1 migration):**

- `backend/app/services/substrate/provider_fallback.py`: Added `ProviderProvenance` frozen dataclass (requested_provider, served_provider, degraded, substituted_from, fallback_reason). Added `_is_local_provider()` helper for cloud↔local detection. `resolve_provider()` now returns `ProviderProvenance` instead of `str`. Cloud→local fallback auto-detected via provider prefix comparison. `AllProvidersOpen` now carries optional `provenance` attribute. **Item #6.**

- `backend/app/services/budget_enforcer.py`: `call()` tracks `requested_model`, extracts `provenance` from `resolve_provider()`. Adds `requested_model`/`served_model`/`substituted_from`/`degraded` to every response dict (both success and error paths). `degraded` computed as `bool(substituted_from) or bool(provenance and provenance.degraded)`. Added `requested_model` and `degraded` params to `_record_llm_event()`. Event log payload and `LLMCallRecord` creation both carry provenance fields. Emits `record_model_fallback` metric on degraded calls. `ProviderProvenance` imported under `TYPE_CHECKING` (safe because `from __future__ import annotations` defers eval). **Item #6.**

- `backend/app/models/llm_call_record.py`: Added `requested_model` (String(100), nullable, indexed), `substituted_from` (Text, nullable), `degraded` (Boolean, NOT NULL, server-default false, indexed). **Item #6.**

- `backend/app/services/substrate/__init__.py`: Added `ProviderProvenance` to imports and `__all__`. Sorted `__all__` alphabetically to satisfy RUF022 lint rule. **Item #6.**

- `backend/alembic/versions/20260708_llm_call_record_provenance.py`: New migration adding the 3 provenance columns to `llm_call_records`. Chains off head `d30_60_2a3`. Server-default `false` for `degraded` so existing rows are safe. **Item #6.**

- `backend/app/tests/test_budget_enforcer.py`: Added provenance field assertions on all 4 test cases (failed cloud, local fallback, explicit allow_fallback, substitution event log). **Item #6.**

- `backend/tests/test_substrate_circuit_breaker.py`: Updated all `resolve_provider()` assertions from `== "string"` to `isinstance(result, ProviderProvenance)` with field-level checks. Updated CB wiring integration tests to return `ProviderProvenance` from mock `resolve_provider`. **Item #6.**

---

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `backend/app/services/substrate/__init__.py`: Imports reordered and `__all__` sorted — cosmetic fix for RUF022, no functional change.
- `backend/app/core/metrics.py`: Read for context (has `record_model_fallback` function). Not changed — already existed.

---

## TESTS RUN + RESULT

**Local host (homelab) — all new + affected tests:**
```
$ python -m pytest app/tests/test_budget_enforcer.py -v
8 passed in 0.74s

$ python -m pytest tests/test_substrate_circuit_breaker.py -v
24 passed in 3.72s

$ python -m pytest app/tests/test_deprecated_strategy_gate.py app/tests/test_exceptions.py app/tests/test_sse_buffer.py -v
49 passed in 5.20s
```

**In-container tests:** Timed out at 300s (full suite). The new files are not in the running container — a `deploy-backend.sh` rebuild is required to pick them up.

**Lint (ruff):** All 4 changed source files pass clean.

**Pre-existing failures (not caused by this session):**
- `app/tests/test_mission_cqrs.py::test_get_mission_success_when_owned` — confirmed pre-existing.

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
20260708_prov (head)

$ curl -sf http://127.0.0.1:8000/api/health
status: "ok" (langfuse unhealthy — pre-existing, disabled)
```

---

## COMMITS (2 on main, both pushed)

```
1aa3f388 feat(alembic): migration for provenance columns on llm_call_records
394ea987 feat(provenance): add provider-fallback provenance to every LLM call response
```

---

## NEXT SESSION HANDOFF

This session completed **Item #6** (Provider-fallback provenance) from the Opus 4.8 Design-QA plan. Every `BudgetEnforcer.call()` response now carries `requested_model`, `served_model`, `substituted_from`, and `degraded` fields. Cloud→local fallback is automatically flagged as degraded. The provenance is also recorded in the substrate event log, `LLMCallRecord`, and a `record_model_fallback` metric is emitted on degraded calls.

**5 of 10 items now complete (P1+P2 done):**
- ✅ Item #1 — SSE seq via Redis Streams (XADD/XRANGE)
- ✅ Item #2 — Typed error hierarchy (AppError → version-aware envelope)
- ✅ Item #4 — Gate deprecated strategies (DEPRECATED gate + STRATEGY_ALLOW_DEPRECATED)
- ✅ Item #6 — Provider-fallback provenance (this session)
- ✅ Item #8 — Frontend PUBLIC_PATHS segment-aware matcher

**Remaining (P3→P4):**
- Item #9 — Replay assertion headroom (P3)
- Item #3 — Workflow replay idempotency + budget ledger (P3)
- Item #5 — Plan-selection calibration (P3)
- Item #7 — v3 OIDC + webhooks (P4, needs design sign-off)
- Item #10 — Dual-auth consolidation (P4)

**Gotchas for next agent:**
1. **Backend needs rebuild.** The new source files (budget_enforcer.py, provider_fallback.py, llm_call_record.py, etc.) are in source but NOT in the running container. Run `bash /opt/flowmanner/deploy-backend.sh` to pick them up. The migration file was `docker cp`'d in for the migration, but the code changes are not live.
2. **Alembic migration already applied.** `20260708_prov` is the current head — the 3 new columns exist in PostgreSQL. No need to re-run `alembic upgrade head` after rebuild.
3. **`resolve_provider()` return type changed.** It now returns `ProviderProvenance` (dataclass) instead of `str`. The only caller is `budget_enforcer.py` — already updated. But if any future code calls it, they need to use `.served_provider` instead of the raw return value.
4. **`LLMCallRecord` has 3 new columns.** `requested_model`, `substituted_from`, `degraded`. All nullable or have server defaults — safe for existing data.
5. **`degraded` field semantics:** `True` when either (a) a model-level substitution happened (cloud→local fallback via `_local_llamacpp_fallback`) OR (b) the CB fallback resolved to a local provider when the requested provider was cloud. Cloud→cloud CB fallback is NOT degraded.

---

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

**Untracked files:** None (working tree clean).

**Deleted files:** None.

---
