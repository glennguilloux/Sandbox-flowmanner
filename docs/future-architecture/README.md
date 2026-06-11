# FlowManner Future-State Architecture

**Status:** Ready  
**Date:** 2026-06-11  
**Audience:** Product, architecture, backend, frontend, infra, and future AI agents.  
**Purpose:** Redesign FlowManner for the next 5–10 years as a durable, agent-native workflow orchestration platform without chasing trends.

## Grounding

This architecture is grounded in the current FlowManner repository and docs:

- `docs/REBUILD-ROADMAP.md` — current rebuild state, substrate status, Blueprint+Run migration, stop gates.
- `Docs/FLOWMANNER_ARCHITECTURAL_ANALYSIS.md` — existing philosophy, weaknesses, and V3 brainstorming.
- `Docs/FLOWMANNER-CANONICAL-KNOWLEDGE.md` — current concepts, API versions, data model, execution strategies, and hidden assumptions.
- `Docs/FLOWMANNER-ROADMAP.md` — production-to-V2/V3 roadmap and phase gates.
- `Docs/OPUS-BRAINSTORM-CONTEXT.md` — compact product and strategic context.
- `docs/HOMELAB-SERVICES-REFERENCE.md` — current homelab topology and services.
- `Docs/agent-handoff/README.md` and `Docs/agent-handoff/topics/00-system-map.md` — current agent handoff and system map.

## Document Map

| File | Purpose |
|---|---|
| `01-paradigm-evaluation.md` | Paradigm tradeoff matrix and adoption decision. |
| `02-architecture-diagrams.md` | High-level architecture, domain map, data flow, event flow, execution flow. |
| `03-domain-boundaries.md` | Domain boundaries, aggregates, APIs, ownership rules. |
| `04-execution-agent-runtime.md` | Durable execution engine and agent runtime design. |
| `05-knowledge-events-data.md` | Knowledge, event bus, data layer, AI provider abstraction. |
| `06-observability-deployment.md` | Observability and deployment architecture for self-hosted and SaaS. |
| `07-roadmap-risks-not-build.md` | Migration roadmap, 12/24-month plans, 5-year vision, risks, and what not to build. |
| `08-final-recommendation.md` | Final recommended architecture and non-negotiable principles. |

## Executive Summary

FlowManner should become a **modular monolith with an event-driven durable execution substrate**, not a premature microservice platform.

The recommended future state:

```text
Clients
  → API Gateway / Edge
  → FlowManner Control Plane
      → Auth, Workspace, Agent, Workflow, Execution, Knowledge, Tool, Billing, Observability modules
      → Event Outbox + NATS JetStream / RabbitMQ
      → Postgres transactional store + append-only event log
      → Qdrant semantic memory
      → Redis cache/session/rate-limit
      → Object storage for artifacts
  → Distributed Execution Plane
      → Workers claim leases, execute tasks, checkpoint progress, emit events
  → AI Provider Layer
      → OpenAI, Anthropic, Gemini, Ollama, llama.cpp, future providers
```

The core architectural bet is:

> Keep the backend logically unified, make execution event-sourced and resumable, and let the deployment topology scale horizontally when needed.

This preserves FlowManner's current moat: sovereign deployment, local inference, agent marketplace potential, workflow replay, cost attribution, and operational control.

## How to Use This Architecture

1. Read `01-paradigm-evaluation.md` before debating architecture style.
2. Read `02-architecture-diagrams.md` for the complete system shape.
3. Read `04-execution-agent-runtime.md` before changing execution or agent runtime code.
4. Read `05-knowledge-events-data.md` before changing memory, events, storage, or AI provider routing.
5. Read `07-roadmap-risks-not-build.md` before planning migrations or product scope.
6. Read `08-final-recommendation.md` for the final decision and principles.
