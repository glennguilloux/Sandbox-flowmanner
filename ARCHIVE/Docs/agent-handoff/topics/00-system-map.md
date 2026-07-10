# 00 — FlowManner System Map

**Status:** Ready
**Last grounded:** 2026-06-11
**Purpose:** Fast orientation for agents entering FlowManner before a backend or feature deep-dive.

## 1. Machine topology

| Machine | Role | Source/deploy notes |
|---|---|---|
| Homelab | Backend, databases, LLM inference | Canonical source edits happen here. |
| VPS | Frontend, Nginx, SSL | Deployment target only; never edit directly. |
| Ops/Dev | Deploy trigger and development work | Uses repo docs and deploy scripts. |

Network flow:

```text
Internet → VPS Nginx :443 → frontend:3000
                         → /api/* → WireGuard → Homelab backend:8000
                         → /api/auth/* → frontend NextAuth
                         → /ws → WireGuard → Homelab WebSocket
```

## 2. Canonical docs

| Doc | Use |
|---|---|
| `Docs/FLOWMANNER-COMPLETE-SPEC-FOR-GPT.md` | Full AI-readable system spec. |
| `Docs/FLOWMANNER-CANONICAL-KNOWLEDGE.md` | Concepts, entities, relationships, principles. |
| `Docs/FLOWMANNER-ROADMAP.md` | Roadmap and phase gates. |
| `docs/REBUILD-ROADMAP.md` | Current rebuild state and stop gates. |
| `Docs/ARCHITECTURE-CONTEXT-WINDOW-SURVIVAL-GUIDE.md` | Architecture audit recovery notes. |
| `SESSION-RITUAL.md` | Exit audit and commit/push ritual. |

## 3. Backend mental model

FlowManner is not just a chatbot. It has multiple overlapping execution concepts:

| Concept | Where to look | Notes |
|---|---|---|
| Mission | `backend/app/models/mission_models.py`, `backend/app/api/_mission_cqrs/` | Legacy decomposable work unit. |
| Workflow/Graph | `backend/app/models/graph.py`, `backend/app/models/workflow_version_models.py` | Visual workflow/graph execution. |
| Swarm | `backend/app/models/swarm.py`, `backend/app/models/swarm_models.py` | Swarm/orchestrator concepts. |
| Substrate | `backend/app/services/substrate/` | Event-sourced unified execution layer. |
| Blueprint+Run | `backend/app/services/blueprint_service.py`, `backend/app/services/run_service.py`, `backend/app/api/v2/blueprints.py`, `backend/app/api/v2/runs.py` | Newer unified model being phased in. |

Important: treat overlaps as transition state. Do not assume one concept has fully replaced another unless current source confirms it.

## 4. API versions

| Version | Prefix | Role |
|---|---|---|
| v1 | `/api/*` | Legacy broad feature surface. |
| v2 | `/api/v2/*` | Cleaner next-gen API with envelope, Blueprint+Run, GraphQL, regression endpoints. |
| v3 | `/api/v3/*` | Workspace-scoped auth/scope API. |

## 5. High-value deep-dive order for backend work

1. Agent runtime and tool/capability registry.
2. Mission/substrate/Blueprint+Run execution path.
3. Auth, workspace scope, and API keys.
4. Data model and migrations.
5. Sandbox/code execution.
6. Marketplace/plugins.
7. Observability, CI, and deployment gates.

## 6. Non-negotiables

- Never edit VPS source.
- Never claim verification without command output.
- Model changes and migrations must stay in the same commit.
- Do not deploy during deep-dive; deploy only after review unless explicitly asked.
