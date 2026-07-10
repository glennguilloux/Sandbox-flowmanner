# FlowManner Active Deep-Dive Work

This is the lightweight status board for serious backend work. Keep it under 200 lines. Move completed detail into topic dossiers or archives.

## Status board

| Area | Dossier | Status | Why it matters | Next grounding step |
|---|---|---|---|---|
| Future backend architecture | `docs/future-architecture/README.md` | Decision-ready; implementation phased | 5–10 year architecture target for agent-native workflows, durable execution, memory, providers, and deployment. | Use as design reference before major backend refactor; finish active rebuild gates before Phase 4 event backbone work. |
| Agent runtime | `topics/01-agent-runtime.md` | Draft | Agents, domain agents, tools, capabilities, and registry behavior drive the product. | Verify current `agent_service.py`, `agent_registry_service.py`, `domain_agents/*`, `tools/*`, and tests. |
| Execution substrate | `topics/02-execution-substrate.md` | Draft | Mission, graph, workflow, Blueprint+Run, and substrate paths overlap and must not be changed blindly. | Trace v1 mission CQRS, v2 Blueprint+Run CQRS, `services/substrate/*`, and tests. |
| Auth and workspaces | `topics/03-auth-workspaces.md` | Draft | Workspace scope, API keys, v3 cookies, and role checks are security-sensitive. | Verify v3 auth routes, middleware, `UserAPIKey`, workspace dependencies, and tests. |
| Data model and migrations | `topics/04-data-model-migrations.md` | Draft | Model changes require migrations in the same commit; overlapping concepts can cause duplicate writes. | Inventory `__tablename__`, Alembic head, and overlapping execution tables. |
| Sandbox and code execution | `topics/05-sandbox-code-execution.md` | Draft | Chat code execution and sandbox preview are user-facing and deployment-sensitive. | Trace `/api/chat/code/execute`, sandbox preview auth, sandbox service, and tests. |
| Marketplace and plugins | `topics/06-marketplace-plugins.md` | Draft | Marketplace listings, plugins, SDK, and artifact installs need API/storage consistency. | Verify `marketplace.py`, plugin runtime, SDK files, and marketplace tests. |
| Observability and CI | `topics/07-observability-ci.md` | Draft | Tests, tracing, Sentry, Jaeger, and CI gates determine whether backend work is safe to merge. | Check tests, workflows, health endpoints, tracing, and deploy runbook. |
| Frontend dashboard | `topics/08-frontend-dashboard.md` | Draft | Dashboard routes, API clients, stores, and auth state affect every backend API change. | Inspect route tree, generated SDK calls, Zustand stores, and broken-page reports. |
| LLM, RAG, memory, eval | `topics/09-llm-rag-memory.md` | Draft | Model routing, RAG, memory, and evaluation affect agent quality and cost. | Verify model router, RAG services, memory services, eval runner, and Qdrant usage. |

## Working rules

1. A topic is `Ready` only after the dossier has current file paths, API contracts, tests, and next safe action.
2. A topic is `Draft` until at least one live source inspection has been recorded.
3. If a topic touches production, deployment, auth, money, or data migrations, require a second verification pass before code changes.
4. Do not start a new feature deep-dive while an active topic is half-grounded unless the user explicitly changes priority.
