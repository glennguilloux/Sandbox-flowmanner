# Flowmanner Execution Engine — Deep-Dive Architecture

*Based on 40+ service files across mission_executor, decomposition_service, dag_executor, swarm, swarm_pipeline, nexus, graph_executor, browser_agent, self_improvement, learning_service, trigger_scheduler, langgraph, flow, and runtime.*

---

## 1. Architecture Overview

The execution engine spans **five layers** from user intent to agent action:

```
LAYER 1: ROUTING (ExecutionRouter)
  Goal analysis → Route: mission | workflow | AI

LAYER 2: PLANNING
  ├── Mission: LLM decomposes goal → JSON task plan
  ├── Swarm: LLM decomposes → subtasks with types/dependencies
  ├── Graph: Pre-defined node graph (visual builder)
  └── Nexus: AIExecutionPlanner uses Q/K/V attention for agent matching

LAYER 3: ORCHESTRATION
  ├── Solo: mission_executor.py — single-agent task loop
  ├── DAG: decomposition_service.py — topological sort, layer execution
  ├── Swarm: swarm/orchestrator.py — decompose→match→dispatch→execute→synthesize
  ├── Pipeline: swarm_pipeline/ — 7-phase state machine
  ├── Graph: graph_executor.py — GraphInterpreter with Kahn algorithm
  └── LangGraph: langgraph/agent.py — StateGraph with human-in-the-loop

LAYER 4: EXECUTION
  ├── Tool invocation (browser, terminal, search, RAG, code)
  ├── Agent resolution (system prompt from AgentTemplate)
  ├── Code sandbox (isolated subprocess, restricted builtins)
  └── Browser agent (LLM-driven interactive loop, 15 iterations)

LAYER 5: LEARNING & IMPROVEMENT
  ├── Feedback storage (PostgreSQL + Qdrant embeddings)
  ├── Self-improvement (failure analysis → Improvement suggestions)
  └── Learning (similarity-based context injection, model recommendation)
```

---

## 2. Layer 1: Routing

### ExecutionRouter (flow/execution_router.py)
The entry point that decides which execution path to take.

```
User goal → analyze_goal(goal)
  ├── mission keywords ("execute", "mission", "task", "process") → Mission route
  ├── workflow keywords ("workflow", "pipeline", "chain", "sequence") → Workflow route
  └── default → AI route ("analyze", "generate", "chat", "research")

Overridable via project config: `project.config.route`
Generates internal JWT tokens for inter-service auth.
```

---

## 3. Layer 2: Planning

### Mission Decomposition (mission_executor.py)
```
Mission (description, type, constraints)
  → LLM plan_mission()
  → JSON array of tasks: [{title, task_type, dependencies: [index], ...}]
  → Save plan to DB
```

**Task types:** `llm`, `tool`, `rag`, `code`, `review`

### Decomposition Service (decomposition_service.py)
```
Manual decomposition strategy:
  Pass 1: Create MissionTask records with order_index
  Pass 2: Resolve index-based depends_on → UUID dependencies
  → validate_dag() — check references + cycle detection
  → Mission status = "decomposed"
```

### DAG Executor (dag_executor.py)
Pure algorithmic DAG handling using Kahn algorithm:

```
Functions:
  validate_dag(tasks) → error list (ref check + cycle detection via DFS)
  topological_sort(tasks) → list of execution layers
  get_ready_tasks(tasks) → task IDs with all deps completed
  get_downstream(task_id, tasks) → transitive dependents (BFS)
  _has_cycle(tasks) → DFS with WHITE/GRAY/BLACK coloring
```

**Parallelism:** Tasks within the same topological layer can execute concurrently — all dependencies satisfied by previous layers.

### Swarm Orchestrator (swarm/orchestrator.py)
```
goal → DECOMPOSE_SYSTEM_PROMPT (LLM)
  → subtasks: [{title, type, dependencies}]
  → AgentRegistryService.match_agent(task) → best agent
  → _execute_tasks(strategy, dependencies)
  → SYNTHESIZE_SYSTEM_PROMPT (LLM) → unified result
  → Conflict resolution: note both perspectives or pick stronger
```

### Swarm Pipeline (swarm_pipeline/)
7-phase state machine with REVIEW→DEBATE loop for retries:

```
DISPATCH → RESEARCH → DRAFT → DEBATE → CONSENSUS → SYNTHESIS → REVIEW
                                                            ↑         │
                                                            └─────────┘ (retry on FAIL)

Status machine: PENDING → RUNNING → PAUSED ⇄ RUNNING → COMPLETED | FAILED | CANCELLED
```

**Phase implementations (swarm_pipeline/phases/):**
- `dispatch.py` — Distribute tasks to agents
- `research.py` — Initial research activity
- `draft.py` — Generate initial outputs
- `debate.py` — Agents debate drafts, accept review_feedback
- `consensus.py` — Reach consensus from debate results
- `synthesis.py` — Synthesize into final result
- `review.py` — Final quality review, PASS/FAIL verdict

### Nexus AI Execution Planner (nexus/ai_execution_planner.py)
Hybrid Q/K/V attention-inspired semantic agent matching:

```
Task requirements → Query vector
Agent capabilities → Key vectors
  → attention_score(Q, K) → best agent via Value
  → ExecutionStep(agent_id, confidence: float)
  → Fallback: legacy rule-based if TopologyManager unavailable

ExecutionPlan: goal, estimated_cost, steps[], planning_method="semantic"
```

### Graph Workflow (graph_executor.py)
Pre-defined node graphs (from visual builder):

```
GraphInterpreter.execute(workflow, context)
  → _topological_sort(nodes) → execution layers (Kahn)
  → For each layer: await asyncio.gather(execute_node(n) for n in layer)
  → NodeHandlerRegistry[ nodeType ] → handle(context, config)
  → After each node: save GraphState to DB, broadcast via WebSocket
  → Pause support: if node output contains "pause" key
```

---

## 4. Layer 3: Orchestration

### Mission Executor (mission_executor.py)
The core execution loop:

```python
execute_mission(mission, db):
    plan = LLM plan_mission(mission)
    while not all_tasks_terminal():
        ready = get_ready_tasks(tasks)
        for task in ready:
            task.status = "running"
            system_prompt = resolve_agent_prompt(task.assigned_agent_id)
            result = execute_task(task, system_prompt)
            if success:
                task.status = "completed"
            elif is_retryable(error):
                task.retry_count += 1
                task.status = "pending"  # re-queue
            else:
                task.status = "failed"
                apply_fallback(mission.fallback_strategy)
                    # "human_escalate" → pause mission
                    # "abort" → cancel mission
```

**Error classification:**
- RetryableMissionError: timeout, 5xx, rate limits
- PermanentMissionError: 401/403/404, invalid config

**Retry:** max_retries (default 3), status reset to "pending"

### Tool Execution Framework

| Tool | Implementation |
|------|---------------|
| Web Search | ToolRegistry → web search API |
| Code Execution | Isolated subprocess: temp dir, restricted builtins (`__import__`, `open`, `exec` removed), 60s timeout, memory limits, 1MB output truncation, blocked network, prohibited patterns blocklist |
| File Read | ToolRegistry → file read operations |
| RAG Search | Qdrant vector similarity search |
| Browser | browser_agent.py → LLM-driven interactive loop |
| Terminal | Shell command execution in sandbox |

### Browser Agent (browser_agent.py)
LLM-powered interactive browser automation:

```
Loop (max 15 iterations):
  1. Build context: system prompt + request + page context (URL, title, elements)
  2. LLM returns JSON action: navigate(url) | snapshot() | click(ref) | type(ref,text) | scroll(y) | done(msg)
  3. Execute action on browser
  4. If done: return summary + screenshot + action log
```

---

## 5. Layer 4: Learning & Improvement

### Learning Service (learning_service.py)
Dual persistence: PostgreSQL structured feedback + Qdrant semantic embeddings.

```
record_execution(task_description, plan, result, model, success):
  → _store_feedback() → PostgreSQL learning_feedback table
  → _store_embedding() → Qdrant mission_embeddings collection

inject_into_planner_context(task_description):
  → Similarity search (Qdrant vector or PostgreSQL keyword fallback)
  → Calculate success patterns (≥70% success rate)
  → Return: success patterns, avg success rate, top patterns

get_best_model_for_task(task_description):
  → Query similar historical tasks
  → Aggregate success rate per model
  → Return model with highest success rate
```

### Self-Improvement Engine (self_improvement.py)
Failure analysis → improvement generation → strategy application:

```
Failure type → Improvement suggestion:
  code → review execution strategy, add validation, upgrade model
  api → verify endpoint, exponential backoff, check credentials
  rag → expand corpus, improve preprocessing, upgrade embeddings
  timeout → increase timeout, optimize, decompose into sub-tasks
  validation → stricter schema validation, clearer error messages
  default → review logs, implement error monitoring

generate_strategy(failure_type, context) → MissionImprovement (pending)
apply_strategy(improvement_id) → MissionImprovement (applied)
```

### Trigger Scheduler (trigger_scheduler.py)
Background asyncio task, ticks every 30 seconds:

```
TriggerScheduler._run():
  while True:
    sleep(30)
    process_cron_triggers(db)  → evaluate due cron triggers
    + webhook triggers (path-matched, on-demand)
```

### Runtime Self-Healing (runtime/)
```
runtime/
├── anomaly_detector.py — Detect execution anomalies
├── health_monitor.py — System health monitoring
├── predictive_scaler.py — Predictive resource scaling
├── recovery_strategies.py — Auto-recovery from failures
├── runtime_sdk.py — Client SDK for runtime operations
└── self_healing.py — Autonomous healing actions
```

---

## 6. Cross-Cutting Concerns

### Execution Models Compared

| Model | Planning | Execution | Consensus | Use Case |
|-------|----------|-----------|-----------|----------|
| **Solo Mission** | LLM plan | Serial task loop | None | Simple goals |
| **DAG Mission** | Manual decomposition | Topological layers, parallel | None | Complex workflows |
| **Swarm** | LLM decompose | Hub-and-spoke orchestrator | Synthesis-time conflict resolution | Multi-agent goals |
| **Swarm Pipeline** | 7-phase state machine | Sequential + debate loop | Consensus round | High-quality outputs |
| **Graph Workflow** | Visual builder | Kahn layers, parallel nodes | None | Pre-defined flows |
| **Nexus** | AI semantic matching | Distributed execution | Capability negotiation | Cross-system |
| **LangGraph** | StateGraph definition | Checkpointed graph | Human-in-the-loop | Complex automations |

### State Tracking Across All Models

Every execution model tracks:
- Status: pending → running → completed | failed | cancelled
- Timestamps: started_at, completed_at
- Error state: error_message, retry_count, max_retries
- Costs: tokens_used, estimated_cost, actual_cost
- Observability: Jaeger traces, Langfuse metrics, WebSocket events
- Feedback: MissionLog, FeedbackReport, FeedbackPattern, LearningFeedback

### Security Boundaries

```
User code (sandbox):
  - Temp directory isolation
  - Restricted builtins (no __import__, open, exec)
  - 60s timeout, memory limits, 1MB output
  - Network blocked
  - Prohibited patterns blocklist (os, sys, subprocess)

Browser agent:
  - Session isolation per agent
  - Activity tracking for session timeout
  - Screenshot-based feedback (not raw HTML)
```
ENDOFDOC'"
