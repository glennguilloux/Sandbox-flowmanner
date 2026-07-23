# TODO-02: Extend Blueprint Linter — Stricter Validation + More Node Types

## Objective

Extend the blueprint linter (`backend/scripts/lint_blueprints.py`) with two improvements:

1. **Stricter value validation** — currently the linter checks that required config keys are *present*, but doesn't validate that their values are non-empty / non-whitespace. A `split` node with `splitOn: ""` or `splitOn: "  "` would pass linting but crash at runtime.

2. **More node types in `REQUIRED_NODE_CONFIG`** — the linter currently only validates `split`, `merge`, `sandbox`, `llm_call`, and `variable_set`. Several other node types have required config keys that should be enforced:

   - `transform`: requires `transformType` (must be `"map"`, `"filter"`, or `"expression"`)
   - `condition`: requires `expression` (the boolean expression to evaluate)
   - `validate_schema`: requires `schema` (the JSON schema to validate against)
   - `memory_write`: requires `collection` (the Qdrant collection name)
   - `memory_read`: requires `query` (the search query)
   - `webhook`: requires `url` (the webhook URL)
   - `log`: requires `level` (info/warning/error) and `message`
   - `router`: requires `routes` (the routing configuration)
   - `delay`: requires `duration` (the delay in seconds)
   - `retry`: requires `max_retries` (the retry count)
   - `cache_get`: requires `key` (the cache key)

## Verified substrate facts (do NOT invent — these are from live source)

### Node config keys (node_executor.py handlers)
- `transform` (node_executor.py:2324-2351): `transformType` ∈ {"map", "filter", "expression"}, `transformExpression` (the expression to apply)
- `condition` (node_executor.py:2443-2477): `expression` (the boolean expression to evaluate via `_safe_eval`)
- `validate_schema` (node_executor.py:2376-2441): `schema` (JSON schema dict), `payload_key` (optional, default "payload")
- `memory_write` (node_executor.py:3030-3093): `collection` (Qdrant collection name), `text` (interpolated text), `payload` (static dict)
- `memory_read` (node_executor.py:2175-2245): `query` (search query), `collection` (optional, default "flowmanner_memory")
- `webhook` (node_executor.py:2754-2837): `url` (webhook URL), `method` (optional, default "POST")
- `log` (node_executor.py:2577-2635): `level` (info/warning/error), `message` (log message)
- `router` (node_executor.py:3150-3234): `routes` (list of route definitions), `input_key` (optional)
- `delay` (node_executor.py:3236-3273): `duration` (delay in seconds)
- `retry` (node_executor.py:2839-2893): `max_retries` (retry count)
- `cache_get` (node_executor.py:2895-3028): `key` (cache key), `default` (optional default value)

### Existing linter structure (backend/scripts/lint_blueprints.py)
- `REQUIRED_NODE_CONFIG` dict maps node type → list of required config specifiers
- Each specifier is either a string (key must be present) or a list of strings (at least one must be present)
- `validate_node_constraints(definition)` checks each node against `REQUIRED_NODE_CONFIG`
- `validate_blueprint(path, data)` runs top-level keys, node constraints, graph validation, and adapter conversion

### _safe_eval rules (node_executor.py:100-377) — for value validation
- `dict.get("key")` method syntax is BLOCKED (node_executor.py:268-278)
- Use the `get` builtin instead: `get(inputs, "key")`
- Subscript access works: `inputs["key"]`, `previous_outputs["node_id"]`

## Design

### 1. Stricter value validation

Add a new function `validate_node_config_values(definition: dict) -> list[str]` that checks:
- `split` nodes: `splitOn` must be a non-empty string (not just whitespace)
- `variable_set` nodes: `varName` must be a non-empty string (not just whitespace)
- `log` nodes: `level` must be one of "info", "warning", "error"; `message` must be non-empty
- `transform` nodes: `transformType` must be one of "map", "filter", "expression"
- `validate_schema` nodes: `schema` must be a dict (not a string or null)
- `webhook` nodes: `url` must be a non-empty string
- `delay` nodes: `duration` must be a positive number
- `retry` nodes: `max_retries` must be a positive integer
- `cache_get` nodes: `key` must be a non-empty string

### 2. Extended REQUIRED_NODE_CONFIG

Add entries for:
- `transform`: `["transformType", "transformExpression"]`
- `condition`: `["expression"]`
- `validate_schema`: `["schema"]`
- `memory_write`: `["collection"]`
- `memory_read`: `["query"]`
- `webhook`: `["url"]`
- `log`: `["level", "message"]`
- `router`: `["routes"]`
- `delay`: `["duration"]`
- `retry`: `["max_retries"]`
- `cache_get`: `["key"]`

### 3. Integration

- Call `validate_node_config_values` from `validate_blueprint` (after `validate_node_constraints`)
- Add unit tests for the new value validation in `backend/tests/test_lint_blueprints.py`
- Run `make lint-blueprints` to verify all existing blueprints still pass

## Constraints
- Product name: `flowmanner` (NO 'p', double-N — like "Glenn")
- Do NOT deploy, do NOT run `flowmanner push` — just modify the linter and tests
- After changes, run: `python3 -m pytest backend/tests/test_lint_blueprints.py -v`
- After changes, run: `make lint-blueprints` (from /opt/flowmanner)
- Do NOT use `dict.get()` in any YAML expression fields — use `get()` builtin
- The linter must NOT crash on unknown node types — they should be ignored
- The linter must NOT crash on missing `config` — treat as empty dict

## Files to modify
- `backend/scripts/lint_blueprints.py` — add value validation + extend REQUIRED_NODE_CONFIG
- `backend/tests/test_lint_blueprints.py` — add tests for value validation

## Reference files to read
- `backend/scripts/lint_blueprints.py` — the linter (already read)
- `backend/tests/test_lint_blueprints.py` — existing tests (already read)
- `backend/app/services/substrate/node_executor.py` — handler config keys (already read)
- `backend/flowmanner-ab-arena.yaml` — example with transform, variable_set, llm_eval, memory_write
- `backend/flowmanner-rag-report.yaml` — example with validate_schema, webhook, log
- `backend/flowmanner-cache-warmer.yaml` — example with split, sandbox, log
- `backend/flowmanner-multi-repo-audit.yaml` — example with split, merge, variable_set, llm_call, log
