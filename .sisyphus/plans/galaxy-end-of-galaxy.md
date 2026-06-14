# FlowManner End-of-the-Galaxy Strategic Plan

**Date:** 2026-06-14
**Status:** Strategic — awaiting prioritization
**Companion to:** `flowmanner-galaxy-taxonomy.html` (high-level capability map)

## The thesis

FlowManner is a platform with **substantial substrate already shipped** (156 DB tables, 121 API endpoints, 116 tools, 7 substrate strategies, 16 improvement modules, 57 capabilities, 116-tool tool registry, 7 integrations, MCP gateway, 8-module SDK, 5-locale frontend).

The "end of the Galaxy" target — *every LLM capability realisable* — is therefore **mostly wiring, not greenfield**. Three reinforcing capabilities:

| Axis | What it gives the LLM | Existing seams |
|------|----------------------|-----------------|
| **Memory** | Persistent context (what we know) | `memory_bridge/` (8 methods), `learning_service.py`, `self_correction_loop.py`, `evaluation/llm_judge.py` |
| **Reasoning** | Quality multiplier (how we think) | `mission_planner.py`, 7 substrate strategies, `improvement/` cluster (16 modules), `knowledge_graph.py`, `strategy_evolution.py` |
| **Integrations** | Distribution (where we act) | `integrations/adapters/` (slack, notion, github, linear, google_drive), `services/connectors/` (12 Slack actions, 8 Notion actions), MCP gateway, SDK at `app/sdk/` |

Build them as a **flywheel**, not three features:

```
remember → reason → act → observe → improve → remember better
```

## Sequence: 30 / 60 / 90 days

| Phase | Memory | Reasoning | Integrations |
|-------|--------|-----------|--------------|
| **D0–30** | Schema + extractor + recall + planner injection + Memory Inspector API | ToT primitive (K=3, depth=1) + PlanCandidate model + budget knobs | Slack slash command endpoint + Notion "append summary" + minimal Python SDK |
| **D30–60** | Edit/delete/forget UX + provenance + confidence + workspace/user scope | CriticAgent + ImprovementGenerator wired to Programs brief + "show alternatives" UI | Slack event verification hardening + Notion OAuth UX + CLI via Typer + TypeScript SDK start |
| **D60–90** | World-model graph view + decay tuning + "why recalled?" explanations | Optional ToT depth-2 for high-risk + critic dashboard + A/B normal vs ToT | Zapier publishing + SDK docs + Slack/Notion examples + auth flow |

The sequence: **Reasoning first** (improves plan quality, makes memory extraction cleaner) → **Memory second** (gives reasoning persistent context) → **Integrations third** (exposes the now-smart-and-contextualized LLM to the user's existing workflow).

## What's already in place (verified)

### Memory seams
- `app/services/memory_service.py` — episodic memory
- `app/services/memory_bridge/memory_service.py` — `store`, `recall`, `forget`, `update_importance`, `consolidate`
- `app/services/memory_bridge/memory_bridge.py` — `store_with_sync`, `recall_with_context`, `inject_context`, `share_memory`, `_get_shared_memories`
- `app/services/learning_service.py` — `inject_into_planner_context`, `record_execution`, `get_similar_tasks`, `get_best_model_for_task`
- `app/services/self_correction_loop.py` — `SelfCorrectionLoop.correct`, `mark_success`
- `app/services/evaluation/llm_judge.py` — `LLMJudge.score`
- `app/services/improvement/knowledge_graph.py` — `record_strategy_outcome`
- `app/services/improvement/strategy_evolution.py` — `StrategyEvolver.evolve_strategy`, `record_outcome`

### Reasoning seams
- `app/services/mission_planner.py` — `plan_mission`, `_build_plan_prompt`, `_extract_learning_brief`, `_build_learning_context_section` (DATA ONLY wrapper)
- `app/services/mission_executor.py` — `execute_mission`, `_trigger_improvement_analysis`
- `app/services/substrate/` — UnifiedExecutor (H5.1 GA), 7 strategies
- `app/services/mission_program_service.py` — `consolidate_learning` (just shipped) — **the wire-up target for personal memory**

### Integration seams
- `app/integrations/adapters/slack.py` — `_send_message`, `_search_messages`, `_list_channels`, `_create_channel`
- `app/integrations/adapters/notion.py` — `_create_page`, `_query_database`, `_append_block`
- `app/services/connectors/slack_connector.py` — 12 actions including ephemeral, update, delete, history, list users, reactions
- `app/services/connectors/notion_connector.py` — search, list databases, get/create/update page, blocks
- `app/integrations/adapters/{github,google_drive,linear}.py`
- `app/sdk/` — `runtime_sdk.py`, `cli.py`, `manifest.py`, `examples/`, `config.py`, `context.py`, `exceptions.py`, `base.py`
- `mcp_gateway/client_config.json` — filesystem + GitHub servers

## What Sisyphus's plan misses (or under-emphasizes)

These five additions are what make the plan actually shippable:

### 1. Wire personal memory into Mission Programs

The consolidation_learning() that just shipped should pull from BOTH episodic mission memory AND user personal claims. The Programs brief becomes:

```
=== LEARNING CONTEXT (DATA ONLY) ===
Mission-level learnings: [from episodic memory, runs, episodic data]
User-level preferences: [from personal claims, scoped to workspace]
=== END LEARNING CONTEXT ===
```

Differentiation: FlowManner's memory RUNS missions, not just retrieves facts.

### 2. Memory hallucination + correction UX (kill-or-be-killed)

Extractors will get things wrong. Required UX:
- Inline `[memory]` citations in every LLM response: "I remembered X (sourced from mission #482, claim #14)"
- One-click "Forget this" / "Edit this" / "Why did you think this?" right in the chat UI
- "Pause memory extraction for this conversation" toggle
- Daily digest: "Here's what I learned about you this week. Correct anything wrong."
- Memory Inspector web UI: tree view of all claims + provenance + delete buttons

Without this, long-term memory becomes creepy and gets disabled en masse.

### 3. Cold start + bootstrap migration

Three sub-problems Sisyphus skipped:

**New user (empty memory)**: explicit onboarding flow
- "Tell me about your project" → extract from responses
- "Watch my first 5 missions, then ask me to review what you learned" warmup

**Existing user (no memory yet)**: backfill pipeline
- Replay last 30 days of missions
- Extract candidate claims
- Dedupe, score confidence
- Present for user review before activating auto-extraction

**New program (empty brief)**: cold-start flow
- Use the program's `description` field as a seed
- Optional: one-shot "interview the user about this program" flow before first fire
- Fall back to the global personal memory for transfer

### 4. Cost model quantified (deepseek pricing: $0.14/M in, $0.28/M out)

| Operation | LLM calls | Avg cost |
|-----------|-----------|----------|
| Single-plan mission (current) | 1 | ~$0.005 |
| ToT depth-1, K=3 | 3 | ~$0.015 (3x) |
| ToT depth-2, K=3, M=2 expansion | 9 | ~$0.045 (9x) |
| Critic post-execution | 1 | ~$0.008 |
| Memory extraction (cheap model) | 1 | ~$0.001 |
| Personal memory recall injection | 0 (vector only) | ~$0.002 |
| **Full ToT+critic+memory overhead** | | **~$0.024/mission** (5x current) |

Verdict: Worth it for non-trivial missions. Too expensive for trivial ones. `tot_budget_usd` knob from Sisyphus is correct.

### 5. Killer 5-minute demo per capability

Each capability needs a "show, don't tell" moment:

**Memory demo**: User has 3 separate chat sessions over 3 days. In session 4, LLM says *"I remember you prefer DeepSeek for planning, terse progress updates, and avoid Mondays. Want me to follow that here?"* without being told. Jaw-drop moment.

**Reasoning demo**: User asks for a complex multi-step migration. Show 3 candidate plans side-by-side with scored trade-offs. LLM picks best. After execution, critic points out 2 things the original plan missed → they feed into the Programs brief.

**Integrations demo**: User is in Slack. Types `/flowmanner run deploy-frontend` → bot responds in Slack with mission status → mission completes → bot posts summary to Slack → bot writes structured page to user's linked Notion. End-to-end in 60 seconds, no FlowManner UI touched.

## Build order rationale

1. **Reasoning first** (D30) — improves plan quality, makes memory extraction cleaner
2. **Memory second** (D60) — gives reasoning persistent context to reason about
3. **Integrations third** (D90) — exposes the now-smart-and-contextualized LLM to the user's existing workflow

If we did integrations first, we'd be exposing a still-stupid LLM. If we did memory first without reasoning, the extracted claims would be lower-quality (no critic to filter). Reasoning first cleans the data; memory gives the cleaned data somewhere to live; integrations expose the result.

## Risks

1. **Memory hallucination** — without correction UX, the system becomes creepy. Mitigation: kill-or-be-killed correction UX is part of D30 memory ship.
2. **ToT cost runaway** — K=9 missions at $0.045 = $0.40/run. Mitigation: `tot_budget_usd` knob, opt-in flag, default off.
3. **OAuth edge cases** — Slack, Notion, Teams each have weird OAuth flows. Mitigation: ship Slack first (best OAuth UX), then Notion, then Teams last.
4. **Privacy compliance** — persistent user memory = GDPR surface. Mitigation: per-workspace encryption, retention policy, audit log, "export all my data" endpoint.
5. **Multi-tenant world model conflicts** — shared projects with multiple users. Whose memory wins? Mitigation: claims have `user_id` + `workspace_id` + `claim_scope` (personal/project/workspace); conflict resolution by recency + confidence.

## D0–30 specifics (the shippable slice)

### Personal Memory MVP (D0–30)

**Tables** (new):
- `personal_memory_claims` — (user_id, workspace_id, subject, predicate, object, claim_type, confidence, source_mission_id, source_type, created_at, last_used_at, expires_at, sensitivity, deleted_at)
- `personal_memory_entities` — denormalized for fast recall
- `personal_memory_relations` — entity-to-entity edges
- `personal_memory_sources` — provenance (which conversation/mission generated this claim)
- `personal_memory_user_actions` — view/edit/delete/forget events

**Files** (new):
- `app/services/personal_memory_service.py` — extract, recall, forget, update_importance
- `app/services/personal_memory_extractor.py` — async LLM extraction (cheap model)
- `app/api/v2/personal_memory.py` — endpoints: POST /recall, GET /inspector, PATCH /claims/{id}, DELETE /claims/{id}, POST /forget
- `app/components/memory-inspector/` — web UI tree view
- `tests/test_personal_memory_*.py` — full TDD

**Wire-up**:
- `mission_planner.py:_build_plan_prompt` — append "PERSONAL MEMORY CONTEXT" section (DATA ONLY wrapped) after the existing LEARNING CONTEXT
- `mission_program_service.py:consolidate_learning` — extend merge step to include user personal claims, with `user_notes` isolation preserved

### Budgeted Advanced Reasoning (D0–30)

**Files** (new):
- `app/services/tree_of_thought_planner.py` — K-candidate + scoring + BFS
- `app/services/critic.py` — `RedTeamAgent`, `CriticAgent`, `ImprovementGenerator`
- `app/models/critique_models.py` — persistent critique history
- `app/api/v2/critiques.py` — read API
- `tests/test_tree_of_thought_*.py` — full TDD

**Wire-up**:
- `mission_planner.py:plan_mission` — opt-in `use_tot=True` flag; if True and mission risk > threshold, delegate to TreeOfThoughtPlanner
- `mission_executor.py:execute_mission` — after completion, invoke `CriticAgent.critique(goal, outcome)`, emit misses, feed into `MissionProgramService.consolidate_learning`

### Slack + Notion + Python SDK (D0–30)

**Files** (new):
- `app/api/v2/channels/slack.py` — slash command endpoint (`/flowmanner run`, `/flowmanner ask`, `/flowmanner status`, `/flowmanner approve`, `/flowmanner pause`)
- `app/api/v2/channels/notion.py` — "append summary" action (mission completes → Notion page update)
- `sdk-python/flowmanner/__init__.py` — `FlowmannerClient` class wrapping the OpenAPI
- `sdk-python/flowmanner/missions.py` — `client.missions.run(template=..., inputs=...)`
- `sdk-python/flowmanner/programs.py` — `client.programs.fire(program_id=...)`
- `sdk-python/flowmanner/memory.py` — `client.memory.recall(query=...)`
- `tests/test_sdk_*.py` — full TDD

**Wire-up**:
- Slack slash commands: URL verification, signed request verification, idempotency, async job enqueue, response within 3s Slack timeout
- Notion summary: `mission completes → generate concise summary → append blocks to linked Notion page → store Notion page ID on mission`

## Connection to the Mission Programs work just shipped

The mission-programs plan (T1-T17, F1-F4, all APPROVE) built the durable-program primitive. The "end of the Galaxy" flywheel wires it into memory + reasoning + integrations:

- **Mission Programs brief** ← personal memory claims (new)
- **consolidate_learning()** ← critic output (new)
- **Program fire** → Slack slash command (new)
- **Program run complete** → Notion page update (new)

The Programs work was the substrate. This is the engine that runs on it.

## What this plan avoids

- ❌ Raw transcript memory (we extract claims, not conversations)
- ❌ ToT on every mission (we opt-in with budget knob)
- ❌ Zapier first (Slack + Notion + SDK first; Zapier is packaging)
- ❌ Multiple SDKs at once (Python first, then TypeScript, then CLI polish)
- ❌ Cross-tenant learning (locked scope per mission-programs plan)
- ❌ Persisted hidden chain-of-thought (persist summaries + scores, not raw thinking)
- ❌ Auto model selection (locked by T10 guardrail)

## Open questions for the user

1. **Pilot rollout**: 1 user (you) → 10 users (beta) → 100 users (GA)? Or all-at-once?
2. **Memory retention**: 1 year default? Forever? Configurable per claim?
3. **Multi-tenant world model**: shared project memory (collaborative) vs per-user only (private)?
4. **Public SDK licensing**: MIT? Apache 2.0? Source-available?
5. **Zapier**: publish ourselves, or wait for community pull?


## Appendix A — External References

### Advanced Reasoning
- Tree-of-Thoughts paper — https://arxiv.org/abs/2305.10601
- Princeton ToT repo — https://github.com/princeton-nlp/tree-of-thought-llm
- Self-RAG — https://arxiv.org/abs/2310.11511
- LLM-as-Judge — https://arxiv.org/abs/2306.05685
- OpenAI Red Teaming Guide — https://platform.openai.com/docs/guides/red-teaming
- OpenAI Agent Improvement Loop Cookbook — https://cookbook.openai.com/examples/agents_sdk
- OpenAI Cost Optimization — https://platform.openai.com/docs/guides/cost-optimization

### Personal Memory + World Model
- MemGPT / Letta archival memory — https://arxiv.org/abs/2310.08560 + https://docs.letta.com/guides/core-concepts/memory/archival-memory/
- GraphRAG (Microsoft) — https://microsoft.github.io/graphrag/
- Neo4j GraphRAG Python — https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html
- LangMem (LangChain) — https://langchain-ai.github.io/langmem/guides/manage_user_profile/
- AIGNE user-profile-memory — https://github.com/AIGNE-io/aigne-framework/blob/main/afs/user-profile-memory/README.md
- Anthropic Memory Tool — https://platform.claude.com/docs/en/managed-agents/memory
- ChatGPT Memory — https://help.openai.com/en/articles/10303002-how-does-memory-use-pastconversations
- Gemini Memory — https://support.google.com/gemini/answer/16598469
- OWASP LLM01 Prompt Injection — https://owasp.org/www-project-top-10-for-large-language-model-applications/

### Slack / Notion / Zapier
- Slack Slash Commands API — https://api.slack.com/interactivity/slash-commands
- Slack Events API — https://api.slack.com/apis/connections/events-api
- Notion API — https://developers.notion.com
- Zapier Platform CLI — https://platform.zapier.com/cli_docs/docs

### SDK + CLI
- Typer (Python CLI) — https://typer.tiangolo.com
- Python Packaging Guide — https://packaging.python.org
- FastAPI OpenAPI — https://fastapi.tiangolo.com/advanced/extending-openapi/

## Appendix B — Competitive Landscape

FlowManner's long-term memory competes with:

| Product | Strength | FlowManner differentiation |
|---------|----------|---------------------------|
| **MemGPT / Letta** | Archival memory, hierarchical context | Tied to the execution substrate; memory RUNS missions, not just retrieves facts |
| **LangMem (LangChain)** | LLM-native memory primitives | Already inside the substrate; works with the existing substrate + Programs |
| **AIGNE / sonz.ai** | User-profile memory | Same — but FlowManner has a working mission execution layer today |
| **Anthropic Memory Tool** | Client-side memory for Claude | Server-side, multi-tenant, with the substrate |
| **ChatGPT Memory** | Cross-session personalization | Per-workspace, with Program-specific learning brief |
| **Gemini Memory** | Cross-session persistence | Same — but FlowManner has HITL + cron triggers + Programs |

**The moat**: memory that drives execution. None of the competitors have the unified substrate (mission + programs + tools + reasoning + learning). The memory is just one piece of a larger system that actually RUNS things.

## Appendix C — LSP / Code Quality Followups

`backend/app/services/mission_program_service.py` has 3 ruff warnings (not errors, but worth fixing in a follow-up commit):

- **TC002** at line 29:35 — Move `sqlalchemy.ext.asyncio.AsyncSession` into a type-checking block
- **TC003** at line 25:7 — Move `uuid` standard library import into a type-checking block
- **I001** at line 456:8 — Import block is un-sorted or un-formatted

These are stylistic (type-checking imports), not behavioral. Fix with `ruff check --fix`.

## Appendix D — Multi-Agent Research Friction Note

The Sisyphus context shows 20+ cancelled background agents (context-length overflow at 262144 tokens + accidental cancellation). This is a real friction point when running parallel deep-research agents. For future Sisyphus-style research:

- Set explicit `max_tokens` per agent
- Stagger dispatch (don't launch 5 in parallel)
- Persist findings to disk between agents to avoid context bloat
- Use `delegate_task` with `load_skills=[]` (no skill) for pure explore/librarian roles to reduce per-agent context

## Appendix E — Open Questions for the User

These remain to be decided before D30 ship:

1. **Pilot rollout shape** — 1 user (you) → 10 (beta) → 100 (GA), or all-at-once behind a flag?
2. **Memory retention** — 1 year default? Forever? Per-claim configurable?
3. **Multi-tenant world model** — shared project memory (collaborative) vs per-user only (private)?
4. **Public SDK license** — MIT? Apache 2.0? Source-available (BSL)?
5. **Zapier** — publish ourselves, or wait for community pull?
6. **Competitive response** — does FlowManner want to be a MemGPT competitor (open agent memory) or a vertical (mission + memory for ops teams)? The strategic positioning affects which capabilities to ship first.
