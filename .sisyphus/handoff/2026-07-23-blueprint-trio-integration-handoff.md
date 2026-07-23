# Handoff — Blueprint Trio + CI + Integration Tests

**Date:** 2026-07-23
**Author:** Hermes coding agent (kanban-style worker slot)
**Scope:** Create three Flowmanner example blueprints, document them, wire CI validation, and add substrate-level integration tests.

> This handoff records exactly what was built, how it was verified, and what remains open for the next session. Do NOT re-derive context — it is all here.

---

## 1. Where things stand (summary)

| Deliverable | Status | Location | Verification |
|-------------|--------|----------|------------|
| `flowmanner-institutional-memory.yaml` | ✅ created | `backend/flowmanner-institutional-memory.yaml` | `flowmanner validate` passes |
| `flowmanner-rag-report.yaml` | ✅ created | `backend/flowmanner-rag-report.yaml` | `flowmanner validate` passes |
| `flowmanner-cache-warmer.yaml` | ✅ created | `backend/flowmanner-cache-warmer.yaml` | `flowmanner validate` + dry-run passes |
| Docs — running the blueprints | ✅ added | `backend/docs/README.md` | n/a (docs) |
| CI — validate blueprints on PR | ✅ added | `.github/workflows/ci.yml` | YAML syntax OK, local run of the same loop passes |
| Integration tests for the trio | ✅ added | `backend/tests/integration/test_blueprint_integration.py` | 3/3 tests passing |
| Push / deploy | ⛔ not done | — | awaiting user review |

---

## 2. Files touched

### Created
- `backend/flowmanner-institutional-memory.yaml` — `solo` strategy blueprint that accumulates knowledge across runs by reading prior Qdrant findings, performing a self-audit in a single sandbox node, and writing new findings back.
- `backend/flowmanner-rag-report.yaml` — `graph` strategy blueprint that retrieves context from a knowledge collection, synthesizes a structured report via LLM, validates the output schema, pauses for human review, and publishes via webhook.
- `backend/flowmanner-cache-warmer.yaml` — `dag` strategy blueprint that splits a list of expensive queries, fans out to check Redis cache freshness per query, recomputes on miss in a sandbox node, and logs a summary.
- `backend/tests/integration/test_blueprint_integration.py` — pytest integration tests for the three blueprints using the local substrate harness (in-memory `EventLog` / `ReplayEngine` and a fake `NodeExecutor`).

### Modified
- `backend/docs/README.md` — added a new section explaining how to run the three blueprints via the Flowmanner UI or API.
- `.github/workflows/ci.yml` — added a `validate-blueprints` job that builds the CLI from `cli/`, then runs `node cli/dist/index.js validate` on `backend/flowmanner.yaml` and `backend/flowmanner-*.yaml` on every PR and push to `main`.

---

## 3. Blueprint details

### 3.1 Institutional memory (`solo`)

**Strategy:** `solo`
**Inputs:**
- `repo_url` (default: `https://github.com/glennguilloux/FlowmannerV2.git`)
- `topic` (default: `"codebase health"`)

**Nodes:**
1. `recall` (`memory_read`) — reads prior findings from Qdrant (`flowmanner_memory` collection).
2. `analyze` (`sandbox`) — single node that does the full audit. The task prompt instructs the agent to:
   - Query the Qdrant REST API for the topic.
   - Run the standard self-audit signal-gathering (pytest, ruff, TODOs).
   - Incorporate prior findings and write new findings back to Qdrant via HTTP.
3. `persist` (`memory_write`) — structural node; the real memory write is done inside the sandbox via `curl` because `solo` only runs the first node.

**Known caveat:** Because `solo` strategy only executes the first node, the `memory_read` and `memory_write` nodes in the YAML are present for documentation/structure but do not execute. The sandbox node performs all Qdrant operations directly.

### 3.2 RAG report (`graph`)

**Strategy:** `graph`
**Inputs:**
- `topic` (required)
- `webhook_url` (default: `""`)

**Nodes:**
1. `retrieve` (`rag_query`)
2. `store_context` (`variable_set`)
3. `synthesize` (`llm_call`)
4. `store_report` (`variable_set`)
5. `validate` (`validate_schema`)
6. `review` (`human_review`)
7. `publish` (`webhook`)

**Edges:** linear flow with a conditional branch from `validate` to either `review` (when `route == "default"`) or back to `synthesize` (when `route == "on_invalid"`).

**Known caveat:** The current graph strategy does not handle back-edges / cycles in its topological sort. The integration test removes the `validate -> synthesize` on_invalid edge to make the workflow schedulable. The blueprint file retains the edge as the intended design; running it end-to-end requires either a graph-strategy fix or accepting that the retry cycle will not be scheduled.

### 3.3 Cache warmer (`dag`)

**Strategy:** `dag`
**Inputs:**
- `queries` (array of strings)
- `repo_url` (default: same as institutional memory)

**Nodes:**
1. `split_queries` (`split`) — fans the array out into one branch per item.
2. `fan_out` (`fan_out`)
3. `check_cache` (`cache_get`)
4. `recompute` (`sandbox`) — only runs on cache miss.
5. `fan_in` (`fan_in`)
6. `log_summary` (`log`)

**Verification:** A dedicated dry-run script at `/tmp/dry_run_cache_warmer.py` loaded the blueprint, converted it via `blueprint_to_workflow`, and executed it with a stubbed `NodeExecutor`. It confirmed the split node produced one `recompute` call per query and that `log_summary` ran after all per-item branches.

---

## 4. CI job

Added `validate-blueprints` to `.github/workflows/ci.yml`.

```yaml
  validate-blueprints:
    name: Validate Backend Blueprints
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: cli
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run build
      - run: |
          cd ..
          shopt -s nullglob
          for f in backend/flowmanner.yaml backend/flowmanner-*.yaml; do
            echo "Validating $f"
            node cli/dist/index.js validate "$f"
          done
```

**Local verification:**
```bash
cd /opt/flowmanner
for f in backend/flowmanner.yaml backend/flowmanner-*.yaml; do
  node cli/dist/index.js validate "$f"
done
```
All blueprints passed.

---

## 5. Integration tests

File: `backend/tests/integration/test_blueprint_integration.py`

### Approach
- Loads each blueprint YAML and converts it with `blueprint_to_workflow`.
- Executes with `UnifiedExecutor` using in-memory `EventLog` / `ReplayEngine`.
- Patches `NodeExecutor` to avoid real LLM, sandbox, webhook, or external service calls.
- Disables post-run hooks (`_run_post_hooks`) to avoid event-loop teardown issues in the test environment.

### Tests
1. `test_institutional_memory_blueprint_loads_and_runs` — verifies the solo sandbox node completes successfully.
2. `test_rag_report_blueprint_pauses_at_human_review` — verifies the graph runs through retrieve → variable_set → synthesize → variable_set → validate → human_review, and the run pauses/returns at the human_review node.
3. `test_cache_warmer_blueprint_splits_and_recomputes` — verifies the dag splits the default three queries and invokes the sandbox recomputation node once per query.

### Running
```bash
cd /opt/flowmanner/backend
APP_ENV=test FLOWMANNER_LEASE_ENABLED=false FLOWMANNER_CROSS_MISSION_MEMORY=false \
  .venv/bin/python -m pytest tests/integration/test_blueprint_integration.py -v --tb=short
```

Result at handoff: **3 passed**.

---

## 6. Known limitations and open threads

1. **RAG report on_invalid retry edge is not actually schedulable.** The blueprint declares `validate -> synthesize` for the invalid-schema case, but the graph strategy treats all edges as hard dependencies and cannot schedule a cycle. The integration test removes that edge. To fully realize the retry behavior, the graph strategy needs to support conditional back-edges or the blueprint needs to be redesigned without a cycle.

2. **Solo blueprint structural nodes do not run.** `memory_read` and `memory_write` nodes in the institutional-memory blueprint are present for documentation but are not executed because `solo` strategy only runs the first node. The sandbox node handles all Qdrant I/O directly.

3. **Fake NodeExecutor is a partial stub.** It mimics enough behavior for the tests to pass but does not exercise real `_handle_*` implementations, external APIs, or HITL interruption. It is intended as a substrate-level integration test, not an end-to-end service test.

4. **No deployment / push.** Nothing has been pushed or deployed. The user should review before merging.

---

## 7. Deliverable summary for the human

- ✅ Three example blueprints created and validated.
- ✅ Documentation added for running the blueprints.
- ✅ CI job added to validate all backend blueprints on PR.
- ✅ Integration tests added and passing for the three blueprints.
- ⛔ Not pushed or deployed — awaiting review.

**Decision for the human:** review the blueprints, the integration-test approach (especially the modified RAG-report graph used in tests), and either approve the work for merge or request scope changes.