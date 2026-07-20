# BACKEND.md — Substrate Unknowns for a Plan-Only Blueprint

**Author:** Backend Architect (fmw2)
**Subject:** How to run `flowmanner.yaml` as a *plan-only* blueprint — analyze the
repo + emit a structured PLAN (JSON) with **zero side effects** (no repo
mutation, no git commit).
**Scope:** Read-only substrate investigation. No repo files were edited; nothing
was committed.
**Verdict up front:** A pure plan-only run is **achievable today** with the
existing `sandbox` node. The executor does **not** force any mutation — cloning
and file writes are driven entirely by the `task_prompt`, which we can constrain
to "analyze + print JSON, never write files / never git commit". The only real
gap is a stale line reference in `flowmanner.yaml` (see §5).

---

## 1. Which node type can (a) clone/read the repo and (b) emit a plan without mutating anything?

**`sandbox` is the only egress-capable, repo-cloning node type.** Everything else
is network-isolated or in-process-only.

- **Dispatch table** (`node_executor.py:1077-1149`): `_dispatch()` routes
  `NodeType.SANDBOX` → `_handle_sandbox_node()` at `node_executor.py:1131-1132`.
- **`sandbox` handler** (`_handle_sandbox_node`, `node_executor.py:2125-2424`):
  talks to **sandboxd** via `SandboxdClient` (HTTP, same-host). sandboxd-base
  ships `git`, so the agent inside the container has network egress + can clone
  the repo. The handler itself performs **no repo mutation on the host** — it
  only (1) creates a sandbox container, (2) optionally writes injected files,
  (3) submits a `task_prompt` to the agent, (4) streams SSE, and (5) returns the
  agent's text output. See `node_executor.py:2177-2420`.
- **`code` / `tool` nodes are network-isolated** and cannot see `/opt/flowmanner`:
  - `_handle_code` runs the user code in a restricted **subprocess** with
    "**No network access (blocked via environment)**" — explicitly stated at
    `node_executor.py:1682-1683` (handler body at `node_executor.py:1650-1677`,
    sandbox wrapper at `node_executor.py:1679+`). It also blocks
    `import os/sys/socket/urllib/http`, `open()`, `exec/eval/compile`
    (`node_executor.py:1700-1724`) and runs from a `tempfile.mkdtemp`
    workspace (`node_executor.py:1697`) — it has no path to the host repo.
  - `_handle_tool` (`node_executor.py:1504-1519+`) executes registered tools
    (capability-gated) inside the backend process; it has no filesystem access to
    `/opt/flowmanner` and no egress model for cloning.
- **`agent` is NOT a node type.** The `NodeType` enum
  (`workflow_models.py:57-101`) lists: `llm_call, tool_call, code_execution,
  rag_query, web_search, file_operation, human_review, browser_*, approval,
  sub_workflow, phase_gate, fan_out, fan_in, sandbox, transform, condition, log,
  loop, webhook`. There is no `agent` type. "Agent" behavior for plan-only is
  delivered *inside* a `sandbox` task via the opencode coding agent
  (`node_executor.py:2281`, `agent="opencode"`).

**Constraining the sandbox to plan-only (analyze + print JSON, never write /
never commit):**
The executor does not clone or write on its own — cloning is in the
`task_prompt` (`flowmanner.yaml:74-78` does `git clone` *inside the prompt*), and
file mutation is gated behind the `input_files` config key. To make a node
strictly read-only:
- Set `task_prompt` to instruct the agent: *"clone to a temp dir, analyze, print
  exactly one fenced ```json plan``` block, never run `git commit`/`git push`,
  never write files outside /tmp."* (The existing `flowmanner.yaml:69-124`
  task_prompt is already structured this way — it only prints JSON, no commit.)
- Leave `input_files: {}` (default, `node_executor.py:2150`) so the handler skips
  the write-file step entirely (`if input_files:` guard at `node_executor.py:2238`).
- Leave `snapshot_before: false` (default, `node_executor.py:2151`) so no
  snapshot is taken (`if snapshot_before:` guard at `node_executor.py:2218`).
- Leave `shared_workspace: false` (default, `node_executor.py:2149`) so a fresh
  ephemeral container is used and torn down by the caller — no persistent
  workspace is reused.
- **Crucially, the executor never calls `git commit` for a sandbox node.** The
  only host-side writes a sandbox node can trigger are: (a) the sandbox container
  filesystem (ephemeral, inside sandboxd), and (b) `input_files` writes (only if
  `config.input_files` is non-empty). A plan-only task_prompt that avoids
  `git commit`/`git push` and sets `input_files: {}` therefore has **zero host
  side effects**. Confirmed by reading `_handle_sandbox_node` end-to-end
  (`node_executor.py:2177-2420`) — no mutation calls outside the guards above.

**Cite:**
- `node_executor.py:1077-1149` (dispatch `match`)
- `node_executor.py:1131-1132` (SANDBOX → `_handle_sandbox_node`)
- `node_executor.py:2125-2424` (sandbox handler, all egress + output)
- `node_executor.py:1650-1677` + `1682-1683` (code node: no network, host-isolated)
- `node_executor.py:1504` (tool node)
- `workflow_models.py:57-101` (NodeType enum — no `agent` type)
- `flowmanner.yaml:74-78` (clone lives in the prompt, not the executor)

---

## 2. Exact config keys for the `sandbox` node + the template name that works on this host

**Config keys read by `_handle_sandbox_node`** (`node_executor.py:2143-2152`):

| Key | Source | Default | Meaning |
|-----|--------|---------|---------|
| `task_prompt` | `config.get("task_prompt") or context.get("task_prompt")` | **required** — returns `{"success": False, "error": "No task_prompt provided"}` if missing (`node_executor.py:2144-2146`) | The coding-agent instruction. Supports `{{ inputs.<key> }}` interpolation (`node_executor.py:2274`, `_render_inputs` at `2262-2272`). |
| `template` | `config.get("template", "worker-standard")` | `"worker-standard"` (`node_executor.py:2148`) | sandboxd template name. |
| `shared_workspace` | `config.get("shared_workspace", False)` | `False` (`node_executor.py:2149`) | Reuse a mission/run sandbox instead of creating fresh. |
| `input_files` | `config.get("input_files", {})` | `{}` (`node_executor.py:2150`) | `dict[path] -> content` written into the container *before* the task. Skipped when empty. |
| `snapshot_before` | `config.get("snapshot_before", False)` | `False` (`node_executor.py:2151`) | Create a container snapshot checkpoint. Skipped when false. |
| `model` | `config.get("model") or node.assigned_model` | `None` → sandboxd default (`node_executor.py:2152`) | Passed to `submit_task(model=...)` (`node_executor.py:2282`). Supports `{{ inputs.model }}` rendering (`node_executor.py:2153-2165`). |
| `agent` | *not read from config here* — hardcoded `agent="opencode"` at `node_executor.py:2281` | `opencode` | The sandboxd coding agent. |

> Note: `flowmanner.yaml` also sets `agent: opencode` in its `config:` block
> (`flowmanner.yaml:67`) but the handler ignores a config `agent` key and always
> passes `opencode` (`node_executor.py:2281`). Harmless, but worth knowing the
> `agent` config key is currently a no-op for sandbox nodes.

**Template name that actually works on this host: `worker-standard`.**

- The backend default is `SANDBOXD_DEFAULT_TEMPLATE = "worker-standard"`
  (`backend/app/config.py:306`).
- `SandboxdClient.create` resolves `effective_template = template if template is
  not None else settings.SANDBOXD_DEFAULT_TEMPLATE` (`sandboxd_client.py:151`),
  and only attaches `template` to the payload when truthy
  (`sandboxd_client.py:167-168`). So an empty/missing template silently sends no
  template and falls back to sandboxd's own default via the internal API.
- `flowmanner.yaml` explicitly uses `template: worker-standard`
  (`flowmanner.yaml:64`), matching the backend default — **this is the verified,
  working choice.**
- **Substrate GAP / gotcha (doc drift):** Several places still reference
  `python-img`:
  - `backend/app/models/playground_models.py:84-85` defaults `template` to
    `"python-img"`.
  - `backend/app/services/playground_service.py:36,218` and
    `backend/app/api/v1/playground.py:90` use `"python-img"`.
  - `backend/tests/test_mission_sandbox_integration.py:128` asserts
    `SANDBOXD_DEFAULT_TEMPLATE == "python-img"` — **this test is now stale**
    because `config.py:306` is `"worker-standard"`. (Historical: commit `4f88743`
    flipped the default to `python-img`; a later change moved it to
    `worker-standard`. See `backend/alembic/versions/20260611_*.py` and
    `backend/sprint-status.yaml:55`.)
  - `python` (bare) is also a valid historical template name but is not the
    current default.
  - **Recommendation for plan-only:** keep `template: worker-standard` (matches
    `config.py:306` and `flowmanner.yaml`). Do **not** switch to `python-img`
    unless you specifically need that image; `worker-standard` is the value that
    is both the code default and the one exercised by the existing blueprint.

**Cite:**
- `node_executor.py:2143-2152` (config key extraction)
- `node_executor.py:2144-2146` (task_prompt required)
- `node_executor.py:2153-2165` (`{{ inputs.model }}` render)
- `node_executor.py:2262-2272` (`{{ inputs.* }}` render for task_prompt)
- `node_executor.py:2281` (hardcoded `agent="opencode"`)
- `backend/app/config.py:306` (`SANDBOXD_DEFAULT_TEMPLATE = "worker-standard"`)
- `sandboxd_client.py:151` + `167-168` (template resolution + payload attach)
- `flowmanner.yaml:64` (uses `worker-standard`)
- `backend/app/models/playground_models.py:84-85`,
  `backend/app/services/playground_service.py:36,218`,
  `backend/app/api/v1/playground.py:90`,
  `backend/tests/test_mission_sandbox_integration.py:128` (stale `python-img`
  references — drift GAP)

---

## 3. How is the plan passed OUT of the node? Output envelope.

The plan is emitted by the sandbox agent as **text** (a fenced ```json block```)
and captured by the executor into a structured output envelope.

- The agent's final message is read from the terminal `done` SSE event:
  `agent_output = ev_data.get("agent_message_final") or ev_data.get("stdout") or ""`
  (`node_executor.py:2353-2354`).
- The handler returns it inside `result["output"]`:
  ```python
  return {
      "success": succeeded,
      "output": {
          "sandbox_id": ..., "task_id": ..., "status": ...,
          "agent_output": agent_output,          # <-- the plan text lives here
          "stdout": ..., "exit_code": ..., "error_message": ...,
          "files_changed": ..., "tokens": ...,
      },
      "tokens": 0, "cost": 0.0,
  }
  ```
  (`node_executor.py:2373-2388`). The terminal event type is `done`
  (`node_executor.py:2343`); `succeeded = task_status == "succeeded"`
  (`node_executor.py:2351`).
- The caller (`execute_node`) stores this whole dict as `node.output_data`:
  `node.output_data = result.get("output")` (`node_executor.py:845`). So the
  blueprint run reads `node.output_data["agent_output"]` to get the plan text.
- **Output envelope summary:** the plan is **plain text** in
  `output.agent_output`. The blueprint layer must parse the fenced ```json```
  block out of that string to get the structured PLAN. There is no automatic
  JSON parsing by the executor — it returns raw text. (This matches
  `flowmanner.yaml`'s STEP 5 contract: "Print exactly one fenced json block"
  — `flowmanner.yaml:119-124`.)
- SSE framing: terminal event is `type == "done"` carrying `TaskResult` in
  `data`; sandboxd's live wire is SSE, persisted replay is NDJSON — both
  normalized by `SandboxdClient.task_events` / `_normalize_event`
  (`sandboxd_client.py:304-423`). The stream yields `done` and the handler
  returns (`node_executor.py:2343-2388`).

**Cite:**
- `node_executor.py:2353-2354` (agent_output extraction)
- `node_executor.py:2343-2388` (terminal `done` handling + return envelope)
- `node_executor.py:2373-2388` (`output` dict with `agent_output`)
- `node_executor.py:845` (`node.output_data = result.get("output")`)
- `sandboxd_client.py:304-423` (SSE/NDJSON event stream + normalize)
- `flowmanner.yaml:119-124` (plan emitted as fenced json in agent output)

---

## 4. Inputs schema for the plan-only blueprint

Mirror the existing `flowmanner.yaml` `inputs:` block (`flowmanner.yaml:30-52`).
A plan-only blueprint should expose:

| Input | Type | Default | Purpose |
|-------|------|---------|---------|
| `repo_url` | string | `https://github.com/glennguilloux/FlowmannerV2.git` | Repo to clone + analyze. Rendered into `task_prompt` via `${repo_url:-...}` (`flowmanner.yaml:31-33, 75`). |
| `prior_plan_url` | string | `""` | Optional URL to a previous PLAN for drift reconciliation. Mapped to the existing `prior_clues_url` input (`flowmanner.yaml:34-36, 95-98`). Rename to `prior_plan_url` for clarity; the task_prompt already supports "if non-empty, curl + reconcile" (`flowmanner.yaml:95-98`). |
| `scope` / `glob` | string | `"backend"` (or `""` = whole repo) | Limit analysis to a subtree/glob (e.g. `backend/app/services/substrate`). **New** — not in current `flowmanner.yaml`; add a `scope` input and interpolate it into STEP 2 grep/file globs (`flowmanner.yaml:84-92`) so the plan-only run stays focused and cheap. |
| `workdir` | string | `/workspace/repo` | Clone target inside the container (`flowmanner.yaml:37-39, 76-78`). |
| `model` | string | `""` | Sandbox agent model; `""` → sandboxd default (glm-5 free tier). Rendered via `{{ inputs.model }}` → `submit_task(model=...)` (`flowmanner.yaml:40-52`, `node_executor.py:2152-2165`, `2282`). |

All four existing inputs already flow through `context["inputs"]`, which
`_handle_sandbox_node` interpolates into both `task_prompt` (`{{ inputs.* }}`,
`node_executor.py:2260-2274`) and `model` (`node_executor.py:2153-2165`). Adding
`scope`/`glob` requires only: (a) a new `inputs:` entry in `flowmanner.yaml`, and
(b) referencing `${scope:-backend}` inside the task_prompt — no executor changes.

**Cite:**
- `flowmanner.yaml:30-52` (existing inputs block: repo_url, prior_clues_url,
  workdir, model)
- `flowmanner.yaml:75, 95-98` (repo_url / prior_clues_url usage in prompt)
- `node_executor.py:2153-2165` + `2260-2274` (inputs → model + task_prompt)

---

## 5. Substrate GAPs that could block a pure plan-only run

1. **Stale line references in `flowmanner.yaml` (DOC DRIFT, low risk).**
   The header claims sandbox-only-egress is proven at `node_executor.py:1485` and
   code/tool isolation at `node_executor.py:1285`. Those lines are actually:
   - `node_executor.py:1485` → inside `_emit_cost_event` (a `CostEvent`
     constructor), unrelated to sandbox/clone.
   - `node_executor.py:1285` → an `except Exception` handler in `_handle_llm`
     (failed-to-record-depth-event), unrelated to code/tool isolation.
   The real evidence is: sandbox dispatch `node_executor.py:1131-1132`;
   code-node no-network comment `node_executor.py:1682-1683`; egress only via
   sandboxd `node_executor.py:2125-2424`. **Fix the header comments** — the claim
   is correct, the line numbers are wrong.

2. **`agent` config key is a no-op for sandbox nodes (cosmetic).**
   `flowmanner.yaml:67` sets `agent: opencode`, but `_handle_sandbox_node` always
   hardcodes `agent="opencode"` (`node_executor.py:2281`) and never reads
   `config["agent"]`. Harmless for plan-only (opencode is what we want), but the
   config key misleads.

3. **`template` drift between backend default and playground/tests (moderate).**
   Backend default is `worker-standard` (`config.py:306`) and `flowmanner.yaml`
   uses it, but `playground_models.py:84-85`, `playground_service.py:36,218`,
   `playground.py:90`, and `test_mission_sandbox_integration.py:128` still assert
   / default to `python-img`. If someone "aligns" the blueprint to `python-img`
   to match the tests, they'd diverge from the actual default. **Keep
   `worker-standard`**; the `python-img` references are legacy drift, not the
   plan-only path.

4. **Executor does NOT force any mutation — confirmed NO hard block.**
   A sandbox node performs host-side writes *only* when `input_files` is
   non-empty (`node_executor.py:2238` guarded by `if input_files:`) or
   `snapshot_before` is true (`node_executor.py:2218` guarded by
   `if snapshot_before:`). Cloning and any `git commit`/`git push` happen
   *inside the agent's task_prompt*, not in the executor. Therefore a plan-only
   blueprint that:
   - sets `input_files: {}`, `snapshot_before: false`, `shared_workspace: false`,
   - writes a `task_prompt` that clones to `/tmp` (or uses injected `input_files`
     instead of cloning — see #5 below), analyzes, and prints JSON **without**
     committing/pushing,
   has **zero host side effects**. The two-phase STAGE→CONFIRM side-effect gate
   (`node_executor.py:695-794`) only engages for `effect_class == IRREVERSIBLE`
   nodes; `sandbox` defaults to `IRREVERSIBLE`
   (`workflow_models.py:164`), but the *committed intent* is just a substrate
   event log entry — it does not itself mutate the repo. The actual external
   effect (the sandboxd task) is still the agent's prompt behavior, which we
   constrain. If you want the node treated as read-only by the safety layer, set
   `effect_class: reversible` on the node (`workflow_models.py:53-54`) — but this
   is optional; it does not change whether the repo is touched.

5. **Can the sandbox be told to use injected `input_files` instead of cloning?**
   **Yes.** `input_files` (`node_executor.py:2150`, written at
   `node_executor.py:2238-2255`) lets the blueprint push repo contents (or a
   subtree) into the container as files, so the task_prompt can *skip the clone*
   entirely and just analyze the pre-staged files. This is the cleanest plan-only
   mode: no egress needed at runtime, fully deterministic, zero clone. Caveat:
   the blueprint must itself have the repo content to inject (the *orchestrator*
   building the blueprint needs egress to gather files; the sandbox node then
   doesn't). For a self-referential blueprint run from the homelab, the simpler
   path is to let the sandbox clone (`flowmanner.yaml:74-78`) — egress is
   available and the agent does the analysis. Both modes are supported; neither
   is forced.

**No substrate gap hard-blocks a pure plan-only run.** The only items are doc
drift (#1, #2, #3) and an optional design choice (#4 effect_class, #5
clone-vs-inject). All evidence is read from source at the cited lines.

---

## Bottom line for the plan-only blueprint author

- Use **one `sandbox` node**, `template: worker-standard`, `shared_workspace:
  false`, `snapshot_before: false`, `input_files: {}`.
- Put the analysis instructions + "print exactly one ```json plan``` block, never
  commit/push, never write outside /tmp" constraint in `task_prompt`.
- Expose `repo_url`, `prior_plan_url`, `scope`/`glob`, `workdir`, `model` as
  `inputs:` (mirror `flowmanner.yaml:30-52`).
- Read the plan from `node.output_data["agent_output"]`; parse the fenced json
  block. (Executor returns raw text — no auto-JSON.)
- Fix the three stale `node_executor.py` line refs in `flowmanner.yaml`'s header
  when you touch the file.
