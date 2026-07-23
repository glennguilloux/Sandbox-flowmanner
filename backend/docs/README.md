# Flowmanner Docs Index

## API & Integration
- [Swarm Debate Quick Start](./swarm-debate-quickstart.md) — `POST /api/swarm/protocol/debate` in 30 seconds (the most differentiated call)
- [Prompt Library](../../scripts/prompts/flowmanner-prompt-library.md) — Goal-driven templates for the swarm orchestration API
- [Architecture](./architecture.md) — System architecture overview

## Development
- [Sprint Plan S1](./sprint-plan-s1.md) | [Sprint Plan S2](./sprint-plan-s2.md)
- [Sprint Status](./sprint-status.yaml)

## Reports
- [Integration Seam Report](./INTEGRATION-SEAM-REPORT.md)
- [BMAD State](./02-bmad-state.md)

## Running the Example Blueprints

Three example blueprints live in the root of the `backend/` directory. They show the
`solo`, `graph`, and `dag` blueprint strategies and exercise memory, RAG, cache,
and human-review nodes.

| Blueprint | Strategy | File | Purpose |
|-----------|----------|------|---------|
| Institutional Memory | `solo` | [`../flowmanner-institutional-memory.yaml`](../flowmanner-institutional-memory.yaml) | Recall prior findings from Qdrant, audit the repo, and write new findings back. |
| RAG Report | `graph` | [`../flowmanner-rag-report.yaml`](../flowmanner-rag-report.yaml) | Retrieve context, synthesize a report with an LLM, validate it, wait for human review, then publish via webhook. |
| Cache Warmer | `dag` | [`../flowmanner-cache-warmer.yaml`](../flowmanner-cache-warmer.yaml) | Split a list of queries across parallel branches; each branch checks Redis, recomputes on miss, warms the cache, and a final log node emits a summary. |

### Submit a blueprint run

Blueprints are loaded from the YAML file and submitted through the missions API.
The exact endpoint depends on your local wiring, but the payload shape is generally:

```json
{
  "blueprint": "<yaml-content-or-blueprint-id>",
  "inputs": {
    "topic": "codebase health",
    "webhook_url": "https://example.com/webhook"
  }
}
```

### Blueprint-specific inputs

**Institutional Memory** (`flowmanner-institutional-memory.yaml`)

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `repo_url` | string | `https://github.com/glennguilloux/FlowmannerV2.git` | Repo to audit. |
| `topic` | string | `codebase health` | Topic to recall from and write to memory. |
| `workdir` | string | `/workspace/repo` | Clone/work directory inside the sandbox. |
| `model` | string | `""` | Optional model override for the sandbox agent. |

**RAG Report** (`flowmanner-rag-report.yaml`)

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `topic` | string | required | What the report is about. |
| `webhook_url` | string | `""` | URL to POST the approved report to. |

The `webhook_url` is only used if the report passes `validate_schema`, human review,
and reaches the `publish` node.

**Cache Warmer** (`flowmanner-cache-warmer.yaml`)

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `queries` | array | `["codebase summary", "API endpoint list", "test coverage report"]` | Queries to warm in parallel. |
| `repo_url` | string | `https://github.com/glennguilloux/FlowmannerV2.git` | Repo the sandbox clones to answer each query. |

### Important runtime notes

- **Qdrant** must be reachable from the sandbox for *Institutional Memory* reads/writes
  (`http://localhost:6333` is used by the task prompt).
- **RAG Report** will pause at the `human_review` node until a reviewer provides input.
  Provide a `webhook_url` if you want the approved report to be published automatically.
- **Cache Warmer** expects Redis at `10.0.4.5:6379` (hard-coded in the sandbox task prompt).
  Update the IP/port in the blueprint if your Redis instance differs.
  The `split` node injects the current query as `{{ input }}` into the
  immediate downstream sandbox; the per-item cache check, recompute, and Redis
  write all happen inside that sandbox.
- All three blueprints assume the sandbox can reach the public internet to clone the
  Flowmanner repo.
