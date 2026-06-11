# FlowManner Agent Handoff Index

**Start here before any serious FlowManner backend work.**

## 1. Immediate pre-work

Run these first and paste the output into the session notes or handoff:

```bash
git status --short && git branch --show-current && git rev-parse --short HEAD
```

Then read:

1. `AGENTS.md`
2. `docs/REBUILD-ROADMAP.md`
3. `Docs/agent-handoff/DEEP-DIVE-PLAYBOOK.md`
4. The matching topic dossier in `Docs/agent-handoff/topics/`

## 2. Which dossier should I read?

| Work type | Dossier |
|---|---|
| General orientation | `topics/00-system-map.md` |
| Agent runtime, domain agents, tool registry, capabilities | `topics/01-agent-runtime.md` |
| Mission execution, substrate, Blueprint+Run, CQRS | `topics/02-execution-substrate.md` |
| Auth, scopes, API keys, workspaces, v3 | `topics/03-auth-workspaces.md` |
| Data model, migrations, transactions, indexing | `topics/04-data-model-migrations.md` |
| Sandbox/code execution/chat IO | `topics/05-sandbox-code-execution.md` |
| Marketplace, plugins, SDK, artifacts | `topics/06-marketplace-plugins.md` |
| Observability, CI, tests, deployment | `topics/07-observability-ci.md` |
| Frontend dashboard, routes, stores, API clients | `topics/08-frontend-dashboard.md` |
| LLM routing, RAG, memory, evaluation | `topics/09-llm-rag-memory.md` |

If a dossier does not exist yet, create it from `topics/_TEMPLATE.md` and mark it `Draft` until verified.

## 3. Current deep-dive backlog

See `ACTIVE-WORK.md`. It is the lightweight status board for what is grounded, ready, or still needs investigation.

## 4. Handoff artifacts

| Artifact | When to use |
|---|---|
| `TOPIC-DOSSIER-TEMPLATE.md` | For a backend/domain/infrastructure area. |
| `FEATURE-DEEP-DIVE-TEMPLATE.md` | For a user-facing feature spanning UI/API/data. |
| `SESSION-HANDOFF-TEMPLATE.md` | At end of session when work is incomplete. |
| `SESSION-RITUAL.md` | At end of any session that changed files. |

## 5. Verification-first rule

Before changing code, every dossier should answer:

- What files/routes/models are actually present now?
- What existing tests cover this area?
- What is the exact request/response path?
- What is the current status: broken, partial, complete, or unknown?
- What command proves the next step is safe?
