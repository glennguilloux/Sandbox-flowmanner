# Plan-Only Blueprint — Facts-Only Signal Inventory

Scope: enumerate the concrete `file:line` anchors a plan-only blueprint author
would cite. Facts only, no ranking, no recommendations. Read-only: nothing in
the repo was modified.

Repo root: /opt/flowmanner
Backend: /opt/flowmanner/backend

---

## 1. Blueprint authoring surface (CLI + backend schema)

### CLI entry / command wiring
- `/opt/flowmanner/cli/bin/flowmanner.js:1-2` — thin shim; forwards `argv` to `../dist/index.js`.
- `/opt/flowmanner/cli/src/index.ts:14-27` — imports and registers every subcommand.
- `/opt/flowmanner/cli/src/index.ts:43-75` — commander setup; registers `validate`, `push`, `publish`, `run`, `blueprints`, `runs`, `logs`, `status`, `abort`, `login`, `logout`, `init`, `whoami`, `config`.
- `/opt/flowmanner/cli/src/index.ts:50-58` — documented "Quick start" dev loop: `login → init → validate → push → publish → run`.

### CLI command files (the verbs a plan would reference)
- `/opt/flowmanner/cli/src/commands/validate.ts:7-29` — `validate [path]`; parses local `flowmanner.yaml` via `loadBlueprintFile`, prints node/edge counts.
- `/opt/flowmanner/cli/src/commands/push.ts:11-87` — `push` (`-f/--file`, `--update <id>`); `POST /api/v2/blueprints/` (create) or `PATCH /api/v2/blueprints/{id}` (update); caches `blueprint_id` to `.flowmanner/state.json` (`push.ts:65-74`).
- `/opt/flowmanner/cli/src/commands/publish.ts:11-40` — `publish [id]`; `POST /api/v2/blueprints/{id}/publish`; reads id from `.flowmanner/state.json` if not passed.
- `/opt/flowmanner/cli/src/commands/run.ts:33-93` — `run [id]`; `POST /api/v2/blueprints/{id}/run` with `input_data` + optional `budget_override`; then `followRun`.
- `/opt/flowmanner/cli/src/commands/run.ts:96-178` — `followRun` / `pollUntilTerminal` (`GET /api/v2/runs/{id}`) and `tailEvents` (`SSE /api/v2/runs/{id}/events`).
- `/opt/flowmanner/cli/src/commands/run.ts:187-205` — `printFinalSummary` reads `run.output_data.text` (string) or JSON-dumps `run.output_data`.
- `/opt/flowmanner/cli/src/lib/blueprint.ts` — `loadBlueprintFile` parser (imported by validate/push/publish).
- `/opt/flowmanner/cli/src/lib/api.ts` — `apiRequest`, `sseStream` HTTP/SSE helpers.

### Backend API surface (v2 blueprints)
- `/opt/flowmanner/backend/app/api/v2/blueprints.py:28` — `APIRouter(prefix="/blueprints")`.
- `blueprints.py:34-63` — `GET /blueprints` (list, type/status filter).
- `blueprints.py:66-76` — `POST /blueprints` (create → `BlueprintResponse`).
- `blueprints.py:82-91` — `GET /blueprints/{id}`.
- `blueprints.py:94-103` — `PATCH /blueprints/{id}` (update; new version if definition changes).
- `blueprints.py:106-113` — `DELETE /blueprints/{id}` (soft delete).
- `blueprints.py:119-127` — `POST /blueprints/{id}/publish`.
- `blueprints.py:133-142` — `POST /blueprints/{id}/run` → `RunResponse` (HTTP 201).
- `blueprints.py:148-157` — `GET /blueprints/{id}/versions`.
- Handlers wired via `app/api/_blueprint_cqrs/commands.py` / `queries.py` (`blueprints.py:12, 24-25`).

### Backend schema (Pydantic)
- `/opt/flowmanner/backend/app/schemas/blueprint.py:19-31` — `BlueprintNodeDefinition` (id, type, config, dependencies, assigned_model, assigned_agent_id, max_retries, fallback_strategy).
- `blueprint.py:34-40` — `BlueprintEdgeDefinition` (source, target, condition, label).
- `blueprint.py:43-49` — `BlueprintBudgetDefinition` (max_cost_usd, max_wall_time_seconds, max_iterations, max_depth).
- `blueprint.py:52-63` — `BlueprintDefinition` (blueprint_type, nodes, edges, budget, config).
- `blueprint.py:69-82` — `BlueprintCreate` (title, definition, input_schema, output_schema, tags, category, icon).
- `blueprint.py:85-98` — `BlueprintUpdate`.
- `blueprint.py:101-107` — `RunCreate` (input_data, budget_override).
- `blueprint.py:113-140` — `BlueprintResponse`.
- `blueprint.py:143-175` — `RunResponse` (incl. `output_data`, `mission_id` at `blueprint.py:168`).
- `blueprint.py:178-197` — `RunEventResponse`.

### Blueprint → Workflow conversion
- `/opt/flowmanner/backend/app/services/substrate/adapters.py:335-339` — `def blueprint_to_workflow(snapshot, blueprint_id, user_id) -> Workflow`.
- `adapters.py:358-375` — skips `start`/`end` sentinel nodes; derives real `WorkflowType` from topology (a "solo" with >1 node/any edge becomes a DAG).
- Design note: `/opt/flowmanner/backend/Docs/DESIGN-BLUEPRINT-RUN-UNIFIED-MODEL.md:356-360` documents the trivial snapshot→Workflow mapping.

### Run execution / output surfacing
- `/opt/flowmanner/backend/app/services/run_service.py:181-184` — on completion, `run.output_data = result.data` (dict) else `{"result": result.data}`.
- `blueprint.py:151-152` (`RunResponse.output_data`) and `blueprint.py:168` (`RunResponse.mission_id`) are the fields a plan JSON would surface.

---

## 2. Existing blueprint example to mirror

- `/opt/flowmanner/flowmanner.yaml:1-132` — self-referential `sandbox`-node blueprint.
  - `flowmanner.yaml:20` — `version: 1`.
  - `flowmanner.yaml:28` — `blueprint_type: solo`.
  - `flowmanner.yaml:30-52` — top-level `inputs:` (repo_url, prior_clues_url, workdir, model) with `type` + `default`.
  - `flowmanner.yaml:54-132` — `definition:` block (blueprint_type, nodes[], edges[], budget{}, config{}).
  - `flowmanner.yaml:56-68` — single node `self_audit`, `type: sandbox`, `config:` (template, shared_workspace, snapshot_before, agent, model, task_prompt).
  - `flowmanner.yaml:68` — `model: "{{ inputs.model }}"` (input-parameterized).
  - `flowmanner.yaml:126` — `edges: []`.
  - `flowmanner.yaml:127-131` — `budget:` (max_cost_usd 2.00, max_wall_time_seconds 600, max_iterations 20, max_depth 1).
  - `flowmanner.yaml:7-11` — authoring loop documented (`validate`/`push`/`publish`/`run`).
  - `flowmanner.yaml:13-16` — notes that `sandbox` is the ONLY egress-capable node type; `code`/`tool` nodes are network-isolated (cites `node_executor.py` lines, approximate).

---

## 3. Where plans / handoffs live today

Directories:
- `/opt/flowmanner/.sisyphus/plans/` — active plans (e.g. `frontend-wiring-roadmap.md`, `post-incident-remediation-plan.md`, `OPUS-BLUEPRINT-CHOICE-BRIEF.md`, `blueprint-sandbox-spawn-fix-2026-07-15.md`).
- `/opt/flowmanner/.sisyphus/plans/OLD/` — archived plans (e.g. `prompt-engineering-playbook-frontend.md`).
- `/opt/flowmanner/.sisyphus/handoff/` — handoff docs (e.g. `2026-07-19-sandbox-picker-deploy-handoff.md`, `2026-07-19-phase2-4-uplift-handoff.md`).
- `/opt/flowmanner/.sisyphus/brainstorm/` — brainstorm briefs (e.g. `mission-builder-chat/B3-UX.md`).
- `/opt/flowmanner/.sisyphus/SCHEMA.md` — knowledge-substrate schema (timeline + "earn a kind" gate).
- `/opt/flowmanner/docs/` — design/audit docs (e.g. `architecture/INTENT-EXECUTION-ARCHITECTURE.md`, `cli-rebuild-plan-2026-07-15.md`, `adr/`).
- `/opt/flowmanner/docs/archive/` — archived handoffs/exit-audits.
- `/opt/flowmanner/AGENTS.md` — authoritative infrastructure/system reference (router to per-machine AGENTS.*.md).

This deliverable target dir: `/opt/flowmanner/.sisyphus/plan-only-blueprint/`.

---

## 4. Substrate node-type capabilities (which types exist, which have egress)

### NodeType enum (all supported types)
- `/opt/flowmanner/backend/app/services/substrate/workflow_models.py:57-101` — `class NodeType(str, Enum)`.
  - Lines 65-71: `LLM_CALL`, `TOOL_CALL`, `CODE_EXECUTION`, `RAG_QUERY`, `WEB_SEARCH`, `FILE_OPERATION`, `HUMAN_REVIEW` (from mission_executor).
  - Lines 74-80: `BROWSER_NAVIGATE`, `BROWSER_SNAPSHOT`, `BROWSER_CLICK`, `BROWSER_TYPE`, `BROWSER_SCROLL`, `BROWSER_SCREENSHOT`, `BROWSER_CLOSE`.
  - Lines 83-88: `APPROVAL`, `SUB_WORKFLOW`, `PHASE_GATE`, `FAN_OUT`, `FAN_IN`, `SANDBOX`.
  - Lines 92-96: `TRANSFORM`, `CONDITION`, `LOG`, `LOOP`, `WEBHOOK` (template node types, Scope B).
  - Lines 98-101: convention note — read-only/passthrough types annotated `REVERSIBLE`; `TOOL_CALL`, `BROWSER_*`, `SUB_WORKFLOW`, `SANDBOX` default `IRREVERSIBLE`.

### EffectClass (side-effect classification)
- `workflow_models.py:37-54` — `class EffectClass(str, Enum)`: `REVERSIBLE`, `IRREVERSIBLE` (default fail-closed).
- `workflow_models.py:164` — `WorkflowNode.effect_class` defaults to `IRREVERSIBLE`.

### Node dispatch (type → handler)
- `/opt/flowmanner/backend/app/services/substrate/node_executor.py:1065-1149` — `async def _dispatch(...)` with `match node.type:`:
  - `:1078-1079` `LLM_CALL` → `_handle_llm`
  - `:1088-1089` `TOOL_CALL` → `_handle_tool`
  - `:1090-1091` `CODE_EXECUTION` → `_handle_code`
  - `:1092-1093` `RAG_QUERY` → `_handle_rag`
  - `:1094-1095` `WEB_SEARCH` → `_handle_web_search`
  - `:1096-1097` `FILE_OPERATION` → `_handle_file`
  - `:1098-1106` `HUMAN_REVIEW` / `:1107-1123` `APPROVAL` → `_handle_hitl_interrupt`
  - `:1124-1125` browser types → `_handle_browser`
  - `:1126-1127` `SUB_WORKFLOW` → `_handle_sub_workflow`
  - `:1128-1130` `PHASE_GATE | FAN_OUT | FAN_IN` → passthrough
  - `:1131-1132` `SANDBOX` → `_handle_sandbox_node`
  - `:1133-1134` `TRANSFORM` → `_handle_transform`
  - `:1135-1138` `CONDITION` → `_handle_condition` (branch-taking is strategy-level)
  - `:1139-1140` `LOG` → `_handle_log`
  - `:1141-1145` `LOOP` → `_handle_loop` (marker; bounds honored by strategy)
  - `:1146-1147` `WEBHOOK` → `_handle_webhook`
  - `:1148-1149` default → `{"success": False, "error": "Unknown node type: ..."}`

### Egress-capable types (external side effects)
- `SANDBOX` — `node_executor.py:2125` `_handle_sandbox_node` (sandboxd Docker execution; egress via container). `flowmanner.yaml:14-16` states `sandbox` is the ONLY egress-capable type; `code`/`tool` nodes are network-isolated.
- `WEBHOOK` — `node_executor.py:2039-2084` `_handle_webhook` emits outbound HTTP (`method` default POST) to `config['url']`; IRREVERSIBLE; SSRF-guarded by `_is_safe_url` (`node_executor.py:361-408`, rejects non-http(s) and private/loopback/link-local IPs).
- `TOOL_CALL` — `_handle_tool` may invoke external tools (cost event at `node_executor.py:1485-1498`); default `IRREVERSIBLE`.
- `BROWSER_*` — `_handle_browser`; default `IRREVERSIBLE` (per enum note `workflow_models.py:101`).

### Non-egress (read-only / passthrough) types
- `LLM_CALL`, `CODE_EXECUTION`, `RAG_QUERY`, `WEB_SEARCH`, `FILE_OPERATION`, `HUMAN_REVIEW`, `APPROVAL`, `PHASE_GATE`/`FAN_OUT`/`FAN_IN`, `TRANSFORM`, `CONDITION`, `LOG`, `LOOP` — annotated `REVERSIBLE` (per `workflow_models.py:47-50`, 98-101).
- `CODE_EXECUTION` handler uses a restricted wrapper (`_WORKSPACE_WRAPPER`, `node_executor.py:413-444`) — network-isolated.

---

## 5. Output / return path for a node's result

### Handler return shape
- Every `_handle_*` returns `dict[str, Any]` with keys `success`, `output`, `tokens`, `cost` (e.g. `_handle_transform` returns `{"success": True, "output": result, "tokens": 0, "cost": 0.0}` at `node_executor.py:1908`; `_handle_webhook` likewise emits a result dict).
- `NodeExecutor` is the shared `execute_node` path used by all 7 strategies (`node_executor.py:471-501` class + `__init__`).
- `execute_node` is referenced at `node_executor.py:783-797` (dispatch call sites within the two-phase STAGE→CONFIRM flow for IRREVERSIBLE nodes).

### Strategy result envelope
- `/opt/flowmanner/backend/app/services/substrate/workflow_models.py:243-264` — `class StrategyResult`: `success`, `status` ("completed"/"failed"/"aborted"/"paused"), `run_id`, `data`, `error`, `completed_nodes`, `failed_nodes`, `total_tokens`, `total_cost_usd`, `execution_time_ms`, `event_count`.

### Persisted run output
- `/opt/flowmanner/backend/app/services/run_service.py:181-184` — `run.output_data = result.data` (dict) or `{"result": result.data}`.
- `RunResponse.output_data` (`blueprint.py:152`) is what the CLI reads; CLI prints `run.output_data.text` (`cli/src/commands/run.ts:195-198`).
- `RunResponse.mission_id` (`blueprint.py:168`) links the run to its Mission.

### Substrate events (live stream the CLI tails)
- `RunEventResponse` (`blueprint.py:178-197`): `id`, `sequence`, `run_id`, `mission_id`, `type`, `payload`, `actor`, `task_id`, `causal_parent`, `timestamp`.
- CLI tails via `SSE /api/v2/runs/{id}/events` (`cli/src/commands/run.ts:152-178`).
- Event-log module: `app/services/substrate/event_log.py` (`_compute_idempotency_key`, `get_event_log`).

---

## Files inspected
- `/opt/flowmanner/cli/bin/flowmanner.js`
- `/opt/flowmanner/cli/src/index.ts`
- `/opt/flowmanner/cli/src/commands/validate.ts`
- `/opt/flowmanner/cli/src/commands/push.ts`
- `/opt/flowmanner/cli/src/commands/publish.ts`
- `/opt/flowmanner/cli/src/commands/run.ts`
- `/opt/flowmanner/backend/app/api/v2/blueprints.py`
- `/opt/flowmanner/backend/app/schemas/blueprint.py`
- `/opt/flowmanner/backend/app/services/substrate/workflow_models.py`
- `/opt/flowmanner/backend/app/services/substrate/node_executor.py` (lines 1-501, 618-796, 1065-1149, 1280-1299, 1480-1499, 1882-1911, 2039-2098, 2125-2163; full file is 2989 lines — remaining handler bodies and strategy-level logic NOT line-cited here)
- `/opt/flowmanner/backend/app/services/substrate/adapters.py` (lines 335-375)
- `/opt/flowmanner/backend/app/services/run_service.py` (lines 181-184)
- `/opt/flowmanner/flowmanner.yaml`
- `/opt/flowmanner/.sisyphus/SCHEMA.md` (referenced, not line-cited)
- Directory listings: `/opt/flowmanner/.sisyphus/plans/`, `/opt/flowmanner/.sisyphus/handoff/`, `/opt/flowmanner/.sisyphus/brainstorm/`, `/opt/flowmanner/docs/`

## Files NOT inspected (would be needed for a deeper plan)
- `/opt/flowmanner/backend/app/services/substrate/node_executor.py` handler bodies beyond cited lines (e.g. full `_handle_llm`, `_handle_tool`, `_handle_sandbox_node`, `_handle_browser`, `_handle_sub_workflow`, `_handle_code`, `_handle_rag`, `_handle_web_search`, `_handle_file`, `_handle_hitl_interrupt`, `_handle_loop`, `_handle_condition`).
- `/opt/flowmanner/backend/app/api/_blueprint_cqrs/commands.py` and `queries.py` (handler implementations behind the v2 router).
- `/opt/flowmanner/backend/app/services/substrate/` strategy files (SOLO/DAG/SWARM/PIPELINE/GRAPH/META/LANGGRAPH executors).
- Frontend `Mission Builder` source (`/home/glenn/FlowmannerV2-frontend/`) — emits the `start`/`end` sentinels noted in `adapters.py:358`.
- `cli/src/lib/blueprint.ts`, `cli/src/lib/api.ts`, `cli/src/types.ts` (full body).
