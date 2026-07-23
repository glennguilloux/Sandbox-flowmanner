# Blueprint Linter

The blueprint linter validates Flowmanner blueprint YAML files before they reach
the substrate executor. It is used by `make lint-blueprints`, the
`lint-blueprints` pre-commit hook, and the GitHub Actions CI pipeline.

## Files

- `lint_blueprints.py` — the linter CLI
- `../tests/test_lint_blueprints.py` — unit tests

## Usage

```bash
# Lint all blueprints under backend/ and blueprints/
make lint-blueprints

# Lint a specific file or directory
python backend/scripts/lint_blueprints.py backend/flowmanner-example.yaml
```

**Exit codes:**

- `0` — all discovered blueprints passed validation.
- `1` — one or more blueprints failed validation, or a YAML parse error was
  encountered.

**Discovery:** when no explicit paths are given, the linter scans the
`backend/` and `blueprints/` directories. Common non-blueprint directories
such as `.git`, `docs`, `__pycache__`, and virtualenvs are skipped.

## What it checks

1. **YAML parsing** — the file must be valid YAML.
2. **Blueprint shape** — only YAML files containing both `blueprint_type` and
   `definition` are treated as blueprints.
3. **Required top-level keys** — `version`, `name`, `blueprint_type`,
   `definition`.
4. **Per-node required config keys** — every node must declare the keys
   required by its `type`.
5. **Per-node config value validation** — required values must be non-empty,
   valid enum values, positive numbers, etc.
6. **Graph validation** — `validate_blueprint_definition` checks nodes, edges,
   and connectivity.
7. **Adapter conversion** — `blueprint_to_workflow` verifies the blueprint can
   be converted into an runnable workflow.

## Required node configuration

| Node type        | Required config keys                              |
|------------------|---------------------------------------------------|
| `split`          | `splitOn`                                         |
| `merge`          | `mergeStrategy`                                   |
| `sandbox`        | `task_prompt`                                     |
| `llm_call`       | `prompt`                                          |
| `variable_set`   | `varName` AND (`varValue` OR `varExpr`)           |
| `transform`      | `transformType`, `transformExpression`            |
| `condition`      | `expression`                                      |
| `validate_schema`| `schema`                                          |
| `memory_write`   | `collection`                                      |
| `memory_read`    | `query`                                           |
| `webhook`        | `url`                                             |
| `log`            | `level`, `message`                                |
| `router`         | `routes`                                          |
| `delay`          | `delayMs`                                         |
| `retry`          | `maxRetries`                                      |
| `cache_get`      | `key`                                             |

Specifiers that list alternatives (e.g. `["varValue", "varExpr"]`) mean *at
least one* of the listed keys must be present.

## Value validation

The linter rejects empty or otherwise invalid values for the following node
types:

| Node type        | Validation rule                                           |
|------------------|-----------------------------------------------------------|
| `split`          | `splitOn` must be a non-empty string                      |
| `variable_set`   | `varName` must be a non-empty string                      |
| `log`            | `level` must be `info`, `warning`, or `error`; `message` must be non-empty |
| `transform`      | `transformType` must be `map`, `filter`, or `expression`   |
| `validate_schema`| `schema` must be a mapping (JSON schema object)           |
| `webhook`        | `url` must be a non-empty string                          |
| `delay`          | `delayMs` must be a positive number (milliseconds)      |
| `retry`          | `maxRetries` must be a positive integer                 |
| `cache_get`      | `key` must be a non-empty string                          |
| `condition`      | `expression` must be a non-empty string                   |
| `memory_write`   | `collection` must be a non-empty string                   |
| `memory_read`    | `query` must be a non-empty string                        |
| `router`         | `routes` must be a non-empty list                         |

Unknown node types are ignored and do not produce lint errors.

## CI / pre-commit integration

- `make lint-blueprints` is invoked by the `lint-blueprints` job in
  `.github/workflows/ci.yml`. The `backend` job depends on it, so a lint
  failure blocks the rest of the pipeline.
- `backend/.pre-commit-config.yaml` registers the `lint-blueprints` and
  `lint-blueprints-unit-tests` hooks. They run when blueprint YAML files or the
  linter itself change.

## Auto-fix mode

The linter can automatically correct a set of safe, common blueprint issues:

```bash
# Preview fixes without writing
python backend/scripts/lint_blueprints.py --fix --dry-run

# Apply fixes in place
python backend/scripts/lint_blueprints.py --fix
```

Applied corrections include:

* Renaming deprecated keys: `duration` → `delayMs`,
  `max_retries` → `maxRetries`.
* Adding sensible defaults for optional keys:
  `log.level`, `log.message`, `merge.mergeStrategy`, `split.mode`,
  `webhook.method`, `memory_read.collection`,
  `validate_schema.payload_key`, `file_operation.operation`.
* Trimming leading/trailing whitespace on structural strings.
* Ensuring `definition.nodes` and `definition.edges` exist.

`--fix` re-validates the blueprint after applying corrections. If any
unfixable errors remain, the file is left untouched and the linter exits
with code `1`.

## Adding a new node type

To extend the linter for a new node type:

1. Add the node type and required config keys to `REQUIRED_NODE_CONFIG` in
   `lint_blueprints.py`.
2. If the node has values that need extra validation, add a branch to
   `validate_node_config_values`.
3. Add unit tests to `../tests/test_lint_blueprints.py`.
4. Run `make lint-blueprints` and the unit tests to verify.
