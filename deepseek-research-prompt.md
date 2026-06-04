# FlowManner — Deep Research Brief

## Context

FlowManner is an AI workflow orchestration platform. It's a running production system with:

- **Frontend:** Next.js (TypeScript) — mission management, agent config, workspace admin, browser-based AI agent UI
- **Backend:** FastAPI (Python 3.11) — 60+ endpoint modules, async SQLAlchemy/PostgreSQL, Redis, Qdrant, RabbitMQ/Celery, llama.cpp, Jaeger tracing
- **Status:** Production live at flowmanner.com. 935 tests passing. Recently completed CQRS refactor of mission layer. Has BYOK (bring your own API key), browser agents, RAG, multi-tenant workspaces, subscription tiers.

## Research Questions

Please investigate each of the following areas. Be specific — reference real products, papers, or patterns where possible. Prioritize actionable findings over generic advice.

### 1. Competitive Landscape & Positioning

- Who are the main competitors for "AI workflow orchestration" today? (LangGraph, Temporal, Airflow, Prefect, n8n, etc.)
- Where is FlowManner uniquely positioned vs each?
- What features do competitors have that FlowManner lacks and should prioritize?
- Are there adjacent markets (fine-tuning pipelines, eval platforms, agent observability) that FlowManner is naturally positioned for?

### 2. High-Value Feature Candidates

- **Agent observability:** What do production AI agent systems use for tracing, debugging, replay? (LangSmith, Weights & Biases, custom OpenTelemetry?) What's the minimal viable observability stack?
- **Human-in-the-loop:** How do platforms implement approval gates, pause/resume in mission workflows? Any good reference architectures?
- **Multi-agent orchestration:** FlowManner has a SwarmOrchestrator. What patterns exist beyond simple DAGs — debate/consensus loops, hierarchical planners, tool-calling agents? What papers/products define the state of the art?
- **Evaluation workflows:** Should FlowManner support eval harnesses (lm-eval-harness, EleutherAI, custom)? Is there a product gap here?
- **Template marketplace:** Would a community template gallery (like n8n's or LangFlow's) drive adoption? What's the technical cost?
- **Real-time collaboration:** Shared mission editing, cursors, comments — how valuable vs how complex?

### 3. Infrastructure & Scaling

- The homelab runs llama.cpp (Qwen3.6-27B-MTP) + RTX 5060 Ti. For production AI inference, what's the most cost-effective path?
- GPU marketplace arbitrage: renting spot instances (RunPod, Vast.ai, TensorDock, Lambda) vs buying hardware. At what scale does each win?
- What's the state of speculative decoding / MTP / continuous batching for self-hosted models in 2026?
- The backend is FastAPI + Celery. Are there better patterns for AI workloads? (Ray Serve? Modal? ASGI with background tasks?)

### 4. UX & Product Gaps

- FlowManner targets "technical founders building AI products." What onboarding friction exists for this persona?
- What do mission/agent dashboards look like in leading products (Linear, Vercel, Retool, LangSmith)?
- Would a public API / SDK accelerate adoption? What endpoints should be v1?
- What's the biggest usability gap between FlowManner and a product like LangSmith or Vercel AI SDK?

### 5. Architecture Risks & Debt

- The CQRS refactor just landed. What are common post-CQRS pitfalls? (eventual consistency bugs, dual-write headaches, read-model staleness)
- The test suite was completely broken (99 failures) and is now clean. What does this imply about test coverage quality vs quantity?
- RabbitMQ + Celery for async tasks: at what scale does this break? What are the migration paths (Temporal, River, NATS)?
- Any security concerns with BYOK (users providing their own API keys that hit the VPS)?
- Database growth: what's the query profile? Which tables grow fastest? What's the 6-month projection?

### 6. Business Model & Monetization

- How do competitors monetize? (LangSmith: per-token, Temporal: per-workflow, n8n: per-seat, Airflow: hosted/commercial)
- What pricing model fits FlowManner's positioning?
- Would self-hosted / on-prem enterprise sales work, or is SaaS-only better?
- What's the most common reason users churn from AI workflow platforms?

## Deliverable

A structured research report with:
1. Key findings for each section above
2. Prioritized recommendations (P0/P1/P2)
3. Any "don't do this" warnings based on failed approaches in the industry
4. 3-5 concrete next features or improvements I should build this week
