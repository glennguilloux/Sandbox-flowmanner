# Substrate Node Type Reference

This page documents the node types supported by the unified substrate executor
(`backend/app/services/substrate/node_executor.py`). Each node type maps to a
handler that executes a discrete step in a workflow.

## Conventions

- `node.config` is a flat dict of key/value pairs supplied by the blueprint.
- Optional keys show their default in parentheses if they have one.
- Node outputs are returned under the node's runtime `output_data` field.

## Node categories

| Category              | Node types                                                                 |
|-----------------------|------------------------------------------------------------------------------|
| LLM & reasoning       | `llm_call`, `llm_eval`                                                       |
| Tools & code          | `tool_call`, `code_execution`                                                |
| Data & memory         | `rag_query`, `memory_read`, `memory_write`, `cache_get`, `file_operation`     |
| Control flow          | `condition`, `router`, `split`, `merge`, `delay`, `retry`, `timeout`, `loop` |
| Data transform        | `transform`, `filter`, `template_render`, `variable_set`, `validate_schema` |
| External              | `webhook`, `web_search`, `sandbox`                                           |
| Browser               | `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_scroll`, `browser_screenshot`, `browser_close` |
| Human in the loop     | `approval`, `human_review`                                                   |
| Meta                  | `guardrail`, `sub_workflow`, `phase_gate`, `fan_out`, `fan_in`              |

## LLM & reasoning

### `llm_call`

Calls a budgeted LLM through `BudgetEnforcer.call`.

| Config key      | Required? | Description                                          |
|-----------------|-----------|------------------------------------------------------|
| `prompt`        | Yes       | User prompt text (or rendered template)              |
| `system_prompt` | No        | Optional system prompt                               |
| `temperature`   | No (0.7)  | Sampling temperature                                 |
| `max_tokens`    | No (2000) | Maximum tokens in the response                       |
| `long_context`  | No        | If `true`, uses the run-scoped `ContextManager`     |
| `context_query` | No        | Query for long-context assembly                      |
| `context_token_budget` | No | Token budget for long-context assembly        |

**Output:** `{ "text": "<model response>" }`

### `llm_eval`

LLM-as-judge. Reuses the `_handle_llm` path with a judge prompt and an output
schema of `{ score, rationale }`.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `prompt`   | Yes       | Judge prompt |

## Tools & code

### `tool_call`

Invokes a capability tool.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `tool_name` or `tool_id` | Yes | Tool identifier |
| `params`   | No ({})   | Tool input parameters |

### `code_execution`

Executes Python code in a sandbox.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `code`     | Yes       | Python code to execute. Falls back to `context["code"]` |

## Data & memory

### `rag_query`

Queries a Qdrant collection.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `query`    | Yes       | Query text |
| `collection` | No ("default") | Qdrant collection name |

### `memory_read`

Reads from the shared memory collection.

| Config key       | Required? | Description |
|------------------|-----------|-------------|
| `query`          | Yes       | Search query |
| `collection`     | No ("flowmanner_memory") | Collection name |
| `topK`           | No (5)    | Number of results |
| `scoreThreshold` | No        | Minimum similarity score |

### `memory_write`

Upserts a payload into the shared memory collection.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `collection` | Yes     | Collection name |
| `text`     | No        | Interpolated text to embed and store |
| `payload`  | No        | Static payload dict |

### `cache_get`

Redis read-through cache lookup.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `key`      | Yes       | Cache key |
| `default`  | No        | Default value if key is absent |
| `modelId`  | No        | Model identifier used when cache miss requires LLM |
| `prompt` or `promptTemplate` | No | Prompt used when cache miss requires LLM |
| `params`   | No ({})   | Additional parameters |

### `file_operation`

Performs a file operation.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `operation` | No ("read") | Operation type |
| `file_id`  | No        | File identifier |

## Control flow

### `condition`

Evaluates a boolean expression and reports the branch; the strategy takes the
matching outgoing edge.

| Config key  | Required? | Description |
|-------------|-----------|-------------|
| `expression`| Yes       | Boolean expression evaluated via `_safe_eval` |

### `router`

Deterministic multi-branch classifier. Emits `branch == <routeId>` so the
strategy takes the matching edge.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `routes`   | Yes       | Non-empty list of route definitions |
| `input_key`| No        | Key in inputs to route on |

### `split`

Fans a collection out into one branch per item.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `splitOn`  | Yes       | Expression resolving to the collection |
| `mode`     | No ("item") | Split mode |

### `merge`

Synchronization / join point. Combines upstream outputs per `mergeStrategy`.

| Config key    | Required? | Description |
|---------------|-----------|-------------|
| `mergeStrategy` | Yes     | Strategy for combining upstream outputs |

### `delay`

Hard wall-clock pause, then passes through on branch `default`.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `delayMs`  | Yes       | Delay in milliseconds |

### `retry`

Reliability wrapper that sets/overrides `max_retries` and backoff for a
wrapped child.

| Config key   | Required? | Description |
|--------------|-----------|-------------|
| `maxRetries` | Yes       | Maximum retry count |
| `backoffMs`  | No        | Backoff between retries |

### `timeout`

Deadline wrapper around a single wrapped child node.

| Config key     | Required? | Description |
|----------------|-----------|-------------|
| `timeoutMs`    | Yes       | Deadline in milliseconds |
| `wrapped_node_id` | Yes    | ID of the wrapped child node |

### `loop`

Bounded iteration marker; the strategy drives the actual loop.

| Config key      | Required? | Description |
|-----------------|-----------|-------------|
| `max_iterations`| No (10)   | Maximum loop iterations |
| `stop_condition`| No        | Boolean expression to stop early |
| `loop_var`      | No ("i")  | Loop variable name |

## Data transform

### `transform`

Pure data transform using a whitelisted expression evaluator.

| Config key        | Required? | Description |
|-------------------|-----------|-------------|
| `transformType`   | Yes       | `map`, `filter`, or `expression` |
| `transformExpression` | Yes   | Expression to apply |

### `filter`

Same as `transform` with `transformType` forced to `filter`. Keeps collection
items whose predicate is truthy.

### `template_render`

Renders a `{{ inputs.* }}` template to a string.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `template` | Yes       | Template string with Mustache-style tokens |

### `variable_set`

Writes a named value into the run-scoped inputs dict.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `varName`  | Yes       | Variable name to set |
| `varValue` or `varExpr` | Yes | Static value or expression |
| `prefix`   | No        | Optional prefix applied to the variable name |

### `validate_schema`

Asserts a payload against a JSON schema.

| Config key  | Required? | Description |
|-------------|-----------|-------------|
| `schema`    | Yes       | JSON schema dict |
| `payload_key` | No ("payload") | Key in context containing the payload |

## External

### `webhook`

Outbound HTTP POST with SSRF guard.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `url`      | Yes       | Webhook URL |
| `method`   | No ("POST") | HTTP method |
| `headers`  | No        | Dict of extra headers |
| `params`   | No        | Request body / params |

### `web_search`

Performs a web search.

| Config key | Required? | Description |
|------------|-----------|-------------|
| `query`    | Yes       | Search query |

### `sandbox`

Executes a sandboxed Docker container.

| Config key  | Required? | Description |
|-------------|-----------|-------------|
| `task_prompt`| Yes      | Task/prompt for the sandbox |
| `template`  | No        | Sandbox image template |

## Browser nodes

Browser nodes operate a headless browser. They share common config keys.

| Node type           | Common config | Description |
|---------------------|---------------|-------------|
| `browser_navigate`  | `url`         | Navigate to URL |
| `browser_snapshot`  | —             | Capture DOM snapshot |
| `browser_click`     | `selector`    | Click an element |
| `browser_type`      | `selector`, `text` | Type text into an element |
| `browser_scroll`    | `selector` or direction | Scroll the page |
| `browser_screenshot`| —             | Take a screenshot |
| `browser_close`     | —             | Close the browser |

## Human in the loop

### `approval`

Approval interrupt. Pauses the run until a human approves.

| Config key      | Required? | Description |
|-----------------|-----------|-------------|
| `approval_prompt`| No       | Prompt shown to the approver |
| `description`   | No        | Longer description of the approval request |

### `human_review`

Clarification/review interrupt.

| Config key      | Required? | Description |
|-----------------|-----------|-------------|
| `approval_prompt`| No       | Prompt shown to the reviewer |
| `description`   | No        | Longer description |

## Meta

### `guardrail`

Pre/post content safety check. Runs regex patterns first; optionally runs an
LLM classifier.

| Config key      | Required? | Description |
|-----------------|-----------|-------------|
| `guardrailMode` | No ("both") | `pre`, `post`, or `both` |
| `patterns`      | No ([])   | List of regex patterns to scan |
| `onViolation`   | No ("block") | `block`, `redact`, `route_to_fallback` |
| `redactWith`    | No ("[REDACTED]") | Replacement token when redacting |
| `useClassifier` | No (false)| Run LLM classifier after regex |
| `classifierPrompt` | No   | Classifier instruction |
| `input`         | No        | Text to scan; defaults to upstream output |

### `sub_workflow`

Recursively executes another workflow.

| Config key  | Required? | Description |
|-------------|-----------|-------------|
| `workflow_id`| Yes      | ID of the sub-workflow to run |

### `phase_gate`, `fan_out`, `fan_in`

Passthrough nodes handled by the strategy.

| Node type   | Description |
|-------------|-------------|
| `phase_gate`| Pipeline phase boundary |
| `fan_out`   | Swarm decomposition marker |
| `fan_in`    | Swarm synthesis marker |

## Effect class and side-effect safety

Every node has an default `effect_class` of `irreversible`. Read-only nodes
(LLM, RAG, code, web search, file read, HITL, guardrail, transform, log,
memory read, cache read, validate_schema) should be annotated `reversible` by
the planner/adapter so the two-phase `STAGE → CONFIRM` dispatch is skipped.

## Adding a new node type

1. Add the node type to `NodeType` in
   `backend/app/services/substrate/workflow_models.py`.
2. Implement `_handle_<new_type>` in `node_executor.py`.
3. Wire the dispatch case in `NodeExecutor._dispatch`.
4. Add required config keys to `REQUIRED_NODE_CONFIG` in
   `backend/scripts/lint_blueprints.py`.
5. Add value validation if needed in
   `backend/scripts/lint_blueprints.py`.
