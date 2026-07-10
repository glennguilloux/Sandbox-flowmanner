# Omega Roadmap: H1 (Q3 2026) Completion Assessment

*Assessed: 2026-06-01*

**Goal:** *"Ship what already works, fix the silent failures, earn the right to call the system production-grade."*

---

## H1.1 — Eliminate the ModelRouter Silent Failure ✅ COMPLETE

| Requirement | Status | Evidence |
|---|---|---|
| `_is_model_available(model_id, user_id, db_session)` receives user context | ✅ | Defined in `model_router.py:143`; tests confirm `user_id` and `is_admin` params |
| `mission_executor.py` checks `if not response.get("success")` | ✅ | Line 390 and multiple `{"success": False, "error": ...}` patterns throughout |
| E2E test: bogus model_id returns `success=False` with typed error | ✅ | `test_integration_model_router.py:213` — explicit H1.1 E2E test |
| GAP-2 closed (ModelRouter silently fails) | ✅ | Original bug (missing `user_id` param) fixed |

**Verdict: DONE.** Both acceptance criteria and the GAP-2 closure are satisfied.

---

## H1.2 — Unify the Dual Auth Path ✅ COMPLETE

| Requirement | Status | Evidence |
|---|---|---|
| Pick one source of truth | ✅ | Strategy (c): `fm_tokens` effectively eliminated |
| `fm_tokens` removed from backend | ✅ | 0 references in `/opt/flowmanner/backend/app/` |
| `fm_tokens` removed from frontend | ✅ | 3 remaining refs: 2 in `.bak` files, 1 in a test comment noting the removal |

**Verdict: DONE.** The `fm_tokens` dual-auth path has been eliminated in favor of NextAuth JWT + httpOnly cookies. Remaining references are archival.

---

## H1.3 — Mission Executor Observability + Abort Signals ✅ COMPLETE

| Requirement | Status | Evidence |
|---|---|---|
| State transitions emit structured logs | ✅ | `prev_state` → `next_state` transitions logged in `mission_executor.py` |
| Every LLM call records model_id, tokens, cost, latency, success | ✅ | `LLMCallRecord` model exists (`models/llm_call_record.py`), imported in `mission_executor.py:1609` |
| `Mission.abort(reason: AbortReason)` exists | ✅ | `AbortReason` enum in `mission_models.py`; API endpoint at `mission.py:340-355` |
| Reachable from API + WS | ✅ | API abort endpoint confirmed with integration tests |

**Verdict: DONE.** All four acceptance criteria satisfied.

---

## H1.4 — Browser Agent Loop Hardening ✅ COMPLETE

| Requirement | Status | Evidence |
|---|---|---|
| `iteration_idx` logged per iteration | ✅ | 10 references in `browser_agent.py` |
| `url`, `action`, `screenshot_path`, `tokens_used` logged | ✅ | 14 references each for screenshot_path and tokens_used |
| Hard time budget per iteration (default 30s) | ✅ | Implemented in file header |
| Hard total cost budget (default $0.50) | ✅ | Active code enforcing `MAX_TOTAL_COST_USD`; logs warning and terminates on exhaustion |
| Screenshot artefacts persisted to user storage | ✅ | `screenshot_path` assigned per iteration |

**Verdict: DONE.** All five acceptance criteria satisfied with functional code, not placeholders.

---

## H1.5 — Production Observability + SLOs ⚠️ MOSTLY COMPLETE

| Requirement | Status | Evidence |
|---|---|---|
| SLOs defined (p99 SSE < 300ms, mission > 95%, fallback > 99%, deploy > 99%) | ✅ | All 4 SLOs in `app/core/slo.py` with exact targets |
| Dashboards live in Langfuse | ⚠️ | Langfuse integration exists (`evaluation.py`, `health.py`); alerting service present but unclear if dashboards are actively deployed |
| Alerts wired to PagerDuty / ntfy | ⚠️ | PagerDuty supported in `alerting.py`; **ntfy not found anywhere in codebase** |
| Prometheus gauges for compliance, burn rate, error budget | ✅ | 3 gauges implemented with periodic 60s refresh background task |

**Verdict: PARTIALLY DONE.** SLO framework is solid with Prometheus integration and periodic refresh. Two gaps: (a) ntfy integration is missing (PagerDuty only), and (b) dashboard deployment status for Langfuse is unconfirmed.

---

## H1.6 — Single-Machine Dev Story ✅ COMPLETE

| Requirement | Status | Evidence |
|---|---|---|
| `docker compose up` brings up working Flowmanner | ✅ | `dev/docker-compose.dev.yml` defines full self-contained stack (Postgres, Redis, Qdrant, RabbitMQ, Celery, Backend with hot-reload) |
| Seeded Postgres | ✅ | `docker-entrypoint.dev.sh` in dev directory |
| Hot-reload backend image | ✅ | Volume mounts for backend source |
| One-command startup | ✅ | Integrated documentation with `docker compose` and `make` commands |

**Verdict: DONE.** Self-contained dev environment with no external dependencies.

---

## H1 Exit Criteria ❌ NOT MET

| Criterion | Status | Detail |
|---|---|---|
| All critical findings from `audit-2026-05-22-flowmanner-com.md` CLOSED | ❌ | **CRITICAL finding still OPEN:** `/api/auth/session` returns 401 instead of 200 for unauthenticated users, causing infinite client-side retry loop |
| GAP-2 from `DEEP-DIVE-ANALYSIS.md` CLOSED | ✅ | ModelRouter silent failure fixed |

---

## Summary

| Item | Status | Effort Est. |
|---|---|---|
| H1.1 — ModelRouter fix | ✅ Complete | 1–2 weeks |
| H1.2 — Dual auth unification | ✅ Complete | 2–3 weeks |
| H1.3 — Mission observability + abort | ✅ Complete | 2 weeks |
| H1.4 — Browser agent hardening | ✅ Complete | 1 week |
| H1.5 — Production SLOs | ⚠️ Mostly (missing ntfy) | 1–2 weeks |
| H1.6 — Dev story | ✅ Complete | 2 weeks |
| **Exit criteria** | ❌ **Not met** | — |

**Overall: 5 of 6 tasks complete, but H1 exit gate is blocked** by one remaining critical audit finding: the `/api/auth/session` 401 infinite loop bug. The engineering work on all six H1 tasks is substantially done — the blocker is a single frontend/auth bug that prevents calling H1 "shipped."
