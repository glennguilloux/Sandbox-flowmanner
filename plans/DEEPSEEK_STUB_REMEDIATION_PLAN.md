# DEEPSEEK: Stub & Mock Remediation Plan

> **Status:** ✅ ALL 27 TASKS COMPLETE (verified 2026-06-06)
> **Audit method:** Full codebase audit + backend test suite (1,646 passed, 22 pre-existing failures)
> **Source docs:**
>   - `/opt/flowmanner/plans/TEMP/mock-stub-remediation-phases.md` (25 tasks, 6 phases)
>   - `/opt/flowmanner/plans/research/backend-stub-deep-dive.md` (62 findings, 12 CRITICAL)
>   - `/opt/flowmanner/docs/plans/2026-06-04-stub-remediation.md` (marked ✅ ALL COMPLETE, deployed 2026-06-10)
> **Backend:** `/opt/flowmanner/backend/` (homelab)
> **Frontend:** `/home/glenn/FlowmannerV2-frontend/` (homelab)
> **Deploy scripts:** `deploy-backend.sh` (homelab) or `deploy-frontend.sh` → ssh to VPS

---

## 1. THE PROBLEM

Three overlapping plan documents exist with contradictory completion status. The actual state:

- **62 confirmed stubs** in backend (12 CRITICAL, 18 HIGH, 21 MEDIUM, 11 LOW)
- **~119 instances across ~57 files** total (including frontend)
- **2026-06-04 plan claims "ALL 6 PHASES COMPLETE"** but its scope was limited (only 14 findings, 9 files) — the deeper audit happened *before* that plan (2026-06-02) so the June 4 plan fixed a subset, not the full scope
- **~20 routers silently dropped** via `_safe_import()` in v1/__init__.py
- **~30+ integration tools** check API keys but have no real HTTP calls implemented
- **Frontend blog, case studies, templates, agents** all use hardcoded SAMPLE data

### What the June 4 plan actually fixed:

| Phase | Scope | Status |
|-------|-------|--------|
| 1: Quick Wins | community stats, orchestration stats | ✅ Done |
| 2: Differentiators | 7 tools (semantic_chunking, rag_context_builder, etc.) | ✅ Done |
| 3: Comments | CommunityComment model + CRUD | ✅ Done |
| 4: Alerting + Cost | email/PagerDuty alerting, cost engine | ✅ Done |
| 5: Knowledge Graph | KnowledgeNode + KnowledgeEdge models | ✅ Done |
| 6: Flow Compat | GET /runs fix | ✅ Done |

### What remains (not covered by June 4 plan):

> **ALL DONE** — verified via codebase audit 2026-06-06

- **All 62 deep-dive findings** ✅ — already implemented before this audit
- **All frontend stubs** ✅ — agents API created, toast.error added, templates already wired
- **Mission handlers migration** ✅ — `_mission_handlers.py` deleted, CQRS active
- **30+ integration tools** ✅ — all have real `httpx` calls (120+ execute methods)
- **Except:pass → logging** ✅ — zero instances remaining in api/services code
- **Console.error → toast** ✅ — 20 instances fixed across 10 frontend files

---

## 2. EXISTING INFRASTRUCTURE (Reusable — Do NOT Re-Create)

| Resource | Location | Status |
|----------|----------|--------|
| Qdrant vector store | `app/services/rag/vector_store.py` | Running, 10.0.4.3:6333 |
| EmbeddingService | `app/services/rag/embedding_service.py` | Production-ready |
| ChunkingService | `app/services/rag/chunking_service.py` | Production-ready |
| RetrievalService | `app/services/rag/retrieval_service.py` | Production-ready |
| PromptSynthesizer | `app/services/rag/prompt_synthesizer.py` | Production-ready |
| ModelRouter | `app/services/model_router.py` | Production-ready |
| Redis | docker-compose → workflow-redis:6379 | Running |
| PostgreSQL | 76 migrations | Running |
| GraphExecutor | `app/services/graph_executor.py` | Exists, importable |

---

## 3. PRIORITY MATRIX

Tasks sorted by: User Impact × Feasibility × Risk (highest first)

```
Priority  │ Task                                    │ Effort  │ Status
──────────┼──────────────────────────────────────────┼─────────┼──────────
🔥 CRITICAL │ Wire /api/stats to DB (main_fastapi.py:336) │ 30min   │ ✅ Done
🔥 CRITICAL │ Fix community total_users: 1               │ 20min   │ ✅ Done
🔥 CRITICAL │ Wire sub-workflow execution (node_executor) │ 2h      │ ✅ Done
⚡ HIGH     │ Migrate SSE from _mission_handlers          │ 3h      │ ✅ Done
⚡ HIGH     │ Implement sub_agent_router + task_planner   │ 2h      │ ✅ Done
⚡ HIGH     │ Wire BaseDomainAgent to real LLM            │ 1h      │ ✅ Done
⚡ HIGH     │ Frontend blog → real API                    │ 2h      │ N/A (pages removed)
⚡ HIGH     │ Frontend case studies → real API            │ 1h      │ N/A (pages removed)
⚡ HIGH     │ v1 router audit: remove dead imports        │ 1h      │ ✅ Done
⚡ HIGH     │ Audit 30+ integration tools                 │ 3h      │ ✅ Done
👌 MEDIUM   │ except:pass → logging (12 instances)        │ 1h      │ ✅ Done
👌 MEDIUM   │ console.error → toast.error (16→20 inst.)  │ 1h      │ ✅ Done
👌 MEDIUM   │ Knowledge graph persistence                 │ 2h      │ ✅ Done
👌 MEDIUM   │ Web search → real API                       │ 2h      │ ✅ Done
👌 MEDIUM   │ Frontend templates → real API                │ 2h      │ ✅ Done
👌 MEDIUM   │ Frontend agents → real API                   │ 1h      │ ✅ Done
👌 MEDIUM   │ Pricing refresh (budget_enforcer)           │ 1h      │ ✅ Done
🐢 LOW      │ Webhook signature verification              │ 2h      │ ✅ Done
🐢 LOW      │ Empty browser tools (implement or remove)   │ 30min   │ ✅ Done
🐢 LOW      │ Exception classes → structured fields       │ 1h      │ ✅ Done
🐢 LOW      │ Base handler → raise NotImplementedError    │ 30min   │ ✅ Done
🐢 LOW      │ Connector credential validation             │ 2h      │ ✅ Done
🐢 LOW      │ Legacy TriggerScheduler removal             │ 1h      │ ✅ Done
🐢 LOW      │ LangChain tool wrappers audit               │ 1h      │ ✅ Done (3 dead files removed)
🐢 LOW      │ Browser mode feature flag cleanup           │ 1h      │ ✅ Done
```

---

## 4. TASK BREAKDOWN

### 🔥 CRITICAL (Do First — Production Impact)

#### C-1: Wire /api/stats to real data
- **File:** `backend/app/main_fastapi.py:336`
- **Current:** Returns `{total_runs: 0, successful_runs: 0, ...}` — hardcoded zeros
- **Fix:** Query Mission + GraphExecution tables via SQLAlchemy aggregation
- **Acceptance:** `curl /api/stats` returns real counts from DB
- **Effort:** 30 min

#### C-2: Fix community stats
- **File:** `backend/app/api/v1/community.py:218`
- **Current:** `total_users: 1` hardcoded
- **Fix:** `SELECT COUNT(*) FROM workspace_members`
- **Also fix:** `total_ratings: 0` and `top_categories: []` at same time
- **Effort:** 20 min

#### C-3: Wire sub-workflow execution
- **File:** `backend/app/services/substrate/node_executor.py:549`
- **Current:** Returns `"Sub-workflow execution not yet implemented"` error
- **Fix:** Load sub-workflow from DB, call `self.executor.execute()`
- **Effort:** 2h

---

### ⚡ HIGH (Customer-Facing Gaps)

#### H-1: Migrate SSE streaming from legacy _mission_handlers
- **Files:** `backend/app/api/_mission_handlers.py` (DEPRECATED) → `_mission_cqrs/`
- **Current:** Legacy handlers on hot path for SSE stream, async execution
- **Fix:** Migrate `handle_stream_status` to CQRS handler; update v2/missions.py
- **Risk:** High — touches real-time mission streaming. Test thoroughly.
- **Effort:** 3h

#### H-2: Implement sub_agent_router differentiator tool
- **File:** `backend/app/tools/differentiators.py`
- **Current:** Returns "coming soon"
- **Fix:** Route to sub-agent execution via existing infrastructure
- **Effort:** 1h

#### H-3: Implement task_planner differentiator tool
- **File:** `backend/app/tools/differentiators.py`
- **Current:** Returns "coming soon"
- **Fix:** Use existing mission_planner service
- **Effort:** 1h

#### H-4: Wire BaseDomainAgent to real LLM
- **File:** `backend/app/services/domain_agents/base_domain_agent.py:70`
- **Current:** Echoes input back: `f"[{domain_name}] {query}"`
- **Fix:** Call ModelRouter with domain-specific system prompt
- **Effort:** 1h

#### H-5: Blog — real API endpoint (backend)
- **Create:** `backend/app/api/v1/blog.py`, `schemas/blog.py`, `models/blog.py`
- **Endpoints:** `GET /api/v1/blog/posts`, `GET /api/v1/blog/posts/{slug}`
- **Effort:** 1.5h

#### H-6: Blog — wire frontend to API
- **Files:** `frontend/src/app/[locale]/blog/page.tsx`, `blog/[slug]/page.tsx`
- **Remove:** `SAMPLE_POSTS` constant
- **Add:** Loading/error/empty states
- **Effort:** 1h

#### H-7: RSS feed — wire to API
- **File:** `frontend/src/app/[locale]/blog/rss.xml/route.ts`
- **Remove:** `SAMPLE_POSTS`, use API fetch
- **Effort:** 30min

#### H-8: Case studies — API (reuse blog endpoint or create)
- **Option A:** Blog category filter (`?category=case-study`)
- **Option B:** Separate endpoint
- **Frontend:** Replace `SAMPLE_STUDIES` in both pages
- **Effort:** 1h

#### H-9: v1 router audit — clean up dead imports
- **File:** `backend/app/api/v1/__init__.py`
- **Current:** 60+ `_safe_import()` calls, ~20 modules don't exist
- **Fix:** Remove imports for non-existent modules; add CRITICAL logging for essential routers
- **Effort:** 1h

#### H-10: Audit 30+ integration tools
- **Directory:** `backend/app/tools/` (30+ files)
- **Current:** Check `is_placeholder(API_KEY)` but have no real HTTP call code
- **Action:** For each tool: either implement real API call OR mark as explicitly non-functional
- **Effort:** 3h (parallelizable — each tool is independent)

---

### 👌 MEDIUM (Quality of Life)

#### M-1: except:pass → add logging (12 instances)
- **Files:** dashboard.py, health.py, auth.py, browser.py, api_keys.py, mission.py, two_fa.py
- **Current:** Silent exception swallowing
- **Fix:** `logger.warning("...", exc_info=True)` before pass
- **Effort:** 1h

#### M-2: console.error → add toast.error (16 instances)
- **Files:** 10 frontend files (browser/page-client.tsx, notifications, admin/*, settings, swarm/*, etc.)
- **Current:** Silently logs to console, user sees nothing
- **Fix:** Add `toast.error(message)` alongside `console.error`
- **Effort:** 1h

#### M-3: Knowledge graph persistence
- **File:** `backend/app/services/improvement/knowledge_graph.py`
- **Current:** `_persist_node()`, `_persist_edge()`, `load_from_database()` are stubs
- **Fix:** Write DB operations using existing models
- **Effort:** 2h

#### M-4: Wire web search to real provider
- **File:** `backend/app/services/mission_executor.py` (~L864)
- **Current:** `["Web search not implemented - requires API key"]`
- **Fix:** Use existing `web_search/service.py` or Google/Tavily API
- **Effort:** 2h

#### M-5: Template gallery — real API (backend + frontend)
- **Backend:** Create `GET /api/v1/templates` endpoint
- **Frontend:** Replace hardcoded data in `frontend/src/data/templates.ts`
- **Effort:** 2h

#### M-6: Agent personalities — real API (backend + frontend)
- **Backend:** Create `GET /api/v1/agents/personalities` (data from `agent_personalities/index.json`)
- **Frontend:** Replace hardcoded data in `frontend/src/data/agents.ts`
- **Effort:** 1h

#### M-7: Pricing refresh (budget_enforcer)
- **File:** `backend/app/services/budget_enforcer.py:101`
- **Current:** `refresh()` only updates timestamp, never fetches real prices
- **Fix:** Read from config file or provider API
- **Effort:** 1h

---

### 🐢 LOW (Cleanup / Hardening)

#### L-1: Webhook signature verification
- **File:** `backend/app/services/webhook_handler/signature.py:27-32`
- **Current:** `pass` in all signature verification methods
- **Fix:** Implement Stripe, Slack, GitHub signature verification
- **Effort:** 2h

#### L-2: Empty browser tools
- **Files:** `backend/app/tools/browser_screenshot.py`, `browser_close.py`, `browser_snapshot.py`
- **Current:** Module body is `pass`
- **Fix:** Either implement or remove from registry
- **Effort:** 30min

#### L-3: Exception classes → structured fields
- **File:** `backend/app/services/mission_errors.py`
- **Current:** 7 classes with empty bodies (`pass`)
- **Fix:** Add `mission_id`, `user_id`, `details` fields
- **Effort:** 1h

#### L-4: Base handler → raise NotImplementedError
- **File:** `backend/app/services/langgraph/tool_handlers/base_handler.py:40-64`
- **Current:** Three methods with `pass`
- **Fix:** Change to `raise NotImplementedError`
- **Effort:** 30min

#### L-5: Connector credential validation
- **File:** `backend/app/services/connectors/base.py:266-272`
- **Current:** `_validate_credentials()` returns `True` always
- **Fix:** Implement validation per connector subclass
- **Effort:** 2h

#### L-6: Legacy TriggerScheduler removal
- **File:** `backend/app/services/trigger_scheduler.py`
- **Current:** DEPRECATED, 30s polling, replaced by TriggerBridge (2s)
- **Fix:** Remove; always use TriggerBridge
- **Effort:** 1h

#### L-7: LangChain tool wrappers audit
- **Directory:** `backend/app/services/langchain/tools/`
- **Current:** `workflow_catalog_tool_prod.py`, `n8n_agent_tool_prod.py`, `comfyui_agent_tool_prod.py`
- **Fix:** Remove if unused, document if active
- **Effort:** 1h

#### L-8: Browser mode feature flag cleanup
- **Files:** `browser_mode.py`, `browser_service.py` (TODO comments)
- **Current:** Two parallel browser implementations behind feature flag
- **Fix:** Pick one (harness), remove dead code
- **Effort:** 1h

---

## 5. DEPENDENCY GRAPH

```
                  ┌──────────────────────────────────────┐
                  │  C-1: /api/stats (no deps)           │
                  │  C-2: community stats (no deps)      │
                  │  C-3: sub-workflow (no deps)         │
                  └──────────┬───────────────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                  ▼
   ┌───────────────┐ ┌──────────────┐  ┌──────────────┐
   │ H-1: SSE      │ │ H-2: sub_   │  │ H-9: v1      │
   │ migration     │ │ agent_router │  │ router audit │
   │ (blocked on   │ │ (no deps)    │  │ (no deps)    │
   │ CQRS review)  │ └──────┬───────┘  └──────────────┘
   └───────────────┘        │
                            ▼
                    ┌──────────────────┐
                    │ H-3: task_planner │
                    │ (no deps)        │
                    └──────────────────┘

   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
   │ H-4: Domain   │  │ H-5: Blog API │  │ H-10: 30 tools│
   │ Agent LLM     │  │ (no deps)     │  │ (no deps)     │
   │ (no deps)     │  └───────┬───────┘  └───────────────┘
   └───────────────┘          │
                              ▼
                      ┌──────────────────┐
                      │ H-6: Blog        │ ← depends on H-5
                      │ frontend         │
                      └───────┬──────────┘
                              │
                              ▼
                      ┌──────────────────┐
                      │ H-7: RSS feed     │ ← depends on H-5
                      └──────────────────┘
                      
                      H-8: Case studies ← depends on H-5/H-6

   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
   │ M-1-M7:       │  │ L-1-L8:       │  │               │
   │ Medium items  │  │ Low items     │  │               │
   │ (independent) │  │ (independent) │  │               │
   └───────────────┘  └───────────────┘  └───────────────┘
```

**Parallel execution:** All 🔥 items can run in parallel except H-6/H-7/H-8 (depend on H-5). All 👌 items are independent of each other and of 🔥/⚡.

---

## 6. RECOMMENDED EXECUTION ORDER

### Batch 1: 🔥 CRITICAL (same-day)
1. C-1: /api/stats → real data (30 min)
2. C-2: Community stats → real data (20 min)
3. C-3: Sub-workflow execution (2h)

### Batch 2: ⚡ HIGH — Parallelizable (next session)
4. H-2: sub_agent_router tool (1h) ─┐
5. H-3: task_planner tool (1h)      ├── all independent
6. H-4: Domain agent LLM (1h)      │
7. H-9: v1 router audit (1h)       ┘
8. H-10: Audit 30+ tools (3h) — parallel by tool

### Batch 3: ⚡ HIGH — Blog pipeline (tied to batch 2)
9. H-5: Blog API endpoint (1.5h)
10. H-6: Blog frontend (1h)
11. H-7: RSS feed (30min)
12. H-8: Case studies (1h)

### Batch 4: H-1 — SSE migration (HIGH RISK, schedule carefully)
13. H-1: Migrate _mission_handlers to CQRS (3h)
    → Requires thorough testing, may need rollback plan

### Batch 5: 👌 MEDIUM (any order)
14. M-1: except:pass → logging (1h)
15. M-2: console.error → toast (1h)
16. M-3: Knowledge graph persistence (2h)
17. M-4: Web search real API (2h)
18. M-5: Templates API + frontend (2h)
19. M-6: Agents API + frontend (1h)
20. M-7: Pricing refresh (1h)

### Batch 6: 🐢 LOW (cleanup spree)
21. L-1 through L-8 (~10h total, independent)

---

## 7. WORKFLOW FOR EACH TASK

```
1. READ the current stub code
2. UNDERSTAND existing infrastructure (services, models, DB)
3. IMPLEMENT replacement using existing infra
4. TEST locally:
   - Backend: pytest test_<module>.py
   - Frontend: npm run build (type-check)
   - API: curl endpoint
5. DEPLOY:
   - Backend: bash /opt/flowmanner/deploy-backend.sh (from homelab)
   - Frontend: bash /opt/flowmanner/deploy-frontend.sh (from homelab)
6. VERIFY on production:
   - ssh to VPS, curl the endpoint from /live-curl
   - Check frontend loads real data
7. UPDATE this plan file — mark task complete
```

### Deploy details:
- **Backend:** `bash /opt/flowmanner/deploy-backend.sh` (~2 min, auto-rollback on failure)
  - Optional: `--migrate`, `--dry-run`, `--rollback`
  - NEVER use raw docker commands — script handles backup + health checks
- **Frontend:** `bash /opt/flowmanner/deploy-frontend.sh` (~4 min)
  - rsync + docker build + restart + health checks
  - ⚠️ If it times out: check `docker compose ps` on VPS before retrying

---

## 8. EFFORT SUMMARY

| Batch | Tasks | Est. Time | Complexity |
|-------|-------|-----------|------------|
| Batch 1: 🔥 Critical | 3 | ~3h | Low-Med |
| Batch 2: ⚡ High (parallel) | 4 | ~6h | Medium |
| Batch 3: ⚡ Blog pipeline | 4 | ~4h | Low-Med |
| Batch 4: ⚡ SSE migration | 1 | ~3h | High |
| Batch 5: 👌 Medium | 7 | ~9h | Low-Med |
| Batch 6: 🐢 Low | 8 | ~10h | Low |
| **Total** | **27 tasks** | **~35h** | **✅ ALL COMPLETE** |

---

## 9. COMPLETION LOG (2026-06-06)

All 27 tasks verified complete via full codebase audit:

**New work done this session:**
- Created `backend/app/api/v1/agent_personalities.py` — REST API serving 30 agent personalities across 10 domains
- Registered router in `backend/app/api/v1/__init__.py` (OPTIONAL tier)
- Fixed frontmatter parser bug (`parts[0]` → `parts[1]` unpacking)
- Created 27 new agent personality markdown files across 9 domains
- Added Next.js rewrites for `/api/agent-personalities` and `/api/templates` (local dev proxy)
- Fixed 20 `console.error` → `toast.error` instances across 10 frontend files
- Deleted 3 dead non-prod LangChain tool wrapper files
- Backend deployed to production, API verified live

**Previously completed (already in codebase):**
- C-1, C-2, C-3: Real DB queries for stats/community/sub-workflow
- H-1: SSE migration to CQRS (`_mission_handlers.py` deleted)
- H-2, H-3: sub_agent_router + task_planner in differentiators.py
- H-4: BaseDomainAgent wired to BudgetEnforcer/ModelRouter
- H-9: v1 router uses `_import_router()` with RouterTier
- H-10: All 30+ tools have real `httpx` calls
- M-1: Zero `except:pass` remaining in api/services
- M-3: Knowledge graph persistence via real SQL
- M-4: Web search wired to real provider
- M-5: Templates API queries MissionTemplate from DB
- M-7: Pricing refresh reads from `config/pricing.json`
- L-1 through L-8: All implemented or removed

---

## 10. VERIFICATION

After each task, verify on **HOST** (not container — images are baked):

```bash
# Backend endpoint verification (from VPS)
curl https://flowmanner.com/api/stats

# Frontend page check
curl -s https://flowmanner.com/en/blog | head -20

# Container status
ssh root@74.208.115.142 'docker compose ps'
```

Backend verification happens via deploy-backend.sh health checks. Frontend verification: `curl` the VPS directly.

---

## 11. DON'T

- ❌ Don't re-create infrastructure that already exists (see Section 2)
- ❌ Don't edit files on the VPS directly — all edits on homelab
- ❌ Don't use raw docker build commands — use deploy scripts
- ❌ Don't retry a deploy that timed out — check `docker compose ps` first
- ❌ Don't try to fix all 11K lines of improvement/ code at once — defer to separate audit
