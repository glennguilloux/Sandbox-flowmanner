# TODO-01: Pattern B Multi-Repo Audit Blueprint (split → merge)

## Objective

Rewrite the Pattern A single-sandbox multi-repo audit (from `/tmp/bp15.yaml`, which
used one sandbox node that looped internally) into a **Pattern B DAG blueprint**
that uses TRUE node-level parallelism via the now-fixed `split → merge` substrate
path. The fix (`substrate_split_merge_aggregation_defect`, RESOLVED 2026-07-23)
ensures `merge` collects ALL per-item outputs, not just the last one.

## Deliverable

A new blueprint YAML at:
  `/opt/flowmanner/backend/flowmanner-multi-repo-audit.yaml`

## Verified substrate facts (do NOT invent — these are from live source)

### Node types available (workflow_models.py:57-93)
- `split` — fans a collection out into one branch per item at runtime
- `sandbox` — the ONLY egress-capable node type (node_executor.py:1485)
- `merge` — synchronization/join point (node_executor.py:3275)
- `llm_call` — LLM node (node_executor.py:819)
- `log` — read-only substrate event append (node_executor.py:2577)
- `variable_set` — writes to context["inputs"] (node_executor.py:2625)

### split node config (node_executor.py:2479-2574)
- `splitOn`: dotted path into context. Use `"inputs.repos"` to split a blueprint
  input array directly. The handler resolves `inputs.<key>` from
  `context["inputs"]` (the run-scoped inputs dict).
- `mode`: `"item"` (default) — one branch per collection element.
- Returns `{"items": [...], "count": N, "empty": bool}`.

### DAG strategy split fan-out (dag.py:409-493)
- `_run_split_branches` executes each immediate downstream target ONCE PER ITEM.
- Per-item outputs are collected via `_append_split_output()` which wraps them in
  `{SPLIT_AGGREGATE_MARKER: True, "items": [...]}` (dag.py:392-407).
- Each per-item branch receives the item as `context["input"]`.

### merge node config (node_executor.py:3275-3349)
- `mergeStrategy`: `"concat"` (default) or `"merge_dict"`.
- `"concat"`: concatenates list/iterable outputs into a list.
- `"merge_dict"`: deep-merges dict outputs into one dict.
- Detects the `SPLIT_AGGREGATE_MARKER` and flattens ALL per-item outputs
  (node_executor.py:3307-3320). This is the fix — before, only the last item
  survived.

### sandbox node config (node_executor.py:1503-1511)
- `task_prompt` (required): the shell script / instructions.
- `template`: `"python-img"` (default) or `"worker-standard"`.
- `agent`: `"opencode"` (the coding agent inside the sandbox).
- `model`: `"{{ inputs.model }}"` — per-run model override (node_executor.py:2152).
- `shared_workspace`: bool (default False).
- `snapshot_before`: bool (default False).
- The sandboxd-base image ships `git` (verified: `which git` → `/usr/bin/git`).
- `task_prompt` is rendered with `re.sub` for `{{ inputs.* }}` tokens
  (node_executor.py:1591-1600). Uses `re.sub`, NOT `str.format` (the sandbox
  wrapper carries literal `{}` braces).

### variable_set node config (node_executor.py:2625-2690)
- `varName`: the variable name to write.
- `varExpr`: a Python expression evaluated via `_safe_eval` (AST whitelist).
- Writes the result into `context["inputs"][varName]`.
- Downstream nodes resolve it via `{{ inputs.varName }}` in their prompts.

### llm_call node config (node_executor.py:819-1001)
- `prompt`: the LLM prompt (interpolated with `{{ inputs.* }}`).
- `system_prompt`: optional system prompt.
- `temperature`: default 0.7.
- `max_tokens`: default 2000.
- Output → `output.text`.

### log node config (node_executor.py:2577-2635)
- `level`: `"info"` (default), `"warning"`, `"error"`.
- `message`: the log message (interpolated with `{{ inputs.* }}`).

### _safe_eval rules (node_executor.py:100-377) — CRITICAL
- `dict.get("key")` method syntax is BLOCKED (node_executor.py:268-278).
  The error: "dict attribute access not allowed: .get"
- Use the `get` builtin instead: `get(inputs, "key")`.
- Subscript access works: `inputs["key"]`, `previous_outputs["node_id"]`.
- Available builtins: len, min, max, sum, abs, round, sorted, list, dict, set,
  tuple, bool, int, float, str, any, all, enumerate, range, zip, map, filter,
  isinstance, get.
- NO imports, NO lambdas, NO attribute chains into arbitrary objects.

### Blueprint YAML schema (cli/templates/solo.yaml + blueprint.py)
Top-level: `version`, `name`, `description`, `blueprint_type` (solo|dag|graph|...),
`inputs` (dict of {key: {type, default}}), `definition` (with `blueprint_type`,
`nodes[]`, `edges[]`, `budget`, `config`).

Node schema: `id`, `type`, `title`, `description`, `config` (dict),
`dependencies` (list of node ids), `assigned_model`, `max_retries` (default 3),
`fallback_strategy` (default "human_escalate").

### Budget (capability_models.py)
`max_cost_usd`, `max_wall_time_seconds`, `max_iterations`, `max_depth`.

## Blueprint design

### blueprint_type: dag

### Inputs
- `repos`: array of repo URLs (default: 3 Flowmanner-related repos)
- `model`: string, default "" (sandboxd default)
- `workdir`: string, default "/workspace/repo"

### Nodes (DAG layers)

**Layer 0:**
- `split_repos` (type: split, splitOn: "inputs.repos")
  - Resolves the repos array from run-scoped inputs.
  - Fans out into one branch per repo.

**Layer 1 (per-item, parallel):**
- `audit_repo` (type: sandbox, agent: opencode, model: "{{ inputs.model }}")
  - Per-item: receives the repo URL as `{{ input }}` (injected by split fan-out).
  - Clones the repo, runs `pytest --co -q | tail -3`, `ruff check . | tail -5`,
    `grep -rnE '\b(TODO|FIXME|HACK|XXX)\b' backend --include=*.py | head -20`.
  - Outputs a JSON object: `{"repo": "<url>", "tests": "...", "lint": "...", "debt": "..."}`.
  - The sandbox agent must print exactly one fenced json block.

**Layer 2 (after all split items complete):**
- `merge_results` (type: merge, mergeStrategy: "concat")
  - Collects ALL per-item outputs from `audit_repo` (the fix ensures this).
  - Produces a list of audit result dicts.

**Layer 3:**
- `rank_findings` (type: llm_call)
  - Prompt references `{{ inputs.merge_results }}` — BUT wait, the merge node's
    output goes into `node_outputs["merge_results"]["merged"]`, not into
    `context["inputs"]`. We need a `variable_set` bridge.
- `set_merged` (type: variable_set)
  - `varName`: "merged_results"
  - `varExpr`: `previous_outputs["merge_results"]["merged"]`
  - Bridges the merge output into `context["inputs"]["merged_results"]`.

**Layer 4:**
- `rank_findings` (type: llm_call)
  - Prompt: "You are a code health analyst. Rank the following repo audit results
    by severity of issues found. Output a JSON array of {repo, severity, summary}.
    Results: {{ inputs.merged_results }}"
  - `temperature`: 0.3

**Layer 5:**
- `log_summary` (type: log)
  - `level`: "info"
  - `message`: "Multi-repo audit complete. Ranked {{ inputs.repos }} repos."

### Edges
- split_repos → audit_repo
- audit_repo → merge_results
- merge_results → set_merged
- set_merged → rank_findings
- rank_findings → log_summary

### Budget
- max_cost_usd: 5.00
- max_wall_time_seconds: 900
- max_iterations: 50
- max_depth: 3

## Constraints
- Use `blueprint_type: dag` (not graph — DAG has the split/merge fan-out).
- Product name: `flowmanner` (NO 'p', double-N — like "Glenn").
- Do NOT deploy, do NOT run `flowmanner push` — just create the YAML file.
- After creating, validate: `python3 -c "import yaml; yaml.safe_load(open('<path>'))"`.
- Do NOT use `dict.get()` in any varExpr/transformExpression — use `get()` builtin.
- The sandbox `task_prompt` must use `{{ input }}` for the per-item repo URL
  (injected by the split fan-out as `context["input"]`).
- The sandbox `task_prompt` must use `{{ inputs.model }}` and `{{ inputs.workdir }}`
  for run-scoped inputs.
- The sandbox `task_prompt` must print exactly one fenced json block — no prose.
- Use `template: python-img` (the default, verified working).
- Do NOT use `type: agent` — it's not a valid node type. Use `type: sandbox`.

## Verification steps (run after creating the YAML)
1. `python3 -c "import yaml; d=yaml.safe_load(open('/opt/flowmanner/backend/flowmanner-multi-repo-audit.yaml')); print('OK:', d['name'], d['blueprint_type'], len(d['definition']['nodes']), 'nodes')"`
2. `grep -n '\.get(' /opt/flowmanner/backend/flowmanner-multi-repo-audit.yaml` — must return ZERO matches.
3. `grep -n 'type: agent' /opt/flowmanner/backend/flowmanner-multi-repo-audit.yaml` — must return ZERO matches.
4. Verify the DAG topology has no cycles (the edges form a clean DAG).
5. Check that `splitOn` is `"inputs.repos"` (not `"input.repos"`).
6. Check that `mergeStrategy` is `"concat"` on the merge node.
7. Check that `variable_set` uses `varExpr` with subscript access, not `.get()`.

## Reference files to read
- `/opt/flowmanner/backend/flowmanner-cache-warmer.yaml` — the existing split-based DAG (Pattern A, no merge).
- `/opt/flowmanner/backend/flowmanner.yaml` — the self-audit blueprint (sandbox node pattern).
- `/opt/flowmanner/blueprints/web-recon.yaml` — graph blueprint with variable_set bridge pattern.
- `/opt/flowmanner/backend/app/services/substrate/workflow_models.py` — NodeType enum.
- `/opt/flowmanner/backend/app/services/substrate/node_executor.py` — handler config keys.
- `/opt/flowmanner/backend/tests/test_split_merge_aggregation.py` — the regression tests for the fix.
- `/opt/flowmanner/backend/tests/integration/test_blueprint_integration.py` — integration test patterns.
