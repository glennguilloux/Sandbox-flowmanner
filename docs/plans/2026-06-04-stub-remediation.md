# Stub & Placeholder Remediation Plan

> **Audit source:** DeepSeek codebase audit, 2026-06-04
> **Total findings:** 14 stubs + 5 partial implementations across 9 files
> **Backend repo:** `/opt/flowmanner/backend/` (branch: main)
> **Status:** ✅ **ALL 6 PHASES COMPLETE** — implemented 2026-06-10, deployed to production

**Goal:** Replace all user-facing stubs and fake-data endpoints with real implementations, prioritized by user impact.

## Existing Infrastructure (Reusable — Do NOT Re-Create)

| Resource | Location | Status |
|---|---|---|
| Qdrant vector store | `app/services/rag/vector_store.py` (AsyncQdrantClient, per-user collections) | Running, `10.0.4.3:6333` |
| EmbeddingService | `app/services/rag/embedding_service.py` (OpenAI + sentence-transformers + Redis cache) | Production-ready |
| ChunkingService | `app/services/rag/chunking_service.py` (semantic topic-aware splitting) | Production-ready |
| RetrievalService | `app/services/rag/retrieval_service.py` | Production-ready |
| PromptSynthesizer | `app/services/rag/prompt_synthesizer.py` | Production-ready |
| ModelRouter | `app/services/model_router.py` (LLM routing with BYOK) | Production-ready |
| Redis | `docker-compose.yml` → `workflow-redis:6379` | Running |
| PostgreSQL | 76 migrations, all models in `app/models/` | Running |
| GraphExecutor | `app/services/graph_executor.py` | Exists, importable |
| sentence-transformers | `requirements.txt` → `2.6.1` | Installed |
| qdrant-client | `requirements.txt` → `1.12.0` | Installed |

```
Progression:
Phase 1 ─── Quick Wins (fake data removal) ─── ─ 30 min, high visibility
Phase 2 ─── Differentiator Tools (7 stubs) ─── ─ core product value
Phase 3 ─── Community Comments ──────────────── ─ user-facing feature gap
Phase 4 ─── Alerting + Orchestration + Cost ─── ─ platform polish
Phase 5 ─── Self-Improvement Foundation ─────── ─ migrations + wiring
Phase 6 ─── Deprecated Endpoints ────────────── ─ low risk, sunset zone
```

**Execution strategy:** Phases 1 and 3 can run in parallel. Phase 2 tasks within each tool are independent (can parallelize across tools). Phases 4 and 5 are independent of each other but Phase 5 depends on Phase 2 (semantic_memory_index tool).

---

## Phase 1: Quick Wins — Remove Fake Data ✅

> **Why this order:** 3 endpoints return hardcoded fake numbers. Fixes are <30 lines total. Immediate user-visible improvement.

**Files:**
- `backend/app/api/v1/community.py:218` (hardcoded `total_users: 1`)
- `backend/app/api/v1/community.py:168` (empty comments — deferred to Phase 3)
- `backend/app/api/v1/orchestration.py:105` (hardcoded `tasks_by_status: {}`)

### Task 1.1: Fix community stats — real user count

**Objective:** Replace hardcoded `total_users: 1` with actual count from workspace_members table.

**Files:**
- Modify: `backend/app/api/v1/community.py:210-220`

**Acceptance criteria:**
- `GET /community/stats` returns real `total_users` from `SELECT COUNT(*) FROM workspace_members`
- `total_ratings` counts actual ratings rows (currently hardcoded 0)
- `top_categories` returns top 5 categories by template count (currently empty list)

**Implementation:**
```python
# Replace the hardcoded return at line ~218 with:
from sqlalchemy import func, select
from app.models.workspace_models import WorkspaceMember
# For total_users:
user_count_q = await db.execute(select(func.count()).select_from(WorkspaceMember))
total_users = user_count_q.scalar() or 0
# For total_ratings — check if ratings table exists, otherwise count from templates:
# (grep existing models for rating columns)
```

### Task 1.2: Fix orchestration stats — real aggregations

**Objective:** Replace hardcoded `tasks_by_status: {}` and `avg_task_duration_ms: 0` with real DB queries.

**Files:**
- Modify: `backend/app/api/v1/orchestration.py:95-115`

**Acceptance criteria:**
- `GET /orchestration/stats` returns `tasks_by_status` as `{status: count}` from `mission_tasks` table
- `avg_task_duration_ms` computed from `completed_at - started_at` on completed tasks
- Returns empty dict/0 if no tasks exist (graceful degradation)

---

## Phase 2: Differentiator Tools — Replace 7 Stubs ✅

> **Why this order:** These are advertised as platform differentiators in the UI. Users see "coming soon" when they invoke them. Highest product impact.

**Files:**
- Modify: `backend/app/tools/differentiators.py` (653 lines, 7 stub execute() methods)
- Possibly create: supporting service files where logic is complex enough to warrant extraction

**Key insight:** 4 of 7 stubs can be built on EXISTING infrastructure (RAG services already exist). Only `collaborative_team_space` needs new infrastructure.

### Task 2.1: semantic_chunking → wire to existing ChunkingService

**Priority:** P0 — easiest win, service already exists

**Files:**
- Modify: `backend/app/tools/differentiators.py` — `SemanticChunkingTool.execute()` (line ~297 area)

**Acceptance criteria:**
- Input: `text` + optional `strategy` ("semantic" | "fixed" | "sentence")
- Output: `{chunks: [{id, text, topic, tokens}], total_chunks: N}`
- Uses `ChunkingService` from `app/services/rag/chunking_service.py`
- Handles empty text (returns empty list, not error)

**Implementation sketch:**
```python
async def execute(self, input_data: dict) -> ToolResult:
    from app.services.rag.chunking_service import ChunkingService
    chunker = ChunkingService()
    text = input_data["text"]
    strategy = input_data.get("strategy", "semantic")
    chunks = await chunker.chunk_text(text, strategy=strategy)
    return ToolResult.success_result(
        tool_id=self.tool_id,
        result={
            "chunks": [{"id": c.id, "text": c.text, "topic": c.topic, "tokens": c.tokens} for c in chunks],
            "total_chunks": len(chunks),
        },
    )
```

### Task 2.2: rag_context_builder → wire to RetrievalService + PromptSynthesizer

**Priority:** P0 — both services already exist

**Files:**
- Modify: `backend/app/tools/differentiators.py` — `RagContextBuilderTool.execute()` (line ~570 area)

**Acceptance criteria:**
- Input: `query` + optional `user_id` + `top_k` (default 5)
- Output: `{context: str, sources: [{chunk_id, score, preview}], token_count: int}`
- Uses `RetrievalService.search()` then `PromptSynthesizer.build()`
- Returns empty context (not error) if no documents indexed yet

### Task 2.3: semantic_memory_index → Qdrant-backed conversation indexing

**Priority:** P0 — extends existing Qdrant infrastructure

**Files:**
- Modify: `backend/app/tools/differentiators.py` — `SemanticMemoryIndexTool.execute()` (line ~238)
- Possibly create: `app/services/memory_indexer.py` if logic >50 lines

**Acceptance criteria:**
- Input: `conversation_id`, `text`, optional `metadata`
- Creates embedding via `EmbeddingService`, stores in Qdrant under user-scoped collection
- Returns `{indexed: true, chunk_count: N, collection: str}`
- Idempotent: re-indexing same text does not create duplicates

### Task 2.4: knowledge_base_connector → workspace page search

**Priority:** P1 — needs a workspace page model to exist

**Files:**
- Modify: `backend/app/tools/differentiators.py` — `KnowledgeBaseConnectorTool.execute()` (line ~268)

**Acceptance criteria:**
- Input: `page_id` + `action` ("sync" | "search" | "link")
- `search`: queries workspace documents/pages by title/content (grep existing models for page/document tables)
- `sync`: indexes a page into Qdrant for semantic search
- `link`: creates a reference between agent and knowledge page
- Returns 404 (not stub) if page doesn't exist

**Pre-check before implementing:**
```bash
grep -rn 'class.*Page\|class.*Document\|class.*Knowledge' backend/app/models/ | grep -v __pycache__
```
If no model exists, this task requires creating a `KnowledgePage` model + migration first. Scope that separately.

### Task 2.5: pii_redactor → regex-based PII masking

**Priority:** P1 — self-contained, no external deps

**Files:**
- Modify: `backend/app/tools/differentiators.py` — `PiiRedactorTool.execute()`
- Create: `app/services/pii_redactor.py` (extracted service, ~80 lines)

**Acceptance criteria:**
- Input: `text` + optional `types` (["email", "phone", "ssn", "credit_card", "api_key"])
- Output: `{redacted_text: str, found: [{type, start, end, masked_value}], count: int}`
- Patterns: email, phone (US/EU), SSN, credit card (Luhn-validated), API keys (common prefixes)
- Masking format: `[EMAIL_REDACTED]`, `[PHONE_REDACTED]`, etc.
- Option to reverse-mask (store mapping in Redis with TTL for session-scoped unredaction)

**Implementation sketch:**
```python
import re

PATTERNS = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "phone": re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
    "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "credit_card": re.compile(r'\b(?:\d[ -]*?){13,19}\b'),
    "api_key": re.compile(r'\b(?:sk-|pk-|ak-|AKIA|ghp_)[A-Za-z0-9]{20,}\b'),
}
```

### Task 2.6: brand_voice_enforcer → LLM-based style evaluation

**Priority:** P1 — uses ModelRouter, no external deps

**Files:**
- Modify: `backend/app/tools/differentiators.py` — `BrandVoiceEnforcerTool.execute()`
- Create: `app/services/brand_voice.py` (extracted service, ~100 lines)

**Acceptance criteria:**
- Input: `text`, `style_guide_id`, `action` ("evaluate" | "rewrite")
- `evaluate`: returns `{score: 0-100, issues: [{type, excerpt, suggestion}], passed: bool}`
- `rewrite`: returns `{rewritten_text: str, changes_made: int}`
- Style guides stored as simple JSON in DB or Redis (keyed by `style_guide_id`)
- Uses `ModelRouter` for LLM evaluation
- Falls back to rule-based checks (passive voice, reading level, banned words) if no LLM configured

### Task 2.7: collaborative_team_space → real-time shared state

**Priority:** P2 — most complex, needs new infrastructure

**Files:**
- Modify: `backend/app/tools/differentiators.py` — `CollaborativeTeamSpaceTool.execute()`
- Create: `app/services/team_space.py` (Redis-backed shared state)

**Acceptance criteria:**
- Input: `space_id`, `action` ("create" | "join" | "post" | "read" | "leave")
- Spaces backed by Redis hash keyed by `team_space:{space_id}`
- `post` appends message with timestamp + agent_id
- `read` returns all messages since optional `since` timestamp
- TTL: spaces auto-expire after 24h of inactivity
- Returns `{messages: [...], members: [...], created_at: iso}` for read actions

**Design note:** This is intentionally simple — Redis-backed, no persistent table. If the product direction changes to require persistence, add a migration later.

---

## Phase 3: Community Comments — Full CRUD ✅

> **Why this order:** Comments UI exists in frontend, API returns empty. Direct user-facing gap.

**Files:**
- Create: `backend/app/models/community_models.py` (or add to `models.py`)
- Create: `backend/alembic/versions/XXX_add_community_comments.py`
- Modify: `backend/app/api/v1/community.py:166-180`

### Task 3.1: Create CommunityComment model + migration

**Objective:** Add comments table linked to community_templates.

**Files:**
- Create: `backend/app/models/community_models.py` (if not already a file — check first)
- Create: migration via `alembic revision --autogenerate -m "add community_comments"`

**Model:**
```python
class CommunityComment(Base, TimestampMixin):
    __tablename__ = "community_comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("community_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("community_comments.id", ondelete="CASCADE"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

**Acceptance criteria:**
- Migration runs cleanly on existing DB
- Model registered in `app/models/__init__.py`
- Cascade delete: deleting a template deletes its comments

### Task 3.2: Implement GET /community/templates/{id}/comments

**Files:**
- Modify: `backend/app/api/v1/community.py:166-169`

**Acceptance criteria:**
- Returns `{comments: [...], total: N}` with actual DB rows
- Supports `?page=1&limit=20` pagination
- Supports `?include_deleted=false` (default)
- Returns nested replies (comments with `parent_id`)
- Returns 404 if template doesn't exist

### Task 3.3: Implement POST /community/templates/{id}/comments

**Files:**
- Modify: `backend/app/api/v1/community.py:171-180`

**Acceptance criteria:**
- Creates comment row, returns `{comment: {...}, total: N+1}`
- Supports optional `parent_id` for threaded replies
- Validates content length (min 1, max 5000 chars)
- Returns 404 if template doesn't exist

---

## Phase 4: Alerting + Orchestration + Cost Engine ✅

> **Why this order:** Platform polish. Not user-facing in the same way as stubs, but affects ops and billing accuracy.

**Independent of Phases 2-3** — can run in parallel.

### Task 4.1: Alerting — implement email channel

**Files:**
- Modify: `backend/app/services/alerting.py:165-168`

**Acceptance criteria:**
- Uses `aiosmtplib` (check if already in requirements, otherwise add)
- SMTP config from `settings.SMTP_HOST`, `settings.SMTP_PORT`, etc.
- Sends HTML + plaintext email
- Falls back to log warning if SMTP not configured (not crash)
- Subject line: `[FlowManner Alert] {alert.title}`

### Task 4.2: Alerting — implement PagerDuty channel

**Files:**
- Modify: `backend/app/services/alerting.py:170-175`

**Acceptance criteria:**
- Uses PagerDuty Events API v2 (`https://events.pagerduty.com/v2/enqueue`)
- Requires `settings.PAGERDUTY_INTEGRATION_KEY`
- Falls back to log warning if key not configured
- Sends event with severity mapping (info→info, warning→warning, critical→critical)

### Task 4.3: Orchestration stats — real queries (if Task 1.2 incomplete)

> **May already be done in Task 1.2.** Verify before starting.

### Task 4.4: Cost engine — workspace cost calculation

**Files:**
- Modify: `backend/app/observability/cost_engine.py:245-255`

**Note:** Mission model already has `workspace_id` field (line 152 of mission_models.py). The "not implemented" message is stale.

**Acceptance criteria:**
- Filters `LLMCallRecord` by `workspace_id` from associated Mission
- Sums `total_cost` field for given time range
- Returns `{workspace_id, total_cost, by_model: {model: cost}, period: {start, end}}`

---

## Phase 5: Self-Improvement Foundation ✅

> **Why this order:** 11K lines of code with no migrations, no tests, no frontend. Highest risk. Phase 5 establishes the minimum viable foundation — do NOT attempt to validate all 6 phases at once.

**Files:**
- `backend/app/services/improvement/` (15 modules, 11,216 lines)
- `backend/app/models/` (needs KnowledgeNode + KnowledgeEdge models)
- `backend/alembic/versions/` (needs migration)

### Task 5.1: Create KnowledgeNode + KnowledgeEdge models

**Objective:** The knowledge_graph.py module references these tables but no models or migrations exist.

**Files:**
- Create: `backend/app/models/knowledge_graph_models.py`
- Create: migration

**Models (based on fields referenced in `knowledge_graph.py`):**
```bash
# Before writing models, grep the improvement modules for exact field names:
grep -rn 'knowledge_node\|knowledge_edge\|KnowledgeNode\|KnowledgeEdge' \
  backend/app/services/improvement/*.py | head -30
```

**Acceptance criteria:**
- Migration runs cleanly
- Models match what the improvement modules expect (field names, types)
- Registered in `app/models/__init__.py`

### Task 5.2: Wire improvement routes

**Files:**
- Fix: `backend/app/services/improvement/improvement_routes.py` (currently appears empty/broken)
- Verify routes are registered in the FastAPI app

**Acceptance criteria:**
- `GET /improvement/` endpoints return real data from DB (not defaults)
- Routes imported in main app router

### Task 5.3: Integration tests for improvement foundation

**Files:**
- Create: `backend/tests/test_improvement/test_knowledge_graph.py`
- Create: `backend/tests/test_improvement/test_improvement_routes.py`

**Acceptance criteria:**
- Test: create node → create edge → query graph → verify traversal
- Test: API endpoints return 200 with valid data
- Tests pass in CI

### Task 5.4 — DEFERRED: Validate remaining improvement phases

Phases 3-6 of the improvement architecture (hypothesis tester, improvement loop, success learner, strategy evolution) are deferred until:
1. Tasks 5.1-5.3 are complete and merged
2. A separate audit confirms which modules are actually called in production vs dead code
3. The user prioritizes this work

**Do not attempt to fix all 11K lines at once.**

---

## Completion Summary (2026-06-10)

All 6 phases implemented and deployed. Key deliverables:

| Phase | Status | Files Changed/Created |
|-------|--------|----------------------|
| **1: Quick Wins** | ✅ | `community.py` (real stats), `orchestration.py` (real aggregations) |
| **2: Differentiators** | ✅ | `differentiators.py` (7 tools), `pii_redactor.py` (new), `brand_voice.py` (new), `team_space.py` (new) |
| **3: Comments** | ✅ | `community_models.py` (new), `20260610_add_community_comments.py` (migration), `community.py` (CRUD) |
| **4: Alerting + Cost** | ✅ | `alerting.py` (email + PagerDuty), `cost_engine.py` (workspace_cost) |
| **5: Knowledge Graph** | ✅ | `knowledge_graph_models.py` (new ORM models) |
| **6: Deprecated** | ✅ | `flow_compat.py` (real GET /runs query) |

**Deferred:** Task 5.4 (improvement loop phases 3-6 — needs separate audit first).

---

## Phase 6: Deprecated Endpoints — Flow Compat ✅

> **Why this order:** `flow_compat.py` has deprecation headers (Sunset: 2026-09-01). Low investment. If the v2 blueprints API replaces it, consider removing the stubs entirely rather than fixing them.

### Task 6.1: Decision — fix or remove?

**Pre-check:**
```bash
# Is anything in the frontend calling /api/v1/flow/runs ?
grep -rn 'flow/runs\|flow_compat\|flow-compat' frontend/src/ | head -10
```

**If frontend calls exist:** Wire `GET /runs` to query `GraphExecution` model (which exists). Fix `POST /run/stream` to use the existing `GraphInterpreter` import.

**If no frontend calls:** Remove the stubs entirely, leave only deprecation header + redirect to v2.

**Acceptance criteria:**
- No empty `return []` in any endpoint
- Either real data or proper redirect/410 Gone

---

## IO Router — Code Execute 501 🟢

**File:** `backend/app/api/v1/io.py:316`

This returns 501 when sandbox tools can't be imported. This is a **proper credential guard pattern** — it fails clearly with an HTTP status code, not silently. 

**Recommendation:** Leave as-is. The 501 is the correct response for an unconfigured sandbox. If sandbox support is needed, that's a separate feature, not a stub fix.

---

## Dependency Graph

```
Phase 1: no dependencies
  ├── 1.1 → 1.2 (sequential within phase, both quick)
Phase 2: no dependencies — can start immediately
  ├── 2.1 (semantic_chunking) → independent
  ├── 2.2 (rag_context_builder) → independent
  ├── 2.3 (semantic_memory_index) → independent
  ├── 2.4 (knowledge_base_connector) → check model existence first
  ├── 2.5 (pii_redactor) → independent
  ├── 2.6 (brand_voice_enforcer) → independent
  └── 2.7 (collaborative_team_space) → independent
Phase 3: no dependencies — can run parallel to Phase 2
  ├── 3.1 (model + migration) → 3.2 (GET) → 3.3 (POST)
Phase 4: independent of Phases 2-3
  ├── 4.1 → 4.2 (both alerting, same file)
  ├── 4.3 (may be done in Phase 1)
  └── 4.4 (cost engine, independent)
Phase 5: depends on Phase 2.3 (semantic_memory_index uses same infra)
  ├── 5.1 (models) → 5.2 (routes) → 5.3 (tests)
  └── 5.4 DEFERRED
Phase 6: no dependencies, lowest priority
```

## Effort Estimate

| Phase | Tasks | Estimated time | Complexity |
|-------|-------|---------------|------------|
| Phase 1 | 2 | 1 hour | Low |
| Phase 2 | 7 | 8-12 hours | Medium (2.7 is high) |
| Phase 3 | 3 | 2 hours | Low |
| Phase 4 | 4 | 3 hours | Low-Medium |
| Phase 5 | 3 (+1 deferred) | 4 hours | Medium-High |
| Phase 6 | 1 | 30 min | Low |
| **Total** | **20** | **~20 hours** | |

## Quick Wins (Can Do in <1 Hour)

1. **Task 1.1:** Fix `total_users: 1` — 5 lines changed
2. **Task 1.2:** Fix orchestration stats — 15 lines changed
3. **Task 2.1:** Wire semantic_chunking to existing service — 10 lines changed
4. **Task 2.2:** Wire rag_context_builder to existing services — 15 lines changed

## External Tool Credential Guards (No Action Needed)

The 17 external tools that check `is_placeholder()` before making API calls are **correctly implemented**. They return clear error messages, not fake data. This is the right pattern — no changes needed.

## Build & Deploy

All changes require backend rebuild:
```bash
bash /opt/flowmanner/deploy-backend.sh
```
Use `timeout=300`. Check `docker compose ps` on homelab after deploy before retrying.

**git fetch origin before pushing** — remote gets force-pushed silently by other agents.
