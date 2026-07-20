# PLAN-ONLY BLUEPRINT — Architecture & ADR

**Author:** Software Architect (fmw1)
**Date:** 2026-07-19
**Status:** Proposed — pending review (read-only; no repo edits, no commit)
**Target:** `flowmanner.yaml` — a blueprint whose ONLY job is to emit a structured PLAN as JSON. It executes **nothing** against the real codebase/repo.

---

## 0. Substrate facts (cited evidence)

These constrain every node-capability choice below. All citations are from the
homelab backend source tree.

| Fact | Evidence |
|------|----------|
| Valid node types | `NodeType` enum — `backend/app/services/substrate/workflow_models.py:57-95`. Members: `llm_call, tool_call, code_execution, rag_query, web_search, file_operation, human_review, browser_* (8), approval, sub_workflow, phase_gate, fan_out, fan_in, sandbox` (+ `transform, condition, log, loop, webhook`). **There is no `agent` node type** (confirmed: not in the enum). |
| `sandbox` is the only egress + clone-capable node | `_handle_sandbox_node` — `node_executor.py:2125+`: it creates a sandboxd Docker container (`_sandbox_client.create` / `ensure_sandbox_for_mission`, lines 2196-2201), writes files (`:2242`), and submits a task (`_sandbox_client.submit_task`, `:2278`) running an `opencode` agent. The host repo is cloned **inside** this container. This is also stated in the existing `flowmanner.yaml:14-16`. |
| `code` / `tool` nodes are network-isolated | Confirmed by `flowmanner.yaml:14-16` (cites `node_executor.py:1285`); they cannot reach the network or clone the repo. `code_execution` / `tool_call` handlers run in an isolated context with no egress. |
| Node effect classification is declared, fail-closed | `EffectClass` enum — `workflow_models.py:37-54`. Default `IRREVERSIBLE`; read-only nodes **MUST** be explicitly annotated `REVERSIBLE` or the two-phase `STAGE→CONFIRM` gate will pause them waiting for confirmation. A plan-only blueprint must mark every node `REVERSIBLE`. |
| Blueprint types available | `WorkflowType` enum — `workflow_models.py:113-119`: `solo, dag, pipeline, swarm, graph, meta, langgraph`. |
| Node carries `effect_class`, `dependencies`, `config` | `WorkflowNode` — `workflow_models.py:139-171`. `effect_class` defaults to `IRREVERSIBLE` (`:164`). |
| Input interpolation | `{{ inputs.<key> }}` rendered inside node handlers (`node_executor.py:1288-1292` for LLM; `:2274` for sandbox tasks). |

**Consequence for this design:** the ONLY node that can (a) see the codebase and
(b) run an LLM reasoning step over it is `sandbox`. A `code_execution` node
cannot reach the repo (no egress). An `llm_call` node has egress to the LLM API
but **no filesystem access to the cloned code**. So a multi-node design where a
`code_execution` clones and an `llm_call` reasons **cannot work** — the clone
happens in an isolated box the LLM node can't read. The DAG must therefore keep
"observe code" and "reason into a plan" inside a single egress-capable boundary,
or explicitly hand the gathered text forward via node `output_data`.

---

## 1. Proposed blueprint DAG / structure

### 1.1 Decision: `blueprint_type: dag` with ONE `sandbox` node (recommended)

I recommend a **`dag`** blueprint containing a single `sandbox` node that does
the entire "observe inputs + codebase → emit plan JSON" job and prints the plan
to stdout. This is the smallest shape that satisfies the constraint that code
observation and LLM reasoning must co-locate, and that nothing is mutated.

```
        ┌─────────────────────────────────────────────┐
inputs →│  plan_only (type: sandbox, effect: reversible)│→  plan JSON (stdout)
        └─────────────────────────────────────────────┘
```

Node list:

| id | type | edges (depends_on) | role | effect_class |
|----|------|--------------------|------|--------------|
| `plan_only` | `sandbox` | (none — entry) | Clone/observe inputs + repo, reason, **print** plan JSON. No writes back to host. | `reversible` |

Why a single node and not a multi-node graph:

- The plan author's reasoning needs to *read* the cloned repo (grep, AST,
  test output) **and** call an LLM. Only `sandbox` has both egress and a
  local filesystem. Splitting "gather" (code_execution, no egress) from "rank"
  (llm_call, no FS) is impossible because the gathered signal can't cross the
  isolation boundary except through `output_data` plumbing — which adds
  serialization + prompt-injection surface for zero benefit on a plan-only task.
- `human_review` / `approval` nodes exist but would *pause* the run waiting for
  a person — wrong for an autonomous "emit a plan" job. A human reviews the
  **output** plan, not a node mid-run.

### 1.2 The emitting node — why `sandbox` with an analyze-only `task_prompt`

The plan is emitted by the `sandbox` node's `task_prompt`. The prompt instructs
the opencode agent to:
1. clone the target repo (or use `inputs.repo_path` if already present),
2. gather signals with **read-only** shell commands (`git`, `grep`, `pytest --co`, `ruff`),
3. NOT edit any file, NOT push, NOT open PRs — a hard "no mutation" instruction,
4. print exactly one fenced ```json block containing the plan, and nothing else.

Justification vs alternatives:
- vs `llm_call` node: an `llm_call` can't see the filesystem, so it could only
  plan from a pre-supplied text blob. That pushes the "clone + gather" work onto
  a different node — which, as shown in §0, can't hand the repo to the LLM. Dead end.
- vs `code_execution` node: no egress → can't run the LLM reasoning step; also
  blocked from cloning. Dead end.
- vs a `sub_workflow` fan-out: overkill; nothing to parallelize for a single
  coherent plan, and each sub-sandbox would re-clone.

The `sandbox` node is the *only* substrate primitive that can both observe and
reason. We constrain it to read-only via `effect_class: reversible` + an
explicit prompt contract ("print, don't act").

### 1.3 Emitted plan JSON schema

The single fenced JSON block the node prints MUST conform to:

```json
{
  "blueprint": "plan-only-<name>",
  "generated_at": "ISO-8601",
  "inputs_received": { "repo_url": "...", "goal": "...", "scope": "..." },
  "steps": [
    {
      "id": "step-1",
      "title": "one-line summary",
      "owner_persona": "backend-engineer | frontend-engineer | architect | qa | devops | researcher",
      "depends_on": ["step-0"],
      "acceptance": "measurable done-condition (test passes / file exists / metric < X)",
      "effort": "s|m|l|xl",
      "risk": "low|medium|high",
      "evidence": ["path:line", "signal source"]
    }
  ],
  "assumptions": ["explicit premises the plan relies on"],
  "open_questions": ["decisions a human must make before/while executing"],
  "risks": ["cross-cutting risks not tied to one step"],
  "estimated_total_effort": "s|m|l|xl"
}
```

Rules the prompt enforces:
- `steps` is a topological order; `depends_on` references only ids that appear
  earlier or are themselves resolvable. No cycles.
- `owner_persona` is drawn from a fixed vocabulary (so the plan routes to the
  right downstream worker).
- `acceptance` is testable, not prose ("`pytest tests/x.py` green", not "works").
- `evidence` must cite real paths/signals gathered in step 2 — no invented refs.

---

## 2. ADR — Architecture Decision Record

```markdown
# ADR-PLANONLY-001: Structure of the plan-only blueprint

## Status
Proposed

## Context
Flowmanner needs a blueprint that analyzes inputs + the codebase and emits a
STRUCTURED PLAN as JSON, executing nothing (no code change, no repo mutation,
no side effects). The existing flowmanner.yaml (flowmanner-self-audit) is an
EXECUTION blueprint (one sandbox node that clones + ranks into a "clues" list).
We need a distinct, plan-only variant.

Substrate constraints that drive the decision (verified in code):
- Only `sandbox` nodes have network egress + can clone the repo
  (node_executor.py:2125+).
- `code`/`tool` nodes are network-isolated and cannot see the host repo.
- There is NO `agent` node type (workflow_models.py:57-95).
- Read-only nodes MUST be annotated `effect_class: reversible` or the
  STAGE→CONFIRM gate will pause them (workflow_models.py:37-54).

## Decision
Use `blueprint_type: dag` with a SINGLE `sandbox` node (`plan_only`) that
observes inputs + repo and PRINTS a plan JSON block. Mark the node
`effect_class: reversible` and instruct the agent (in task_prompt) to perform
read-only analysis and emit, never mutate.

## Consequences
What becomes easier:
- Satisfies the "execute nothing" requirement with one primitive that can both
  observe the code and reason.
- Smallest possible surface; trivial to review and to evolve (change the prompt,
  not the graph).
- `reversible` annotation means the run never blocks on STAGE→CONFIRM.

What we give up:
- No in-graph separation of "gather" vs "rank" → the prompt contract must be
  precise so the agent doesn't drift into acting. (Mitigated by explicit
  "print, don't act" instruction + single JSON block output rule.)
- A single sandbox = single point of failure; if the clone or LLM call fails,
  the whole plan fails (no partial fan_in rescue). Acceptable for a plan-only
  job where a partial plan is worthless.
- Reasoning quality is bounded by one agent pass; no independent "ranker"
  node to cross-check the planner. (Could be added later as a second reversible
  sandbox, but that reintroduces cross-node signal passing — see trade-offs.)
```

### 2.1 Trade-off matrix

| Option | Scalability | Coupling | Cost | Reversibility | What you GIVE UP |
|--------|-------------|----------|------|---------------|------------------|
| **A. `dag`, single `sandbox` "do everything + emit plan" (CHOSEN)** | Fine for one plan | Low (1 node) | 1 sandbox run | High (reversible, no mutation) | Independent ranker check; single point of failure |
| B. `solo` blueprint, single `sandbox` | Same | Lowest | 1 sandbox | High | Loses explicit `edges`/DAG semantics; no room to later insert a gather node without redesign |
| C. Multi-node `dag`: `code_execution`(gather) → `llm_call`(rank) → `human_review`(emit) | Parallelizable | High | 2-3 nodes | Needs confirm gate | **Cannot work** — `code_execution` has no egress to clone; `llm_call` can't read the cloned FS. Signal can't cross the isolation boundary cleanly. |
| D. `pipeline` + `sandbox` per phase (gather / rank / emit) | Horizontal | Medium | 3 sandboxes (re-clone each) | High per-node | 3× clone cost; no shared FS between phases unless `shared_workspace: true` (then mutation risk rises) |

**Rule honored:** trade-offs named, not just wins. Option C is rejected on a
hard substrate constraint, not preference.

---

## 3. Exact `flowmanner.yaml` SHAPE (fill-in skeleton, not a full impl)

This is the shape the implementer fills in. Top-level keys mirror the existing
`flowmanner.yaml` (version 1, `cli/` authoring). Pseudocode/YAML only — no edits
to the live file.

```yaml
# flowmanner.yaml — version 1
# PLAN-ONLY blueprint: analyze inputs + repo, EMIT a plan JSON, execute nothing.
# Author with cli/:  flowmanner validate → push → publish → run --input ...

version: 1

name: "plan-only-<name>"          # e.g. plan-only-feature-x
description: |
  Plan-only analyzer. A single reversible sandbox node observes the inputs and
  the target codebase (read-only) and prints a structured PLAN as JSON. It never
  edits files, pushes, or opens PRs.

blueprint_type: dag               # NOT solo/pipeline — keeps edges explicit for future growth

inputs:
  repo_url:
    type: string
    default: "https://github.com/glennguilloux/FlowmannerV2.git"
  goal:
    type: string
    default: ""                   # free-text objective the plan must satisfy
  scope:
    type: string
    default: ""                   # glob/path filter, optional (e.g. "backend/app/services/*")
  prior_plan_url:
    type: string
    default: ""                   # optional prior plan for reconciliation
  workdir:
    type: string
    default: "/workspace/repo"
  model:
    type: string
    default: ""                   # forwarded to sandboxd opencode; "" = sandbox default

definition:
  blueprint_type: dag
  nodes:
    - id: plan_only
      type: sandbox
      title: "Observe + reason + emit plan (read-only)"
      description: >
        Egress-capable sandbox that clones the repo, gathers read-only signals,
        reasons into a plan, and PRINTS one fenced ```json block. No mutation.
      config:
        template: worker-standard
        shared_workspace: false
        snapshot_before: false
        agent: opencode
        model: "{{ inputs.model }}"
        effect_class: reversible          # CRITICAL: prevents STAGE→CONFIRM gate pause
        task_prompt: |
          You are a PLANNING agent. You do NOT implement anything.

          HARD RULES (violation = failure):
          - Do NOT edit, create, push, or open PRs on any repository.
          - Observe only with read-only commands (git, grep, pytest --co, ruff, ast).
          - Output EXACTLY one fenced ```json block. No prose outside it.

          STEP 1 — Clone / locate
            workdir="${workdir:-/workspace/repo}"
            git clone --depth 1 "${repo_url}" "$workdir" || cd "$workdir"
            cd "$workdir"

          STEP 2 — Gather signals (print condensed, then discard)
            a) test/lint baseline:  pytest --co -q | tail -3 ; ruff check . | tail -5
            b) debt markers: grep -rnE '\b(TODO|FIXME|HACK)\b' ${scope:-.} ...
            c) prior plan reconciliation if prior_plan_url non-empty (curl -fsSL)

          STEP 3 — Plan
            Produce the JSON per the schema:
              steps[{id,title,owner_persona,depends_on,acceptance,effort,risk,evidence}]
              assumptions[], open_questions[], risks[], estimated_total_effort
            owner_persona ∈ {backend-engineer,frontend-engineer,architect,qa,devops,researcher}
            acceptance MUST be testable; evidence MUST cite real path:line.

          STEP 4 — Output
            Print exactly:
              ```json
              { ...plan... }
              ```
            Nothing else.

  edges: []                        # single node; empty edge list
  budget:
    max_cost_usd: 2.00
    max_wall_time_seconds: 600
    max_iterations: 20
    max_depth: 1
  config: {}
```

### 3.1 Implementer checklist (what to fill / verify)

1. Replace `<name>` and `goal`/`scope` defaults with the real target.
2. Keep `effect_class: reversible` on the node — without it the run pauses at
   the STAGE→CONFIRM gate (workflow_models.py:45-50).
3. `blueprint_type: dag` is chosen over `solo` so `edges` is a first-class
   field; if a future "ranker" node is added it drops in without a redesign.
4. Validate with `flowmanner validate` before `push`.
5. Do NOT add `webhook` / `approval` nodes — they introduce irreversible side
   effects or human-pause, both contrary to "plan-only, autonomous emit".

---

## 4. Open questions for the reviewer

- **Goal source:** should `goal` be a required input (no default) so a plan
  can't be generated without intent, or is the current empty-default acceptable
  for ad-hoc runs?
- **Plan routing:** is the emitted `owner_persona` vocabulary stable enough to
  drive downstream kanban card assignment, or should the blueprint stay
  persona-agnostic and let a human route?
- **Reconciliation:** if `prior_plan_url` is used, do we want status transitions
  (`open|done|stale`) like the self-audit "clues" schema, or a fresh plan each run?
- **Single vs dual node:** if plan quality from one agent pass is insufficient,
  are we willing to pay for a second reversible `sandbox` ranker node (re-clone
  cost) — or keep it single-node by contract?
```
