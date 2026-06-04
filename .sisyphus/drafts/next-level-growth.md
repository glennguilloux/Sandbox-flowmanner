# Draft: Flowmanner Product/Feature Growth — Next Level

## Requirements (confirmed)
- **Feature Direction**: External Integrations + Workflow Types
- **Biggest Pain**: Poor Visibility
- **Integration Approach**: Generic HTTP/Webhooks (foundation first, pre-built integrations later)
- **Workflow Types**: Human Approval Steps
- **Visibility Scope**: Comprehensive Dashboard (execution timelines, cost tracking, success/failure rates, per-workflow analytics, searchable logs)
- **Execution Strategy**: All three tracks in parallel (foundation fixes, visibility, new features)
- **Test Strategy**: YES — Include automated tests (Python backend)

## Technical Decisions
- Generic HTTP/Webhook integration as the foundation (maximum flexibility)
- Human approval workflow steps as the primary new workflow type
- Comprehensive dashboard (not minimum viable, not full observability suite)
- Parallel execution across all three tracks

## Known Issues (from CLAUDE.md)
- **Root Cause 1**: `ModelRouter._is_model_available` calls `llm_manager.get_model()` WITHOUT `user_id` or `db_session` → external API key lookup fails → returns `None` for all models
- **Root Cause 2**: `mission_executor.py` ignores `success=False` from `ModelRouter.route_request()` → defaults to empty output → creates illusion of mock working
- **Why ONE mission worked**: Explicit `model_preference` hits `_resolve_byok_model()` path which bypasses broken ModelRouter

## Scope Boundaries
- INCLUDE: Foundation fixes (ModelRouter + mission_executor), visibility dashboard, HTTP/webhook integrations, human approval workflow steps
- EXCLUDE: Pre-built integrations for specific services (Slack, GitHub, etc.) — those come later on top of generic foundation
- EXCLUDE: Full observability suite (distributed tracing, alerting) — comprehensive dashboard is the target

## Research Findings

### Backend Architecture (confirmed)
- **Framework**: FastAPI 0.115 + SQLAlchemy 2.0 (async) + Celery + RabbitMQ
- **Mission System**: Robust models (`Mission`, `MissionTask`, `MissionLog`) with status transition validation
- **Mission Executor**: `mission_executor.py` — orchestrates tasks, handles retries, logging, cost tracking, OpenTelemetry tracing
- **Human Interrupt System**: **EXISTS** — `orchestration/human_interrupt.py` has `HITLManager` with raise/poll/resolve, `HumanInterruptRecord` DB model, `approval_required_for()` logic. **NOT WIRED** into mission executor or UI yet.
- **Cost Engine**: **EXISTS** — `observability/cost_engine.py` has `CostAttributionEngine` with agent/mission/user cost aggregation. **NO UI** to display costs.
- **Dashboard**: **MINIMAL** — `routers/dashboard.py` has only 2 admin-only endpoints (analytics + firefighting metrics). No user-facing dashboard.
- **Webhook Models**: **EXISTS** — `webhook_models.py` has `WebhookEndpoint` and `WebhookLog` for INBOUND webhooks. No generic HTTP OUTBOUND integration for missions.
- **Integrations**: `integrations/` has `oauth.py` and `openwhisk/` — partial foundation.
- **API Structure**: 60+ endpoint modules under `/api/v1/`

### Frontend Architecture (confirmed)
- **Framework**: Next.js (App Router) + TypeScript + Tailwind
- **Source Location**: `/home/glenn/FlowmannerV2-frontend/` (homelab), deployed to VPS via rsync
- **Existing Pages**: missions (list + builder + replay), analytics (shell only), chat, graphs, triggers, templates, marketplace, settings, admin
- **Analytics Page**: Exists but is a shell — just imports `AnalyticsClient` component. No substantive UI.
- **Components**: Has `analytics/`, `mission-builder/`, `dashboard/`, `triggers/` directories

### Root Cause Issues (from CLAUDE.md + code review)
- **Root Cause 1**: `_is_model_available` in `llm_router.py` accepts `user_id` and `db` params, but callers may not pass them. The `_get_byok_key` method returns `(None, None)` if `effective_db` is None or `user_id == "system"`, causing model availability check to fail.
- **Root Cause 2**: `mission_executor.py` delegates to `TaskExecutor` which calls `LlmExecutor` which calls `ModelRouter`. The error propagation chain needs verification — `route_request()` returns `LLMRouteResult(success=False)` on failure, but callers may ignore the `success` flag.
- **Fix approach**: Ensure `user_id` and `db_session` are propagated through the entire call chain from `MissionExecutor` → `TaskExecutor` → `LlmExecutor` → `ModelRouter`.

## Open Questions
- ~~(pending codebase exploration)~~ ✅ RESOLVED — full architecture mapped
