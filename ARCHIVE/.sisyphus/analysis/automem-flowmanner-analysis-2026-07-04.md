# AutoMem Analysis for Flowmanner
**Date:** 2026-07-04
**Source:** [autoLearnMem/AutoMem](https://github.com/autoLearnMem/AutoMem)
**Paper:** [arXiv:2607.01224](https://arxiv.org/abs/2607.01224)

---

## 1. What AutoMem Is

AutoMem treats **memory management as a trainable cognitive skill** for LLM agents. Instead of treating memory as a fixed retrieval subsystem, it promotes memory operations into the agent's action space so the model itself decides:

- **what to record**
- **when to retrieve**
- **how to organize what it knows**

A strong **meta-LLM** then improves this skill through two outer loops:

| Loop | Axis | What changes |
|------|------|--------------|
| **Loop 1** | Structure | Meta-LLM rewrites scaffold code, prompts, memory-file schema, and action vocabulary based on full episode traces |
| **Loop 2** | Proficiency | Meta-LLM selects supervised `LOG`/`PLAN` turns, chooses data composition + LoRA config, trains a dedicated **memory specialist** |

At inference, the finetuned **memory specialist** handles `LOG` and the memory-consultation part of `PLAN`, while the unmodified base model commits world actions.

### Concrete results
- `Qwen2.5-32B-Instruct` + AutoMem matches frontier systems on:
  - **Crafter**: 13/22 crafting achievements (59%)
  - **MiniHack**: goal staircase progression (100%)
  - **NetHack**: dungeon level 2 + XP level 5 (2.91%)

---

## 2. Why It Matters for Flowmanner

Flowmanner already has a rich memory stack, but the current design is mostly **infrastructure-first**:

- **Qdrant** for vector search
- **Redis** for caching
- **PostgreSQL** for structured memory
- **agentmemory MCP** for cross-session persistence
- **llama.cpp** for local inference

What AutoMem contributes is a **cognitive-layer pattern on top of that infrastructure**:

1. **Memory operations become first-class agent actions** — not just "the backend does it", but the agent explicitly chooses to `LOG`, `PLAN`, `RECALL`, `SUMMARIZE`, `PROMOTE`, `CONSOLIDATE` as actions with observability and training signal.
2. **Episode-level meta-improvement** — a meta-LLM reviews complete agent traces to improve both the scaffold/prompts and the model's memory proficiency.
3. **Separation of memory skill from task skill** — a memory specialist can be trained without retraining the whole agent.

### Where it fits in Flowmanner's architecture
```
┌─────────────────────────────────────────────────────┐
│  Agent Loop                                          │
│  ┌─────────────┐    ┌─────────────┐                 │
│  │ Task Actions │    │Memory Actions│ ← NEW          │
│  │ (chat, tool) │    │  LOG/PLAN/  │                 │
│  └──────┬──────┘    │  RECALL/... │                 │
│         │           └──────┬──────┘                 │
│         ▼                  ▼                        │
│  ┌──────────────────────────────────┐               │
│  │ Base Model (llama.cpp / OpenRouter)│             │
│  └──────────────────────────────────┘               │
│                                                     │
│  ┌──────────────────────────────────┐               │
│  │ Memory Specialist (LoRA adapter) │ ← NEW         │
│  │ Handles LOG + RECALL during PLAN │               │
│  └──────────────────────────────────┘               │
├─────────────────────────────────────────────────────┤
│  Current Flowmanner Memory Stack                    │
│  Qdrant + Redis + PostgreSQL + agentmemory MCP      │
│  ← unchanged, but now PURPOSE-DRIVEN               │
└─────────────────────────────────────────────────────┘
```

---

## 3. Key Concepts to Port

### 3.1 LOG / PLAN / World Action split
AutoMem's agent runs three routines at each step:

| Routine | Purpose | Flowmanner analogue |
|---------|---------|---------------------|
| `LOG` | Record what just happened into memory | `memory_service.py` write path, `agentmemory` save |
| `PLAN` | Consult memory before committing next action | `mission_state`, tool-routing, context retrieval |
| World action | Execute the actual task | chat response, tool call, mission step |

**Proposed addition:** introduce explicit `LOG` and `PLAN` phases in agent prompts and tool contracts, with structured outputs that downstream systems can score and train on.

### 3.2 Memory as filesystem / discrete actions
AutoMem uses file-system-style memory objects. In Flowmanner, we'd map this to **discrete memory action primitives**:

```yaml
memory_actions:
  - LOG_OBSERVATION      # user said X, tool returned Y
  - LOG_TOOL_RESULT      # tool Z succeeded/failed with payload P
  - RECALL_EPISODIC      # retrieve similar past episodes
  - RECALL_SEMANTIC      # search Qdrant for concepts
  - CONSOLIDATE          # summarize and promote to long-term store
  - FORGET_LOW_QUALITY   # remove stale or redundant entries
```

Each action would:
- Have a structured schema
- Be logged to episode traces
- Be eligible for Loop 1 review / Loop 2 training

### 3.3 Loop 1 — Scaffold optimization
A meta-LLM reviews episode traces and proposes revisions to:

- **Agent system prompts** — improve LOG/PLAN instructions
- **Memory schemas** — change how memory entries are structured in Qdrant/PostgreSQL
- **Action vocabulary** — add/remove/rename memory primitives
- **Retrieval logic** — adjust top-k, embeddings, reranking

Revisions are kept only if they improve a chosen metric on a seed set.

**Flowmanner-specific implementation:**
- Trace episodes in `audit_logs` or a new `agent_episodes` table
- Meta-LLM prompt template that generates scaffold diffs
- Validation harness that runs a replay/eval suite against the revised scaffold
- Approval gate before promotion to production scaffold

### 3.4 Loop 2 — Memory-proficiency training
Train a dedicated memory specialist model that handles `LOG` and `RECALL` during `PLAN`:

1. **Data engine** selects verbatim LOG/PLAN turns from base-model traces
2. **Postprocess** strips artifacts
3. **LoRA SFT** trains the base model into a memory specialist
4. **Two-model eval** serves memory specialist + base model together

**Flowmanner-specific options:**
- **Option A: Full LoRA** — use LLaMA-Factory to train a Qwen2.5 memory specialist adapter
- **Option B: Lightweight adapter** — use llama.cpp LoRA / GGUF adapter for the memory specialist, no separate serving stack
- **Option C: Prompt-level** — no actual model training, but distilled prompt/strategy from meta-LLM review

Option C is the lowest-friction path and may capture 60-80% of the benefit without training infrastructure.

---

## 4. What Flowmanner Gains

| Current limitation | AutoMem-inspired improvement |
|--------------------|------------------------------|
| Memory reads are passive/static retrieval | Agent actively chooses when and what to recall |
| No training signal from memory operations | LOG/PLAN turns become labeled training data |
| Prompt engineering only | Scaffold changes can be validated, rolled back, improved |
| Single model does everything | Memory skill decoupled from task skill |
| No cross-episode memory improvement | Meta-LLM reviews full traces and proposes improvements |
| Hard to measure "is memory helping?" | Episode traces with memory action logging enable clean ablation |

---

## 5. Concrete Implementation Plan

### Phase 1: Memory Action Primitives (1-2 weeks)
**Goal:** Make memory operations explicit in agent traces.

1. Define schema for `memory_action` events in episode traces
2. Modify agent prompts to emit structured `LOG` / `PLAN` phases with memory actions
3. Wire schema into existing `audit_logs` or create `agent_trace_events` table
4. Add frontend trace viewer to inspect memory actions per episode
5. Validate with existing eval dashboard

### Phase 2: Meta-LLM Review Loop (2-4 weeks)
**Goal:** Externalize memory improvement into a review + propose loop.

1. Build trace export/import pipeline for meta-LLM review
2. Prompt template for scaffold-level memory improvement proposals
3. Diff/apply mechanism for scaffold changes
4. Validation harness: compare old vs new scaffold on seed episodes
5. Approval queue + rollback capability

### Phase 3: Memory Specialist Training (4-8 weeks)
**Goal:** Separate memory skill from base model.

1. Curate LOG/PLAN turn dataset from Phase 1 traces
2. Evaluate Option C (prompt distillation) first — low cost, fast iteration
3. If gains warrant, evaluate Option A (LLaMA-Factory LoRA) or Option B (llama.cpp adapter)
4. Two-model serving: memory specialist for LOG/RECALL, base model for world actions
5. A/B test in eval dashboard

### Phase 4: Production Hardening (ongoing)
1. Memory action cost accounting
2. Quality metrics: retrieval precision, consolidation accuracy
3. User-facing transparency: show agent "remembered X" / "consulted Y"
4. Privacy controls: filter sensitive data from training traces

---

## 6. Risks & Prerequisites

| Risk | Mitigation |
|------|------------|
| **Training cost** — LoRA requires GPU + data | Start with Option C (prompt distillation) |
| **Trace volume** — episode traces are large | Sample high-value episodes, not everything |
| **Scaffold instability** — auto-rewrites can regress | Approval gate + shadow eval before promotion |
| **Meta-LLM dependency** — Claude Code CLI is required in AutoMem | Use local meta-LLM via llama.cpp instead |
| **Two-model serving complexity** | Delay Phase 3; validate value first |
| **Privacy** — traces contain user data | Filter PII, obtain consent, never train on live user data |

### Critical prerequisites
1. **Episode tracing must be in place** — need complete traces before meta-LLM can review
2. **Base model serving is already done** — llama.cpp + Qwen3 is in place
3. **Existing eval infrastructure** — k6 load tests + eval dashboard provide validation substrate
4. **Meta-LLM access** — need a strong model for Loop 1/2 reviews; can use DeepSeek/GLM or local Qwen via llama.cpp

---

## 7. Fit with Flowmanner Roadmap

This dovetails cleanly with the active `frontend-wiring-roadmap.md` and recent Phase R5/R6 work:

- **Eval dashboard** (`R5`) → new memory proficiency metrics here
- **Cache metrics** (`R6d`) → extend to memory action hit/miss tracking
- **Tool Routing Inspector** → memory specialist could improve routing decisions
- **Plugin Manager** → memory improvement plugins could be auto-evolved

**Recommended sequencing:**
1. Complete current Phase 6 cleanup/verification
2. Build eval dashboard metric extensions
3. Start Phase 1 here (memory action primitives + trace schema)
4. Use eval dashboard to measure improvement

---

## 8. Open Questions

1. **What's the right action set?** AutoMem uses filesystem operations. Flowmanner needs semantic memory primitives (`CONSOLIDATE`, `PROMOTE`, `FORGET` are guesses).
2. **What metric drives improvement?** AutoMem uses game progression. Flowmanner needs a customer-facing metric — mission success rate? response quality? user satisfaction?
3. **Meta-LLM choice?** AutoMem uses Claude Code CLI. Flowmanner should use what's already available — llama.cpp Qwen or DeepSeek — to keep infrastructure simple.
4. **Separate memory store vs current Qdrant?** AutoMem uses files. Flowmanner already has Qdrant + PostgreSQL. The action set can target existing stores; no need to introduce filesystem memory.
5. **Do we need two models at inference?** The memory specialist may be overkill if Option C works. Validate before adding serving complexity.

---

## 9. Verdict

**Yes, this is worth pursuing, but not as a direct port.** AutoMem's core insight — that memory management is a trainable skill, not just plumbing — is directly applicable to Flowmanner. However, the game-agent context is very different from Flowmanner's conversational/mission-execution context.

**Recommended approach:**
- Adopt the **LOG/PLAN pattern** first (Phase 1)
- Use **meta-LLM review** for scaffold improvement, not necessarily model training (Phase 2)
- Delay LoRA training until you have 10K+ labeled LOG/PLAN turns (Phase 3, later)
- Keep existing memory infrastructure; add **purpose-driven memory actions** on top of it

This gives most of the benefit with minimal new infrastructure and fits Flowmanner's existing architecture.
