# 08 — Final Recommended Architecture

## Final Recommendation

Adopt the architecture pack in `docs/future-architecture/01-paradigm-evaluation.md` through `07-roadmap-risks-not-build.md` as the final direction for FlowManner's V3 target.

This is **implementation-ready as a phased decision record**, not a claim that implementation is complete. The target is a modular monolith backend with an event-driven durable execution substrate, stateless distributed workers, first-class agent runtime boundaries, workspace-scoped knowledge, provider abstraction, observability by default, and deployment paths that are self-hosted-first but SaaS-ready later.

```text
Modular Monolith Backend
+ Event-Driven Durable Execution Substrate
+ Stateless Distributed Workers
+ Agent Runtime with Memory and Tool Boundaries
+ Knowledge Layer over Qdrant + Event-Derived Memory
+ Provider Abstraction for Cloud, Local, and Future AI Runtimes
+ Observability and Replay by Default
+ Self-Hosted Docker Compose Baseline
+ Optional SaaS Packaging After Core Durability Is Proven
```

## Final Architecture Pack

The final pack is the combined decision from `01` through `07`:

| Pack section | Final stance |
|---|---|
| `01-paradigm-evaluation.md` | Modular monolith first; event-driven execution where durability and replay matter; no microservices default. |
| `02-architecture-diagrams.md` | One backend codebase with bounded domains, stateless workers, Postgres event/outbox path, RabbitMQ compatibility, and NATS only as a future Phase 4 candidate. |
| `03-domain-boundaries.md` | Domain ownership, anti-corruption layers, package-layout migration rules, and boundary tests before restructuring. |
| `04-execution-agent-runtime.md` | Durable execution with leases, checkpoints, idempotency, replay, retries, HITL pauses, and interruptible agents. |
| `05-knowledge-events-data.md` | Event schema v1, Postgres outbox, RabbitMQ compatibility, knowledge derived from events, and provider abstraction. |
| `06-observability-deployment.md` | Required identifiers, replay levels, deep-health, SLOs, Docker Compose self-hosting, and optional Kubernetes/SaaS packaging. |
| `07-roadmap-risks-not-build.md` | Active rebuild roadmap remains the near-term source of truth; stop gates and non-goals prevent premature scale work. |

## Non-Negotiable Principles

1. **Execution must be durable.** Runs, tasks, tool calls, provider calls, HITL pauses, budgets, and failures need event and checkpoint evidence.
2. **The backend remains a modular monolith by default.** Split only when deployment, ownership, and data boundaries are stable enough to pay the distributed-systems tax.
3. **Event sourcing is bounded to execution, audit, replay, and knowledge derivation.** Do not event-source every table.
4. **Workers must be stateless and lease-based.** A worker loses authority when its lease expires or is reclaimed.
5. **Checkpointing must precede side-effect acknowledgement.** Crash recovery starts from the last durable checkpoint and idempotency key.
6. **Provider calls must be adapter-bound.** Provider SDKs do not leak into business logic, routing shortcuts, or replay reducers.
7. **Provider routing research remains unresolved until source-backed.** Unsupported provider-specific routing claims are forbidden.
8. **Memory must be workspace-scoped, redaction-aware, and event-derived where possible.**
9. **Replay must be possible without replaying unsafe provider/tool side effects by default.**
10. **Observability is an architectural invariant.** Request, run, task, event, worker, lease, workspace, and provider identifiers must travel together.
11. **Self-hosted deployment stays simple.** Docker Compose remains the baseline; Kubernetes is optional SaaS packaging, not a self-hosting requirement.
12. **Complexity must be earned.** NATS, service mesh, Kubernetes, CQRS projections, and agent runtime scale work wait for stop gates.

## Why This Is the Best Fit

This architecture matches FlowManner's actual product and operational reality:

- The current backend is one cohesive FastAPI codebase, not a set of independently owned services.
- The substrate layer already points toward append-only events, replay, executor strategies, budgets, and failure recovery.
- The current deployment is Docker Compose based and must remain easy for self-hosted users.
- The product is becoming an agentic execution platform, so long-running work needs leases, checkpoints, idempotency, and replay.
- AI providers and local runtimes will change over time, so provider abstraction is safer than provider-specific coupling.
- Knowledge, audit, cost, and dashboards should derive from events rather than from scattered UI state.
- SaaS scale is possible later, but only after the core execution model is durable and observable.

It also matches the active rebuild constraints: production issues, CI, observability, Blueprint+Run unification, chat UX, and broken-page hardening must be completed before the future architecture is treated as user-ready.

## Final Architecture in One Sentence

> FlowManner should become a modular, event-driven orchestration platform with durable execution, stateless leased workers, first-class agents, workspace-scoped knowledge, provider abstraction, replayable observability, and self-hosted-first deployment, implemented in phases behind explicit stop gates.

## Phased Implementation Stance

The final architecture is **phased** and **implementation-ready as a sequencing contract**:

| Phase | Focus | What is safe | What is not safe |
|---|---|---|---|
| Phase 0 | Architecture lock and safety net | Lock decisions, domain boundaries, event schema v1, substrate characterization tests, observability for existing paths. | New scale infrastructure, provider-specific routing claims, one-shot repository restructure. |
| Phase 1 | Substrate hardening | Worker leases, checkpointing, idempotency, executor/chaos tests, retry and budget policies. | NATS, distributed claims, agent runtime scale work before crash recovery is proven. |
| Phase 2 | Agent runtime v1 | Lifecycle, capability-bound tools, context builder, provider adapter interface, memory hierarchy. | Custom actor-framework lock-in or provider-specific business logic. |
| Phase 3 | Knowledge and memory v1 | Event-derived semantic/episodic memory, retrieval, retention, redaction, workspace-scoped indexes. | Knowledge work that cannot cite source events or enforce deletion/retention. |
| Phase 4 | Event backbone and data platform | Evaluate NATS JetStream only after outbox and event-schema stability; add projections and analytics if needed. | Replacing RabbitMQ or introducing Kafka/Redpanda before replay, idempotency, and consumer parity are proven. |
| Later | SaaS packaging | Optional Kubernetes-ready packaging, edge/GPU pools, advanced replay, policy engine. | Making Kubernetes, service mesh, or cloud-only deployment mandatory for self-hosting. |

## Next Safe Steps

Preserve `docs/REBUILD-ROADMAP.md` as the active near-term roadmap. The safe next steps are:

1. Finish production `code_execute` behavior and the chat code execution path with explicit 4xx/5xx responses, request IDs, timeouts, sandbox capability checks, and tests.
2. Fix live preview and Firefox BUSY symptoms through backend tracing, structured errors, and observable progress rather than browser-side workarounds.
3. Harden CI so backend tests, frontend typecheck, and docs validation block merges.
4. Complete Sentry/Jaeger/deep-health baseline, including request ID propagation and dependency checks.
5. Ship substrate executor and kill-worker chaos tests before worker-plane scale claims.
6. Finish Blueprint+Run unification through additive tables, adapters, services, V2 APIs, dual-write, backfill, soak, and cutover.
7. Fix the six broken pages and chat UX baseline before presenting future execution UI as trustworthy.
8. Continue sandbox preview auth hardening and `fm_tokens` cleanup without reintroducing dual-auth state.
9. Add event schema v1, outbox behavior, lease/checkpoint tests, and replay smoke tests before NATS or other backbone work.
10. Keep provider routing research unresolved until source-backed evidence defines routing, fallback, cost, privacy, and local/cloud behavior.

## Closing Principle

The future of FlowManner is not a bigger rewrite.

It is a boring, test-backed platform that can execute work reliably, explain what happened, resume after failure, protect workspace data, and scale only when the substrate has earned the complexity.
