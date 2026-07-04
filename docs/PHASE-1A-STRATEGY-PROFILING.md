# Phase 1A — Strategy Profiling & AI Quality Gate

**Date:** 2026-07-04
**Status:** COMPLETE (code analysis)
**Pending:** Runtime profiling with live 27B model missions

---

## Executive Summary

The 7 execution strategies fall into three tiers based on their reliance on LLM intelligence:

| Tier | Strategies | LLM calls in strategy | 27B suitability |
|------|-----------|----------------------|-----------------|
| **Tier 1: Deterministic** | Solo, DAG, Graph | None | ✅ Production-ready |
| **Tier 2: LLM-delegating** | Pipeline, Meta | None (delegates to nodes) | ⚠️ Depends on node quality |
| **Tier 3: LLM-driving** | Swarm | 2 direct calls | ❌ High risk with 27B |
| **Incomplete** | LangGraph | Falls back to shared executor | ❌ Not wired |

**Key insight:** Only SwarmStrategy makes direct LLM calls (decomposition + synthesis). All others are pure orchestration — they manage graph algorithms, loops, and retries, delegating actual LLM work to `execute_node`. The 27B model's limitations matter most for Swarm's structured JSON decomposition.

---

## Strategy-by-Strategy Analysis

### 1. SoloStrategy — `solo.py` (~50 LOC)

**What it does:** Executes a single node. No dependency resolution, no edges, no LLM calls in the strategy.

**How it works:**
```
workflow.nodes[0] → executor.execute_node() → StrategyResult
```

**LLM dependency:** None in the strategy. The node itself may call the LLM via `NodeExecutor`.

**27B suitability:** ✅ **Production-ready.** This is the simplest strategy. It's a thin wrapper around `execute_node`. The 27B model's quality only matters for the node's content, not the orchestration.

**Risk:** Minimal. Single point of failure is the node executor, not the strategy.

---

### 2. DAGStrategy — `dag.py` (~80 LOC)

**What it does:** Topological sort via Kahn's algorithm, then executes nodes in parallel layers.

**How it works:**
```
workflow → topological_sort() → layers[] → for each layer:
    parallel: executor.execute_node() for each node in layer
→ StrategyResult
```

**LLM dependency:** None. Pure graph algorithms (cycle detection, topological sort, parallel gather).

**27B suitability:** ✅ **Production-ready.** The strategy is entirely deterministic. Layer-parallel execution is efficient. HITL pause propagation is handled correctly.

**Risk:** Low. Cycle detection is DFS-based (standard). The only failure mode is a node failure in a layer, which is handled gracefully.

---

### 3. GraphStrategy — `graph.py` (~120 LOC)

**What it does:** Like DAG, but with conditional edges and context interpolation.

**How it works:**
```
workflow → subgraph_filter(start_node_id?) → topological_sort() → layers[] → for each layer:
    for each node: evaluate incoming edge conditions
    parallel: executor.execute_node() for nodes with all conditions met
→ StrategyResult
```

**LLM dependency:** None. Condition evaluation is string interpolation (`{{node_id.output.field}}`) — pure Python.

**27B suitability:** ✅ **Production-ready.** The conditional edge evaluation is deterministic string matching. Context interpolation uses `{{node_id.output.field}}` syntax resolved against `node_outputs` dict.

**Risk:** Low-medium. The `_evaluate_condition` method catches all exceptions and defaults to `True` (permissive). This means a malformed condition won't crash — it'll just execute the node. The subgraph filtering (`start_node_id`) is useful for partial replay.

---

### 4. PipelineStrategy — `pipeline.py` (~120 LOC)

**What it does:** Executes a fixed 7-phase pipeline: DISPATCH → RESEARCH → DRAFT → DEBATE → CONSENSUS → SYNTHESIS → REVIEW. REVIEW can trigger a retry loop (max 3) back to DEBATE.

**How it works:**
```
while True:
    for phase in [dispatch, research, draft, debate, consensus, synthesis, review]:
        result = executor.execute_node(phase_node)
        if phase == "review":
            if verdict == "PASS": return success
            else: retry_count++, loop back to debate
```

**LLM dependency:** None in the strategy. Each phase is a node that may call the LLM. The strategy just orchestrates the sequence and handles the review retry loop.

**27B suitability:** ⚠️ **Medium risk.** The strategy itself is deterministic, but it assumes each phase produces quality output. A 27B model may struggle with:
- **DEBATE phase:** requires adversarial reasoning
- **CONSENSUS phase:** requires synthesizing multiple viewpoints
- **SYNTHESIS phase:** requires coherent merging
- **REVIEW phase:** requires quality judgment (PASS/FAIL verdict)

The review retry loop (max 3) provides resilience, but if the 27B consistently fails review, the pipeline exhausts retries.

**Risk:** Medium. The 7-phase structure is heavy for a 27B model. Each phase is an LLM call, so a full pipeline run = 7+ LLM calls minimum. Cost and latency multiply. The retry loop can burn budget quickly.

---

### 5. MetaStrategy — `meta.py` (~100 LOC)

**What it does:** Recursive plan-execute-observe loop with depth clamping.

**How it works:**
```
_run_cycle(goal, depth=0):
    for node in workflow.nodes:
        result = executor.execute_node(node)
        if failed and depth < max_depth:
            _run_cycle(f"Retry: {goal}", depth+1)  # recursive retry
```

**LLM dependency:** None in the strategy. It's a retry-with-backoff pattern using recursion. The "meta" aspect is that on failure, it retries the entire workflow with a modified goal that includes the previous error.

**27B suitability:** ⚠️ **Medium risk.** The strategy itself is simple, but the recursive retry pattern means:
- Each retry executes ALL nodes again (not just the failed one)
- The goal string grows with each retry (`"Retry: ... (previous_error: ...)"`)
- Token usage compounds exponentially with depth
- A 27B model may not learn from the error context effectively

**Risk:** Medium-high. The depth clamping (`max_depth` from `workflow.budget.max_depth`, default 5) prevents infinite loops, but a deep retry chain burns significant budget. The "observe" step is implicit — there's no explicit reflection or analysis, just re-execution with the error in context.

---

### 6. SwarmStrategy — `swarm.py` (~150 LOC)

**What it does:** Three-phase multi-agent orchestration: decompose → dispatch → synthesize.

**How it works:**
```
Phase 1: LLM call — decompose goal into subtasks (returns JSON)
Phase 2: parallel execute_node() for each subtask
Phase 3: LLM call — synthesize all agent outputs into unified result
```

**LLM dependency:** **2 direct LLM calls** via `executor.call_llm()`:
1. **Decomposition prompt:** `"Decompose into specific, parallelizable subtasks"` → expects JSON `{"subtasks": [...]}`
2. **Synthesis prompt:** `"Combine multiple agent outputs into a coherent, unified result"`

**27B suitability:** ❌ **High risk.** This is the most LLM-dependent strategy:

- **Decomposition requires structured JSON output.** The 27B model must parse a complex prompt and return valid JSON with specific fields (`id`, `description`, `task_type`). JSON generation is a known weakness of smaller models.
- **The JSON parsing is fragile.** The code strips markdown fences (` ``` `) and calls `json.loads()`. If the 27B returns malformed JSON (common), it falls back to a single generic task — defeating the purpose of the swarm.
- **Synthesis requires coherent merging.** Combining multiple agent outputs into a "result greater than the sum of its parts" requires strong reasoning and synthesis capabilities.
- **Model is hardcoded:** `model_id="deepseek-chat"` — doesn't respect the workflow's assigned model or BYOK configuration.

**Risk:** High. The decomposition step is the critical failure point. If JSON parsing fails, the swarm degenerates into a single-task execution, wasting the parallel dispatch. The synthesis step is also at risk — a 27B model may produce incoherent merges.

---

### 7. LangGraphStrategy — `langgraph.py` (~100 LOC)

**What it does:** Supposed to execute LangGraph-defined workflows natively. Actually just falls back to the shared executor.

**How it works:**
```python
async def _execute_langgraph_node(self, ...):
    return {"success": False, "error": "LangGraph native execution not yet wired — use shared executor"}
```

**LLM dependency:** N/A — the native path is not implemented.

**27B suitability:** ❌ **Not applicable.** The strategy always falls back to `executor.execute_node()` for each node. It works, but it's not using LangGraph — it's just sequential node execution with extra overhead.

**Risk:** Low (functionally), but it's dead weight. The `langgraph` requirement in `requirements.txt` (currently 0.0.40) is outdated and the native integration was never completed.

---

## Complexity Comparison

| Strategy | LOC | LLM calls in strategy | Graph algo | Parallel execution | Retry logic |
|----------|-----|----------------------|------------|-------------------|-------------|
| Solo | 50 | 0 | None | No | Via NodeExecutor |
| DAG | 80 | 0 | Topological sort | Yes (layer-parallel) | Via NodeExecutor |
| Graph | 120 | 0 | Topological sort + conditions | Yes (layer-parallel) | Via NodeExecutor |
| Pipeline | 120 | 0 | Linear + review loop | No | Review retry (max 3) |
| Meta | 100 | 0 | Recursive retry | No | Recursive depth-clamped |
| Swarm | 150 | 2 | None | Yes (subtask-parallel) | Fallback on JSON parse fail |
| LangGraph | 100 | 0 | None | No | Fallback to shared executor |

---

## Recommendations

### Production-ready (default to these)

1. **Solo** — Use for simple single-step missions. Minimal overhead, maximum reliability.
2. **DAG** — Use for multi-step missions with dependencies. Layer-parallel execution is efficient.
3. **Graph** — Use when conditional branching is needed. Context interpolation is deterministic.

### Gated behind `STRATEGY_EXPERIMENTAL=1`

4. **Pipeline** — The 7-phase structure is heavy for a 27B model. Gate until runtime profiling confirms quality.
5. **Meta** — Recursive retry with error context is promising but untested. Gate until profiling.

### Deprecate or heavily gate

6. **Swarm** — The 2 direct LLM calls (JSON decomposition + synthesis) are high-risk with a 27B model. The hardcoded `model_id="deepseek-chat"` bypasses BYOK. Mark `DEPRECATED = True` until profiling proves otherwise.
7. **LangGraph** — Native execution is not wired. Falls back to shared executor. Consider removing or completing the integration.

### Plan scorer cost model

The roadmap calls for replacing `estimated_cost_usd` → `estimated_tokens` + `estimated_latency_ms`. This is a separate code change in `backend/app/services/plan_selection/plan_scorer.py`.

---

## Runtime Profiling Harness (Pending)

The code analysis above identifies *likely* suitability. Runtime profiling with actual 27B missions is needed to confirm. The harness should:

1. Run 5 missions per strategy type with identical prompts
2. Measure: success rate, token usage, latency, output quality (via LLM judge)
3. Publish results in a doc (not in code)
4. Use the results to set `DEPRECATED = True` flags

This requires the backend to be running and the 27B model to be available. Deferred to a live testing session.

---

## Provenance

Analysis based on reading all 7 strategy files, `base.py`, `workflow_models.py`, and `executor.py` (UnifiedExecutor dispatch). Code at commit `00d9ae2`. Strategies loaded via `UnifiedExecutor._load_strategies()` at `executor.py:85`.
