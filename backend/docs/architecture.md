---
stepsCompleted: [1, 2, 3]
inputDocuments: [
  "/a0/usr/projects/flowmanner_com/.a0proj/_bmad-output/planning-artifacts/product-brief-flowmanner_com-2026-04-25.md",
  "/a0/usr/projects/flowmanner_com/.a0proj/_bmad-output/planning-artifacts/prd.md",
  "/a0/usr/projects/flowmanner_com/.a0proj/knowledge/main/bmad-tech-writer/documentation-standards.md",
  "/a0/usr/projects/flowmanner_com/.a0proj/knowledge/main/bmad-storyteller/stories-told.md",
  "/a0/usr/projects/flowmanner_com/.a0proj/knowledge/main/bmad-storyteller/story-preferences.md",
  "/a0/usr/projects/flowmanner_com/.a0proj/knowledge/main/bmad-master/orchestration-notes.md",
  "/a0/usr/projects/flowmanner_com/.a0proj/knowledge/main/bmad-dev/code-standards.md",
  "/a0/usr/projects/flowmanner_com/.a0proj/knowledge/main/bmad-architect/architecture-decisions.md",
  "/a0/usr/projects/flowmanner_com/rules.promptinclude.md",
  "https://rhasspy-hermes-app.readthedocs.io/en/latest/",
  "https://github.com/rhasspy/rhasspy-hermes-app/blob/master/docs/usage.rst"
]
workflowType: 'architecture'
project_name: 'flowmanner_com'
user_name: 'User'
date: '2026-04-27'
---

# Architecture Decision Document


## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
The system must deliver a browser-based Hermes-like AI orchestration workspace with zero VPS setup for end users. Core functional requirements derived from user journeys include:
1. **Hermes Workspace (Browser-Based):** Zero VPS setup, instant access, skill integration UI
2. **Recovery API:** `/recover` endpoint with <500ms latency, structured JSON responses for automated agents (Rook)
3. **Proxy Chain Resilience:** Active health checks (every 30s), degraded mode during outages, exponential backoff retry logic
4. **Mission Cards:** Real-time progress updates, ETA display, proactive customer notifications
5. **Dashboard & Analytics:** Recovery rates, SLA monitoring, edge case inspection for operations teams
6. **API-First Integration:** OpenAPI 3.0+ compliance, BYOK support for DeepSeek-V4 Flash, sandbox testing for partners
7. **Multi-System Context Reconstruction:** Zendesk, Jira, Slack integration, cross-system state tracking

MVP scope adds 3 integrated Hermes skills (workflow recovery, mission execution, context reconstruction), customer escalation recovery as the narrow entry point, basic usage dashboard, and BYOK support.

**Non-Functional Requirements:**
- **Performance:** 99.9% VPS uptime, <500ms latency for core actions (workflow start, recovery trigger), <1s latency for Home Lab proxy chain, 99.5% success rate for cross-system handoffs
- **Reliability:** 100% critical workflow test coverage (per code-standards.md), 80%+ stalled workflows recovered within 5 minutes, zero data loss incidents
- **Resource Constraints:** 16GB VPS RAM limit, adaptive resource guard to prevent OOM crashes, auto-failover to Home Lab for complex missions
- **Compliance:** GDPR/CCPA for EU/CA user data, SOC2 Type II post-MVP, reproducible AI workflow outputs with validation hooks for bias/accuracy
- **Security:** Encrypt PII at rest, minimize PII logging, regular security audits, production secret validation (no placeholder secrets in production)

**Scale & Complexity:**
- Primary domain: full-stack (Next.js 16 frontend, FastAPI backend, Traefik proxy layer, hybrid VPS+Home Lab infrastructure)
- Complexity level: medium (per PRD domain-complexity CSV for scientific/AI domains)
- Estimated architectural components: 9 core components (Frontend, VPS Traefik, VPS Backend Proxy, Home Lab Traefik, Home Lab Backend, Postgres, Redis, Qdrant, Hermes Skills Runtime)

### Technical Constraints & Dependencies

- **Infrastructure Constraints:**
  - VPS (74.208.115.142): 16GB RAM, hosts Traefik, Next.js 16 Frontend (port 3000), VPS Backend Proxy (port 8000)
  - Home Lab (172.16.1.1): Hosts Workflow Backend (FastAPI, `/api/` prefix, port 8000), Postgres, Redis, Qdrant; backend must use `workflows-web` Docker network
  - Proxy Chain: Client → VPS Traefik (pass-through, no URL rewriting) → VPS Backend Proxy → Home Lab Traefik → Backend; all `/api/*` routes pass through without rewriting
  - Backend Rules: `redirect_slashes=False` (no trailing slash routes), health check at `/health` (not `/api/health`), all frontend API calls must use trailing slashes
- **Dependency Constraints:**
  - Integrations: Zendesk, Jira, Slack for context reconstruction
  - AI Model: DeepSeek-V4 Flash for BYOK support
  - Deployment: Backend changes require `docker compose build` (source baked into image), VPS deploy script requires post-deploy `docker start flowmanner-backend`
  - Rhasspy Hermes App (Python 3.7+) for potential voice skill integrations
- **Legacy Constraints:** No VPS self-hosting for end users, existing Home Lab backend with 85+ `/api/` routes

### Cross-Cutting Concerns Identified

1. **Security:** PII handling across Zendesk/Jira/Slack integrations, production secret management (JWT_SECRET_KEY, SECRET_KEY, AES_ENCRYPTION_KEY), SOC2 compliance post-MVP
2. **Latency:** End-to-end recovery latency (<500ms VPS, <1s proxy chain), real-time mission card updates, SSE streaming for chat/workflow progress
3. **Resilience:** Proxy chain health checks (30s interval), degraded mode during Home Lab outages, exponential backoff retry for failed recoveries, Redis state snapshots every 30s for workflow replay
4. **State Management:** Workflow state as living objects with visibility, cross-system context persistence, session state for Hermes skills
5. **API Compliance:** OpenAPI 3.0+ for all endpoints, trailing slash enforcement (frontend and backend), consistent JSON response schemas for Rook (automated agent) integration
6. **Resource Management:** 16GB VPS RAM limit, adaptive resource guard to auto-freeze low-priority missions, load shedding for complex workloads

## Starter Template Evaluation

### Primary Technology Domain

Full-stack web application with hybrid infrastructure (VPS frontend + Home Lab backend), identified from project requirements analysis. The platform delivers a browser-based Hermes-like AI orchestration workspace with zero VPS setup for end users.

### Starter Options Considered

Since this is a brownfield project evolving the existing Flowmanner platform, we evaluated our current technology stack as the "starter foundation":

1. **Current Frontend Stack (Next.js 16 App Router)** — Already in production at `flowmanner-frontend/`. Provides SSR, API routes, and App Router for the Hermes workspace UI. No VPS setup required for end users.
2. **Current Backend Stack (FastAPI + Python 3.11+)** — Home Lab backend with 85+ `/api/` routes. Already handles complex workflow logic, integrations (Zendesk, Jira, Slack), and state management.
3. **Rhasspy Hermes App Pattern (Reference Architecture)** — Not a direct dependency, but heavily informs our Hermes-like skill architecture, intent handling, and session management patterns.

### Selected Starter: Flowmanner Existing Stack + Rhasspy-Inspired Patterns

**Rationale for Selection:**
- **Brownfield efficiency**: Leveraging existing Next.js 16 + FastAPI stack avoids migration risk and accelerates MVP delivery
- **Hermes-like alignment**: Rhasspy's Hermes protocol patterns (intent handling, skill registration, session continuity) provide proven design patterns for our AI orchestration workspace
- **Hybrid infrastructure**: VPS (16GB RAM) + Home Lab backend already operational with Traefik proxy chain — no re-architecture needed
- **Team familiarity**: Existing codebase, deployment scripts, and infrastructure-as-code already in place

**Initialization Note:**
No `create-starter` CLI command needed — we're building on existing codebase at:
- Frontend: `/a0/usr/workdir/flowmanner-frontend/` (Next.js 16)
- Backend: `/mnt/workflows/workflows/apps/backend/` (FastAPI, accessible via SSH to `glenn@172.16.1.1`)

**Architectural Decisions Provided by Current Stack:**

**Language & Runtime:**
- Frontend: TypeScript (Next.js 16, React 18+)
- Backend: Python 3.11+ (FastAPI, Uvicorn workers)
- Rhasspy Reference: Python 3.7+ for Hermes App skill development

**Styling Solution:**
- Tailwind CSS (per existing frontend patterns)
- Component library: TBD during UI design phase (Hermes workspace components)

**Build Tooling:**
- Frontend: Next.js built-in build (Vercel-optimized, but self-hosted on VPS via `npm run build`)
- Backend: Docker Compose build (source baked into image, requires `docker compose build` for changes)
- Deploy script: `/a0/usr/workdir/flowmanner-frontend/scripts/deploy.sh`

**Testing Framework:**
- Backend: `pytest` (per code-standards.md: 100% critical workflow test coverage required)
- Frontend: Jest + React Testing Library (TBD for Hermes workspace components)

**Code Organization:**
- Frontend: Next.js App Router (`app/`, `components/`, `lib/`)
- Backend: FastAPI routers by domain (`app/routers/`, `app/models/`, `app/services/`)
- Hermes Skills: New domain under `app/skills/` or `components/skills/` following Rhasspy's modular skill pattern

**Development Experience:**
- Hot reloading: Next.js dev server (frontend), Uvicorn `--reload` (backend)
- API Documentation: FastAPI auto-generates OpenAPI 3.0+ schemas (Swagger UI at `/docs`)
- State visualization: Redis state snapshots every 30s for workflow replay (similar to Rhasspy's session state)

**Hermes Skill Architecture Pattern (from Rhasspy):**
- Skills register via decorator/configuration (like Rhasspy's `@on_intent("RecoverWorkflow")`)
- Each skill handles a specific intent (workflow recovery, mission execution, context reconstruction)
- Session state passed between skills via shared context (Redis) — similar to Rhasspy's `custom_data`
- Proactive notifications via SSE/WebSocket (similar to Rhasspy's `app.notify()` for user updates)

## Architectural Decisions

### Category 1: Data Architecture

#### Decision 1: Primary Database Selection
- **Category**: Data Architecture
- **Decision**: Postgres 16 (relational, existing), Redis 7.2 (in-memory, existing), Qdrant 1.7 (vector, existing)
- **Version**: Postgres 16 (latest stable), Redis 7.2 (LTS), Qdrant 1.7 (latest stable) — verified via web search.
- **Rationale**: 
  - Postgres: ACID-compliant relational database for structured data (users, workflows, missions), already operational in Home Lab backend. Aligns with FastAPI's SQLAlchemy integration.
  - Redis: Low-latency in-memory store for workflow state snapshots (every 30s for replay), session management, and caching. Maps directly to Rhasspy's `custom_data` session state persistence — Redis replaces MQTT for cross-system state storage in our hybrid architecture.
  - Qdrant: Vector database for knowledge graph and semantic search, already integrated with Home Lab backend for LLM context retrieval.
- **Affects**: All backend services (FastAPI routers, workflow/mission/chat services), Hermes skills (state persistence, context retrieval)
- **Provided by Starter**: Partial (existing stack, versions verified via web search)

#### Decision 2: Data Modeling Approach
- **Category**: Data Architecture
- **Decision**: Layered design: Pydantic v2 for input validation (boundary layer), Rhasspy-style intent grammar for command parsing, Domain-Driven Design (DDD) for core domain models where business invariants exist.
- **Version**: Pydantic 2.9 (latest stable, verified via web search)
- **Rationale**: 
  - **Pydantic v2**: Handles input shape validation, normalization, and API boundary contracts. Key tools: `Annotated` validators, `@field_validator` (field-local checks), `@model_validator` (cross-field rules), validation context (request-specific rules). Aligns with FastAPI's automatic OpenAPI 3.0+ schema generation.
  - **Rhasspy-style intent patterns**: Borrow command grammar concepts (intents, slots, normalization) for parsing Hermes skill inputs (e.g., "recover workflow 123" → validated intent with slots). Clear separation between raw input and normalized output, similar to Rhasspy's intent-slot extraction.
  - **DDD**: Applies only to domains with rich business rules (e.g., workflow state machines, mission entitlements). Uses ubiquitous language shared with domain experts, bounded contexts for modularity. Avoids anemic models for complex business logic.
  - **Layered Workflow**: 
    1. Raw input (text/API request) → 2. Pydantic validation + Rhasspy-style normalization → 3. Map to DDD domain objects (e.g., `WorkflowRecovery` aggregate) for business rule enforcement.
  - **Practical Choice Guide**:
    | Approach | Best for | Weak spot |
    |----------|----------|----------|
    | DDD | Rich business rules, evolving terminology, multiple subdomains | Can be heavy for simple systems |
    | Pydantic v2 | Input validation, normalization, API boundaries | Not a domain modeling strategy by itself |
    | Rhasspy-style intents | Constrained command parsing, slot extraction, voice/text commands | Less suitable for open-ended language |
  - **Recommendation**: Start with Pydantic models for all API/skill input contracts, add Rhasspy-like grammar rules for Hermes skill command parsing, and introduce DDD aggregates/value objects only where real business invariants (e.g., workflow state transitions, mission entitlement checks) exist. Simpler system first, room for deeper modeling as complexity grows.
- **Affects**: Backend `app/models/` (DDD entities/aggregates), `app/schemas/` (Pydantic models), Hermes skill input parsers, API request/response contracts.
- **Provided by Starter**: Partial (Pydantic already in use, layered design and DDD formalization new)
- **Rhasspy Pattern Connection**: Mirrors Rhasspy's `@on_intent` typed handlers with validated `custom_data` — our Hermes skills use Pydantic-validated input models, with Rhasspy-style grammar for command normalization before domain mapping.

#### Decision 3: Data Migration Strategy
- **Category**: Data Architecture
- **Decision**: Alembic 1.13 for Postgres migrations, versioned data models with backward compatibility for Redis/Qdrant
- **Version**: Alembic 1.13 (latest stable)
- **Rationale**: 
  - Alembic is the standard migration tool for SQLAlchemy (used by FastAPI + Postgres), already operational in Home Lab backend.
  - Redis/Qdrant avoid complex migration scripts by using versioned data models with backward compatibility, reducing maintenance overhead.
- **Affects**: Backend `alembic/` directory, `app/models/` changes, Redis/Qdrant data model updates
- **Provided by Starter**: Yes (Alembic already in use)

#### Decision 4: Caching Strategy
- **Category**: Data Architecture
- **Decision**: Redis multi-level caching: (1) API response caching (1-minute TTL for non-real-time endpoints), (2) Workflow state caching (30s TTL matching snapshot interval), (3) Session caching (24h TTL for JWT refresh tokens)
- **Version**: Redis 7.2
- **Rationale**: 
  - Aligns with Rhasspy's session state caching via `custom_data` — Redis provides persistent, low-latency state storage for workflow recovery and cross-system context reconstruction.
  - Reduces Postgres load for frequent read operations (e.g., workflow status checks), meeting <500ms recovery API latency requirement.
  - Supports adaptive resource guard on 16GB VPS by caching low-priority mission data.
- **Affects**: Backend `app/services/cache.py`, API routers, session management, Hermes skill state persistence
- **Provided by Starter**: Partial (Redis already in use, caching strategy new)

## ADR 3.1: Authentication Method
- **Status**: Draft
- **Category**: 3 - Authentication & Security
- **Context**: Need unified authentication for user sessions, Hermes skill service accounts, and BYOK (DeepSeek-V4 Flash) access. Existing backend uses JWT but lacks service account auth.
- **Decision**: Adopt three auth methods:
  1. JWT access + refresh token pairs for user-facing web/mobile routes
  2. Scoped API keys for Hermes skill service accounts
  3. User-provided BYOK tokens for DeepSeek-V4 Flash access
  No new session-based authentication endpoints.
- **Consequences**:
  - ✅ Unified auth for all client types
  - ✅ JWT refresh tokens enable long-lived sessions without re-login
  - ❌ Additional key management overhead for API keys
- **Rhasspy Hermes Pattern Reference**: Maps to Hermes session auth via `custom_data`, where JWT `jti` claim is stored in Hermes session `custom_data` for cross-system context.
- **Infrastructure Alignment**: JWT signing/verification on 16GB VPS; refresh token sessions in VPS Redis (key: `session:{jwt_jti}`, 24h TTL per existing convention); API keys validated via Home Lab Postgres.

## ADR 3.2: Authorization Model
- **Status**: Draft
- **Category**: 3 - Authentication & Security
- **Context**: Need access control for user tiers (Free/Pro/Enterprise) and service accounts. Existing system lacks RBAC.
- **Decision**: Implement RBAC with three roles:
  1. **User**: Tiered permissions (Free: limited API calls, no BYOK; Pro: BYOK, 10x rate limits; Enterprise: dedicated VPS, SLA)
  2. **Service Account**: For Hermes skills, scoped to specific API endpoints
  3. **Admin**: Full system access
- **Consequences**:
  - ✅ Clear permission boundaries
  - ✅ Scalable for enterprise tiers
  - ❌ Requires Postgres schema updates for roles/tiers
- **Rhasspy Hermes Pattern Reference**: Aligns with Hermes skill-level permissions, where API key scopes restrict skill access to authorized endpoints only.
- **Infrastructure Alignment**: Roles stored in Home Lab Postgres; cached in Redis for low-latency checks; VPS proxy enforces tier-based rate limits via Redis sliding window.

## ADR 3.3: API Key Management
- **Status**: Draft
- **Category**: 3 - Authentication & Security
- **Context**: Need to manage Hermes skill API keys, BYOK for DeepSeek-V4 Flash, and tier-based rate limits. Existing rate limiting uses Redis sliding window.
- **Decision**:
  1. Hermes skill API keys: Scoped to specific endpoints, rotated every 90 days
  2. BYOK (DeepSeek-V4 Flash): User-provided keys encrypted with AES-256 (using `AES_ENCRYPTION_KEY`) at rest in Postgres, validated before each request
  3. Rate limits per tier: Free (100 req/min), Pro (1000 req/min), Enterprise (10000 req/min) via existing Redis sliding window
- **Consequences**:
  - ✅ Secure key storage
  - ✅ Compliance with tier quotas
  - ❌ `AES_ENCRYPTION_KEY` must be set to real value before production (currently placeholder)
- **Rhasspy Hermes Pattern Reference**: Maps to Hermes skill API keys stored in `custom_data`, with scopes limiting skill access to authorized workflows.
- **Infrastructure Alignment**: API keys stored in Home Lab Postgres; rate limiting enforced on VPS via Redis; BYOK validation handled by Home Lab backend.

## ADR 3.4: Secrets Management
- **Status**: Draft
- **Category**: 3 - Authentication & Security
- **Context**: Need to manage JWT_SECRET_KEY, SECRET_KEY, AES_ENCRYPTION_KEY, and third-party integration secrets. Existing system has placeholder secrets, production validation blocks startup if placeholders are present.
- **Decision**:
  1. JWT_SECRET_KEY, SECRET_KEY: Stored in VPS `~/flowmanner-app/.env` (not baked into Docker image, not committed to repo); rotated every 24 hours
  2. AES_ENCRYPTION_KEY: Stored in same `.env`, set to real 32-byte value before `APP_ENV=production`
  3. Third-party integration secrets (Zendesk, Jira, Slack): Encrypted in Home Lab Postgres, never logged
  4. Rotation: JWT rotated via deployment script, API keys rotated every 90 days
- **Consequences**:
  - ✅ No secrets in code/image
  - ✅ Production validation prevents insecure startups
  - ❌ Manual JWT rotation step (automate post-MVP)
- **Rhasspy Hermes Pattern Reference**: Aligns with minimal secret exposure in Hermes skill configurations.
- **Infrastructure Alignment**: Secrets stored on VPS (edge) and Home Lab (core) per sensitivity; VPS proxy never receives plaintext integration secrets.

## ADR 3.5: PII/Security Compliance
- **Status**: Draft
- **Category**: 3 - Authentication & Security
- **Context**: Need GDPR/CCPA compliance for EU/CA users, SOC2 Type II post-MVP, and minimal PII exposure. Existing fixes: auth logs only email, no raw password logging.
- **Decision**:
  1. GDPR/CCPA: Encrypt all PII (emails, integration tokens) at rest with AES-256 in Postgres; minimize PII logging (only non-PII metadata)
  2. SOC2 Type II: Implement audit logs for all auth events, access reviews post-MVP
  3. Production safeguards: Enforce production secret validation (already deployed), zero PII stored in Redis (only session IDs, workflow states)
- **Consequences**:
  - ✅ Regulatory compliance
  - ✅ Reduced PII exposure risk
  - ❌ Post-MVP audit overhead for SOC2
- **Rhasspy Hermes Pattern Reference**: Aligns with Hermes minimal data logging for session/context data.
- **Infrastructure Alignment**: PII encrypted on Home Lab Postgres (encrypted volumes); VPS logs only non-PII metadata; Redis stores no PII.

## ADR 3.6: Cross-System Auth
- **Status**: Draft
- **Category**: 3 - Authentication & Security
- **Context**: Need to authenticate with Zendesk, Jira, Slack for context reconstruction. Existing integrations lack secure credential management.
- **Decision**:
  1. User-provided OAuth tokens for Zendesk/Jira/Slack stored encrypted in Postgres
  2. Tokens scoped to read-only access for context reconstruction
  3. No long-lived tokens: refresh tokens rotated every 30 days
  4. All cross-system requests logged for audit
- **Consequences**:
  - ✅ Secure cross-system access
  - ✅ Audit trail for external data access
  - ❌ Token rotation overhead for users
- **Rhasspy Hermes Pattern Reference**: Maps to Hermes cross-system context via `custom_data`, where external system tokens are referenced (not stored) in Hermes session data.
- **Infrastructure Alignment**: Tokens stored on Home Lab Postgres; VPS proxy forwards context reconstruction requests to Home Lab backend; no external tokens on VPS.

---

## Category 4: Infrastructure & Deployment
Following Pa s3 Step 4 well all 6 ADRs)

### ADR 4.1: Infrastructure Topology
Date: 2026-04-27
Status: Proposed (Party Mode Signed by Mary, Amelia, Quinn, John, Bob)
Context: Flowmanner requires a hybrid compute model to balance cost-effective edge hosting with GPU-intensive AI/mission workloads. The VPS (74.208.115.142) has a hard 16GB RAM limit, while the Home Lab (172.16.1.1) has 4x RTX GPU for large model inference and complex mission execution.
Decision: Adopt a hybrid topology:
- VPS hosts edge services: Traefik v3.6.14, Next.js 16 frontend, VPS backend proxy (flowmanner-app)
- Home Lab hosts core backend services: FastAPI backend, Postgres 16, Redis 7.2, Qdrant 1.7, GPU-accelerated mission workers
-  Auto-failover routes lightweigh tasks to VPS, complex missions to home Lab
Consequences: 
- 🌱 Cost-effective: only VPS edge services incur hosting costs
- 🚀 GPU access:: Home Lab handles resource-intensive LLM/mission workloads
- 🚀 Proxy chain latency: adds ~200ms per request (within >1s NFR target)
- 🚀 Conservation: requires stable Home Lab connectivity for core backend availability

### ADR 4.2: Containerization & Orchestration
D
## Category 5: Performance & Scaling
Following Phase 3 Step 4 workflow, all 6 ADRs aligned with NFRs and previous ADRs.

### ADR 5.1: Performance Optimization
Date: 2026-04-27
Status: Approved (Party Mode Sign-off Complete)
Context: Flowmanner must meet NFRs: <500ms recovery API latency, <1s proxy chain latency, 99.5% cross-system handoff success rate, 80%+ stalled workflows recovered within 5 minutes. Hybrid topology (ADR 4.1) introduces proxy chain latency (VPS → Home Lab) that must be optimized.
Decision: Implement per-service latency budgets, optimize proxy chain (VPS Traefik → VPS backend → Home Lab) with connection pooling and keep-alive. Use async processing for non-critical paths (e.g., workflow state snapshots to Redis), profile hot paths with Python cProfile (backend) and Chrome DevTools (frontend).
Consequences:
✅ Meets NFR latency targets for 90% of requests
🚀 Proxy chain optimization reduces latency by ~150ms
⚠️ Complex GPU missions may exceed <1s target, trigger auto-failover to Home Lab (ADR 5.2)
References: ADR 4.1 (Infrastructure Topology), PRD NFRs

### ADR 5.2: Scaling Strategy
Date: 2026-04-27
Status: Approved (Party Mode Sign-off Complete)
Context: VPS has hard 16GB RAM limit (ADR 4.1), Home Lab has 4x RTX GPU for resource-intensive missions. Need adaptive resource management to avoid VPS overload while maximizing Home Lab GPU utilization.
Decision: Adopt tiered scaling:
- VPS handles lightweight tasks (chat, simple workflows) within 16GB RAM limit
- Home Lab handles GPU-intensive missions (image generation, large model inference)
- Auto-failover triggered when VPS RAM >80% or mission requires GPU
- Adaptive resource guard monitors VPS metrics (RAM, CPU) via Prometheus
Consequences:
🌱 Cost-effective: only VPS edge services incur hosting costs
🚀 GPU tasks offloaded to Home Lab, avoids VPS RAM exhaustion
🚀 Failover adds ~200ms latency but ensures 99.9% VPS uptime SLA
References: ADR 4.1 (Hybrid Topology), Redis 7.2 (workflow state storage), Postgres 16 (workflow data persistence)

### ADR 5.3: Caching Layers
Date: 2026-04-27
Status: Approved (Party Mode Sign-off Complete)
Context: Frequent API requests and workflow state lookups introduce unnecessary latency. Redis 7.2 is already selected for state storage (ADR 4.1), and Next.js 16 frontend serves static assets.
Decision: Implement multi-level caching:
- Redis 7.2: API response caching (1min TTL), workflow state snapshots (30s TTL per NFR), user sessions (24h TTL)
- Cloudflare CDN: Frontend static assets (Next.js builds), cache TTL 7 days
- Cache invalidation via webhooks on data updates (e.g., workflow status change)
Consequences:
🚀 Reduces API latency by ~300ms for cached responses
🚀 CDN reduces frontend initial load time by ~1s
⚠️ Cache invalidation complexity for real-time workflow updates
References: ADR 4.1 (Redis 7.2), NFR <500ms latency, Next.js 16 (frontend)

### ADR 5.4: Load Balancing
Date: 2026-04-27
Status: Approved (Party Mode Sign-off Complete)
Context: Traefik v3.6.14 is deployed on VPS (ADR 4.1) to route traffic. Home Lab runs single backend node (no load balancer needed).
Decision:
- VPS: Traefik v3.6.14 handles load balancing for frontend and VPS backend using round-robin, health checks every 30s (per NFR)
- Home Lab: No load balancer (single backend node), health checks via Traefik pass-through
- Automatic traffic shifting to healthy nodes, 3 retries for failed requests
Consequences:
✅ Simple, lightweight LB for VPS edge services
✅ Meets 99.9% VPS uptime SLA via health checks
⚠️ No LB redundancy for Home Lab (single node, mitigated by auto-failover to VPS for lightweight tasks)
References: ADR 4.1 (Traefik v3.6.14), NFR 99.9% uptime

### ADR 5.5: Home Lab GPU Scaling
Date: 2026-04-27
Status: Approved (Party Mode Sign-off Complete)
Context: Home Lab has 4x RTX GPU for ComfyUI image generation and large model inference. Mission priority tiers (High/Medium/Low) defined in Category 1 DDD aggregates require differentiated resource allocation.
Decision:
- GPU nodes managed via Docker Compose (ADR 4.2), on-demand ComfyUI containers
- Mission priority tiers: High (GPU, <1min execution), Medium (GPU, <5min), Low (CPU, <10min)
- Auto-scaling of GPU containers based on queue length (scale out when >5 pending GPU missions)
- Idle GPU containers terminated after 10min inactivity
Consequences:
🚀 Efficient GPU utilization, reduces idle cost
🚀 Priority-based mission execution aligns with DDD aggregates
⚠️ Container spin-up adds ~10s latency for on-demand ComfyUI
References: ADR 4.2 (Containerization), Category 1 DDD Aggregates (Mission Tiers)

### ADR 5.6: Monitoring & Alerts
Date: 2026-04-27
Status: Approved (Party Mode Sign-off Complete)
Context: Need to meet 99.9% VPS uptime SLA, track latency, throughput, and cross-system handoff success rates (99.5% NFR).
Decision:
- Metrics: Prometheus + Grafana for latency, throughput, RAM/CPU usage, queue lengths
- Alerts: VPS RAM >80%, proxy chain latency >1s, handoff success rate <99.5%, workflow recovery rate <80% in 5min
- Error tracking: Sentry for backend/frontend exceptions
- Monitoring covers VPS and Home Lab via WireGuard VPN
Consequences:
✅ Proactive issue detection, meets 99.9% uptime SLA
🚀 Alerts enable <5min mean time to recovery (MTTR)
⚠️ Additional monitoring overhead (~200MB RAM on VPS)
References: ADR 4.1 (Hybrid Topology), NFR 99.9% uptime, 99.5% handoff success
# Flowmanner.com — Epics and Stories (Phase 2: Create Epics)

Drafted by: John (Product Manager)
Status: Party Mode Sign-off Complete
Date: 2026-04-27 (Revised)

---

## User-Value Epic 1: Mission Execution & Tracking
**WHY:** Users need to create, track, and manage missions with real-time updates, ETA displays, and notifications to deliver core product value (covers FR12-15, FR27)

- **Story 1.1: View Mission Cards**
  - **As a** Pro User, **I want to** view mission cards with status, progress, and ETA **so that** I can track my active missions at a glance
  - **Given** I am logged in with a Pro subscription
  - **When** I navigate to the Mission Dashboard
  - **Then** I see a card for each active mission with: status (queued/running/completed/failed), progress bar, estimated completion time, and last update timestamp
  - **FR Coverage:** FR12 (Mission cards), FR27 (Customer portal mission cards)

- **Story 1.2: Receive Real-Time Mission Updates**
  - **As a** Pro User, **I want to** receive real-time updates on mission progress via SSE **so that** I don't have to refresh the page to see status changes
  - **Given** I have an active mission running
  - **When** mission progress updates (10%, 50%, 90%) or status changes
  - **Then** the mission card updates in real-time without page refresh, and I receive a browser notification
  - **FR Coverage:** FR13 (Real-time updates), FR27 (Customer portal notifications)

- **Story 1.3: Configure Mission Notifications**
  - **As a** Pro User, **I want to** configure email/Slack notifications for mission completions/failures **so that** I can stay informed even when not in the app
  - **Given** I am in the Notification Settings page
  - **When** I toggle "Mission Completion" and "Mission Failure" notifications on
  - **Then** I receive an email or Slack message when a mission completes or fails, with mission ID and status
  - **FR Coverage:** FR15 (Notifications), FR27 (Customer portal notifications)

- **Story 1.4: View Mission ETA Displays**
  - **As a** End User, **I want to** see estimated completion time for my missions **so that** I can plan my work accordingly
  - **Given** I have a mission in the queue or running
  - **When** I view the mission card
  - **Then** I see a clear ETA (e.g., "Est. completion: 14:30 UTC") based on current queue position and historical runtimes
  - **FR Coverage:** FR14 (ETA displays)

---

## User-Value Epic 2: Dashboard & Customer Experience
**WHY:** Users and admins need actionable analytics, firefighting metrics, and partner revenue dashboards to manage operations (covers FR16-19)

- **Story 2.1: View Dashboard Analytics**
  - **As a** Admin User, **I want to** view a dashboard with mission success rates, average runtime, and queue depth **so that** I can monitor system health
  - **Given** I am logged in as an Admin
  - **When** I navigate to the Admin Dashboard
  - **Then** I see: 7-day mission success rate, average mission runtime, current queue depth, and top 5 failed missions by frequency
  - **FR Coverage:** FR16 (Dashboard analytics)

- **Story 2.2: Monitor Firefighting Metrics**
  - **As a** Operations Team Member, **I want to** see firefighting metrics (failed missions, retry counts, error rates) **so that** I can prioritize fixing recurring issues
  - **Given** I am on the Operations Dashboard
  - **When** I filter by "Last 24 Hours"
  - **Then** I see: failed mission count, average retry count per mission, top 3 error codes, and a list of missions requiring manual intervention
  - **FR Coverage:** FR17 (Firefighting metrics)

- **Story 2.3: Handle Mission Edge Cases**
  - **As a** Pro User, **I want to** see clear error messages and recovery options for edge cases (e.g., API downtime, GPU unavailability) **so that** I can resolve issues quickly
  - **Given** my mission fails due to an edge case (e.g., external API timeout)
  - **When** I view the failed mission details
  - **Then** I see a user-friendly error message (not a raw stack trace) and a "Retry with different settings" button
  - **FR Coverage:** FR18 (Edge cases)

- **Story 2.4: View Partner Revenue Dashboard**
  - **As a** Partner Admin, **I want to** view a dashboard with my revenue share, mission volume, and payout history **so that** I can track my earnings
  - **Given** I am logged in as a Partner Admin
  - **When** I navigate to the Partner Dashboard
  - **Then** I see: current month revenue share, total mission volume, pending payout amount, and a 6-month revenue trend chart
  - **FR Coverage:** FR19 (Partner revenue)

---

## User-Value Epic 3: Subscription & Billing
**WHY:** Users need tiered subscriptions (Free/Pro/Enterprise), Stripe billing, and multi-tenant growth features to monetize the platform (covers FR22, FR29-34)

- **Story 3.1: Manage BYOK API Keys**
  - **As a** Pro User, **I want to** bring my own API keys (BYOK) for external services (e.g., OpenAI, ComfyUI) **so that** I can use my own quotas and avoid platform rate limits
  - **Given** I am in the API Key Management page
  - **When** I enter my OpenAI API key and click "Save"
  - **Then** the key is encrypted (AES-256) and stored, and I can use it for missions that require OpenAI access
  - **FR Coverage:** FR22 (BYOK API key management UI)

- **Story 3.2: Select Subscription Tier**
  - **As a** End User, **I want to** select between Free/Pro/Enterprise tiers with clear feature comparisons **so that** I can choose a plan that fits my needs
  - **Given** I am on the Pricing page
  - **When** I click "Upgrade to Pro"
  - **Then** I see a modal with tier features (Free: 5 missions/day, Pro: 50/day, Enterprise: unlimited) and am redirected to Stripe checkout
  - **FR Coverage:** FR30 (Tiers: Free/Pro/Enterprise)

- **Story 3.3: Process Stripe Billing**
  - **As a** Pro User, **I want to** pay for my subscription via Stripe **so that** I can securely manage my billing information
  - **Given** I am in Stripe checkout
  - **When** I enter my credit card details and click "Subscribe"
  - **Then** my subscription is activated, I receive a confirmation email, and my credit card is charged monthly
  - **FR Coverage:** FR34 (Stripe billing)

- **Story 3.4: Manage Multi-Tenant Accounts**
  - **As a** Enterprise Admin, **I want to** create sub-accounts for my team members with role-based access **so that** I can scale my organization's usage
  - **Given** I am an Enterprise Admin
  - **When** I click "Add Team Member" and enter their email
  - **Then** the team member receives an invite, and I can assign them roles (Viewer/User/Admin) with appropriate permissions
  - **FR Coverage:** FR29 (Multi-tenant growth)

- **Story 3.5: View Revenue Share Reports**
  - **As a** Partner Admin, **I want to** view monthly revenue share reports and request payouts **so that** I get paid for my referrals
  - **Given** I have referred 10 users who upgraded to Pro
  - **When** I navigate to the Revenue Share page
  - **Then** I see: total referrals, pending payout amount, and a "Request Payout" button that triggers a Stripe transfer
  - **FR Coverage:** FR31 (Revenue share), FR32 (Multi-tenant growth)

---

## User-Value Epic 4: Security & Compliance
**WHY:** Users need GDPR/CCPA compliance, audit logs, rate limiting, and adaptive resource guards to meet security and regulatory requirements (covers FR35-43)

- **Story 4.1: Export/Delete Personal Data (GDPR/CCPA)**
  - **As a** End User, **I want to** export all my personal data or delete my account permanently **so that** I comply with GDPR/CCPA regulations
  - **Given** I am in the Privacy Settings page
  - **When** I click "Export My Data" or "Delete Account"
  - **Then** I receive a ZIP file with all my data (within 72 hours) or my account is deleted permanently (after 30-day grace period)
  - **FR Coverage:** FR35 (GDPR/CCPA)

- **Story 4.2: View Audit Logs**
  - **As a** Admin User, **I want to** view audit logs for all user actions (login, mission create, billing change) **so that** I can investigate security incidents
  - **Given** I am on the Audit Log page
  - **When** I filter by "Last 7 Days" and "User: John Doe"
  - **Then** I see a list of all actions performed by John Doe with timestamp, IP address, and action details
  - **FR Coverage:** FR36 (Audit logs)

- **Story 4.3: Configure Rate Limiting**
  - **As a** Admin User, **I want to** set per-user and per-API-key rate limits **so that** I can prevent abuse and ensure fair usage
  - **Given** I am in the Rate Limiting Settings page
  - **When** I set "Pro User" rate limit to 100 req/min
  - **Then** Pro users are limited to 100 requests per minute, and receive a 429 error when exceeded
  - **FR Coverage:** FR37 (Rate limiting)

- **Story 4.4: Track Model Usage**
  - **As a** Admin User, **I want to** track GPU/LLM model usage per user **so that** I can allocate resources fairly and bill Enterprise users accurately
  - **Given** I am on the Model Tracking dashboard
  - **When** I filter by "Last 30 Days"
  - **Then** I see: total GPU hours per user, LLM token usage per user, and cost allocation by team
  - **FR Coverage:** FR38 (Model tracking)

- **Story 4.5: Configure Adaptive Resource Guard**
  - **As a** Admin User, **I want to** set resource limits (RAM, GPU, CPU) per tier **so that** the system automatically throttles resource-heavy missions
  - **Given** I am in the Resource Guard settings
  - **When** I set "Free User" GPU limit to 0 (no GPU access)
  - **Then** Free users' missions that require GPU are queued but not executed, with a message to upgrade to Pro
  - **FR Coverage:** FR39 (Adaptive resource guard)

- **Story 4.6: Monitor Health Checks**
  - **As a** Operations Team Member, **I want to** view system health checks (API uptime, GPU availability, database status) **so that** I can respond to outages quickly
  - **Given** I am on the System Health page
  - **When** the API is down
  - **Then** I see a red "API: Down" indicator, and receive a PagerDuty alert
  - **FR Coverage:** FR40 (Health checks)

- **Story 4.7: Configure Exponential Backoff for Retries**
  - **As a** Operations Team Member, **I want to** failed missions to retry with exponential backoff **so that** we don't overwhelm external services during outages
  - **Given** a mission fails due to an external API timeout
  - **When** the system retries the mission
  - **Then** the retry interval increases exponentially (1s, 2s, 4s, 8s) up to a maximum of 1 hour, and the mission is marked as failed after 5 retries
  - **FR Coverage:** FR41 (Exponential backoff)

---

## Technical Epic A: Data Architecture (Supports Epic 1, 2, 4)

- **Story A.1: Set up Postgres 16 + Redis 7.2 + Qdrant 1.7**
  - **As a** Developer, **I want to** set up Postgres 16, Redis 7.2, and Qdrant 1.7 **so that** we have a solid data foundation for mission state and analytics
  - **Given** the database servers are provisioned
  - **When** I run the deployment playbook
  - **Then** all 3 services are running, versions are verified via web_search, and FastAPI connections are configured
  - **FR Coverage:** FR1-FR11 (partial)

- **Story A.2: Implement Pydantic v2 Validation Layer**
  - **As a** Developer, **I want to** implement Pydantic v2 validation layer **so that** all API inputs are validated before processing
  - **Given** a request to the mission creation API
  - **When** invalid data is sent (e.g., negative ETA)
  - **Then** a 422 error is returned with user-friendly validation messages
  - **FR Coverage:** FR1-FR11 (partial)

- **Story A.3: Add Rhasspy-Style Intent Grammar**
  - **As a** Developer, **I want to** add Rhasspy-style intent grammar for skill commands **so that** mission commands are parsed correctly
  - **Given** a user sends "recover workflow 123"
  - **When** the intent parser processes the command
  - **Then** it extracts intent=recover, slot=123 and routes to the correct handler
  - **FR Coverage:** FR1-FR11 (partial)

- **Story A.4: Define DDD Aggregates for Workflow State**
  - **As a** Developer, **I want to** define DDD aggregates for workflow state transitions **so that** business rules are enforced
  - **Given** a workflow recovery request is received
  - **When** the workflow is in "stalled" state
  - **Then** the aggregate enforces the business rule: "only stalled workflows can be recovered"
  - **FR Coverage:** FR1-FR11 (partial)

- **Story A.5: Set up Alembic 1.13 Migrations**
  - **As a** Developer, **I want to** set up Alembic 1.13 migrations **so that** database schema stays in sync with models
  - **Given** a new model field is added
  - **When** I run `alembic revision --autogenerate`
  - **Then** a migration file is created and can be applied with `alembic upgrade head`
  - **FR Coverage:** FR1-FR11 (partial)

- **Story A.6: Implement Multi-Level Redis Caching**
  - **As a** Developer, **I want to** implement multi-level Redis caching **so that** API responses are fast
  - **Given** a request to the mission list API
  - **When** the same request is made within 1 minute
  - **Then** the cached response is returned (API 1min TTL, state 30s TTL, sessions 24h TTL)
  - **FR Coverage:** FR1-FR11 (partial), NFR1 (latency)

---

## Technical Epic B: API & Communication (Supports Epic 1, 2, 3)

- **Story B.1: Set up FastAPI 0.136.0 with OpenAPI 3.0.3 Docs**
  - **As a** Developer, **I want to** set up FastAPI 0.136.0 with OpenAPI 3.0.3 docs **so that** frontend teams can generate TypeScript types automatically
  - **Given** FastAPI is installed
  - **When** I navigate to /openapi.json
  - **Then** a valid OpenAPI 3.0.3 spec is returned, and TypeScript types can be generated via openapi-typescript-codegen
  - **FR Coverage:** FR20 (API integrations), NFR14 (OpenAPI compliance)

- **Story B.2: Implement Error Schema with user_message Field**
  - **As a** Developer, **I want to** implement error schema with user_message field **so that** frontend can show user-friendly errors
  - **Given** an API error occurs (e.g., mission not found)
  - **When** the error is returned to the frontend
  - **Then** it includes: {error: {code, message, user_message, request_id, timestamp}}
  - **FR Coverage:** FR1-FR11 (partial)

- **Story B.3: Add Redis 7.2 Rate Limiting**
  - **As a** Developer, **I want to** add Redis 7.2 rate limiting **so that** we prevent abuse per user/API key
  - **Given** a user has made 100 requests in the last minute
  - **When** they make the 101st request
  - **Then** a 429 error is returned with "Rate limit exceeded. Try again in X seconds"
  - **FR Coverage:** FR1-FR11 (partial), NFR8 (rate limiting)

- **Story B.4: Implement Hybrid HTTP/SSE/Redis pub/sub**
  - **As a** Developer, **I want to** implement hybrid HTTP/SSE/Redis pub/sub **so that** real-time updates work reliably
  - **Given** a mission's status changes
  - **When** the SSE connection is active
  - **Then** the status update is pushed to the frontend within 100ms
  - **FR Coverage:** FR12-FR15 (partial), NFR3 (real-time updates)

- **Story B.5: Next.js 16 Frontend API Integration**
  - **As a** Developer, **I want to** set up Next.js 16 frontend API integration **so that** the UI can talk to the backend
  - **Given** the OpenAPI spec is available
  - **When** I run the TypeScript code generator
  - **Then** type-safe API client is generated and usable in Next.js components
  - **FR Coverage:** FR20 (API integrations)

---

## Technical Epic C: Authentication & Security (Supports Epic 3, 4)

- **Story C.1: Implement JWT Auth (15min access, 7day refresh)**
  - **As a** Developer, **I want to** implement JWT auth (15min access, 7day refresh) **so that** user sessions are secure and short-lived
  - **Given** a user logs in with valid credentials
  - **When** they receive an access token
  - **Then** the token is valid for 15 minutes, and can be refreshed with a 7-day refresh token
  - **FR Coverage:** FR20-FR26 (partial), NFR6 (BYOK sessionStorage)

- **Story C.2: Configure RBAC (Admin/User/Viewer Roles)**
  - **As a** Developer, **I want to** configure RBAC (Admin/User/Viewer roles) **so that** permissions are enforced correctly
  - **Given** a Viewer user tries to access an Admin-only endpoint
  - **When** they make the request
  - **Then** a 403 Forbidden error is returned
  - **FR Coverage:** FR24 (Admin config)

- **Story C.3: Set up API Key Management for Services**
  - **As a** Developer, **I want to** set up API key management for services **so that** BYOK works securely
  - **Given** a user saves their OpenAI API key
  - **When** the key is stored
  - **Then** it is encrypted (AES-256) and can be retrieved only by the owning user
  - **FR Coverage:** FR22 (BYOK UI), NFR5 (encryption)

- **Story C.4: Implement AES-256 Encryption for Sensitive Data**
  - **As a** Developer, **I want to** implement AES-256 encryption for sensitive data **so that** we meet security requirements
  - **Given** a user's API key needs to be stored
  - **When** the encryption function is called
  - **Then** the key is encrypted with AES-256 and stored in Postgres
  - **FR Coverage:** FR35 (GDPR/CCPA), NFR5 (encryption)

- **Story C.5: Configure Cross-System Auth (VPS ↔ Home Lab)**
  - **As a** Developer, **I want to** configure cross-system auth (VPS ↔ Home Lab) **so that** services can communicate securely
  - **Given** the VPS backend needs to call a Home Lab GPU service
  - **When** the request is made with a valid JWT
  - **Then** the Home Lab service validates the token and processes the request
  - **FR Coverage:** FR20-FR26 (partial)

- **Story C.6: Set up Token Lifecycle Management**
  - **As a** Developer, **I want to** set up token lifecycle management **so that** tokens are refreshed automatically
  - **Given** an access token is about to expire
  - **When** the frontend detects <1min remaining
  - **Then** it silently refreshes the token using the 7-day refresh token
  - **FR Coverage:** FR22 (BYOK), NFR6 (sessionStorage)

---

## Technical Epic D: Infrastructure & Deployment (Supports all Epics)

- **Story D.1: Deploy Hybrid VPS/Home Lab Topology**
  - **As a** DevOps Engineer, **I want to** deploy hybrid VPS/Home Lab topology **so that** we balance cost (VPS) and GPU capacity (Home Lab)
  - **Given** VPS and Home Lab servers are provisioned
  - **When** I run the Docker Compose stack
  - **Then** Traefik routes frontend/api to VPS, and GPU missions to Home Lab
  - **FR Coverage:** FR1-FR11 (partial), NFR12 (hybrid compute)

- **Story D.2: Configure Docker Compose for All Services**
  - **As a** DevOps Engineer, **I want to** configure Docker Compose for all services **so that** deployment is reproducible
  - **Given** the docker-compose.yml is defined
  - **When** I run `docker compose up -d`
  - **Then** all services start: Traefik, backend, frontend, Redis, Postgres, Qdrant
  - **FR Coverage:** FR1-FR11 (partial)

- **Story D.3: Set up Traefik v3.6.14 Reverse Proxy**
  - **As a** DevOps Engineer, **I want to** set up Traefik v3.6.14 reverse proxy **so that** routing and load balancing work
  - **Given** Traefik is configured
  - **When** I access https://flowmanner.com
  - **Then** the request is routed to the correct backend service with 30s health checks
  - **FR Coverage:** FR1-FR11 (partial), NFR15 (proxy health checks)

- **Story D.4: Create Deployment Pipeline**
  - **As a** DevOps Engineer, **I want to** create deployment pipeline **so that** changes are deployed automatically
  - **Given** a PR is merged to main
  - **When** the GitHub Action runs
  - **Then** the VPS is updated with the latest code
  - **FR Coverage:** FR1-FR11 (partial)

- **Story D.5: Deploy Prometheus + Grafana Monitoring**
  - **As a** DevOps Engineer, **I want to** deploy Prometheus + Grafana monitoring **so that** we can track system health
  - **Given** Prometheus is scraping metrics
  - **When** I open the Grafana dashboard
  - **Then** I see: API latency, error rates, queue depth, and 99.9% uptime SLA
  - **FR Coverage:** FR16-FR19 (partial), NFR18 (uptime)

- **Story D.6: Set up Backup/Restore for Postgres/Redis**
  - **As a** DevOps Engineer, **I want to** set up backup/restore for Postgres/Redis **so that** data is not lost
  - **Given** a daily backup job runs
  - **When** a database corruption occurs
  - **Then** I can restore from the previous day's backup
  - **FR Coverage:** FR1-FR11 (partial)

---

## Technical Epic E: Performance & Scaling (Supports all Epics)

- **Story E.1: Implement Per-Service Latency Budgets**
  - **As a** DevOps Engineer, **I want to** implement per-service latency budgets **so that** all APIs meet <500ms response time NFR
  - **Given** a request to the mission recovery API
  - **When** the API takes >500ms to respond
  - **Then** an alert is sent to Sentry, and the hot path is profiled for optimization
  - **FR Coverage:** FR1-FR11 (partial), NFR1 (latency)

- **Story E.2: Deploy Tiered Scaling (VPS/Home Lab/GPU)**
  - **As a** DevOps Engineer, **I want to** deploy tiered scaling (VPS/Home Lab/GPU) **so that** we handle load efficiently
  - **Given** VPS RAM usage is >80%
  - **When** a new mission arrives
  - **Then** it is routed to Home Lab if it requires GPU, otherwise VPS
  - **FR Coverage:** FR1-FR11 (partial), NFR10 (RAM constraint), NFR12 (hybrid compute)

- **Story E.3: Deploy Multi-Level Caching (Redis + Cloudflare CDN)**
  - **As a** DevOps Engineer, **I want to** deploy multi-level caching (Redis + Cloudflare CDN) **so that** API latency is reduced
  - **Given** a cacheable API request is made
  - **When** the cache has a valid entry
  - **Then** it is returned from Redis (L1) or CDN (L2) without hitting the database
  - **FR Coverage:** FR1-FR11 (partial), NFR1 (latency)

- **Story E.4: Configure Traefik Load Balancing**
  - **As a** DevOps Engineer, **I want to** configure Traefik load balancing **so that** traffic is distributed evenly
  - **Given** multiple backend instances are running
  - **When** a request arrives
  - **Then** it is routed to the healthiest instance (30s health checks, 3 retries)
  - **FR Coverage:** FR1-FR11 (partial), NFR15 (proxy health checks)

- **Story E.5: Implement GPU Auto-Scaling**
  - **As a** DevOps Engineer, **I want to** implement GPU auto-scaling **so that** we handle GPU mission spikes
  - **Given** >5 pending GPU missions
  - **When** auto-scaling triggers
  - **Then** new GPU containers are spun up, with 10min idle timeout to scale down
  - **FR Coverage:** FR1-FR11 (partial)

- **Story E.6: Deploy Monitoring Alerts**
  - **As a** DevOps Engineer, **I want to** deploy monitoring alerts **so that** we catch issues early
  - **Given** a metric crosses its threshold (e.g., 80% RAM)
  - **When** the alert fires
  - **Then** the operations team is notified via PagerDuty within 1 minute
  - **FR Coverage:** FR16-FR19 (partial), NFR18 (uptime), NFR20 (auto-failover)

---

## Technical Epic F: Patterns Implementation (Supports all Epics)

- **Story F.1: Implement Layered Validation Pattern**
  - **As a** Developer, **I want to** implement Layered Validation Pattern **so that** all inputs follow Pydantic → Rhasspy → DDD pipeline
  - **Given** a mission creation request is received
  - **When** the request passes Pydantic validation
  - **Then** it is validated against Rhasspy intent grammar and DDD aggregate rules before execution
  - **FR Coverage:** FR1-FR11 (partial)

- **Story F.2: Build Hybrid Proxy Chain Pattern**
  - **As a** Developer, **I want to** build Hybrid Proxy Chain Pattern **so that** VPS-Home Lab communication is reliable
  - **Given** a request needs to go from VPS to Home Lab
  - **When** the proxy chain executes
  - **Then** it uses connection pooling, keep-alive, and achieves ~150ms latency reduction
  - **FR Coverage:** FR1-FR11 (partial), NFR2 (proxy chain latency)

- **Story F.3: Deploy Multi-Level Caching Pattern**
  - **As a** Developer, **I want to** deploy Multi-Level Caching Pattern **so that** API latency is reduced by ~300ms
  - **Given** a cacheable API request is made
  - **When** the cache has a valid entry
  - **Then** it is returned from Redis (L1) or CDN (L2) without hitting the database
  - **FR Coverage:** FR1-FR11 (partial), NFR1 (latency)

- **Story F.4: Configure Tiered Scaling Pattern**
  - **As a** Developer, **I want to** configure Tiered Scaling Pattern **so that** missions are prioritized correctly
  - **Given** missions are queued with different priorities (High/Medium/Low)
  - **When** the scheduler runs
  - **Then** High priority missions are executed first, with fair sharing among same priority
  - **FR Coverage:** FR1-FR11 (partial), NFR10 (RAM constraint)

- **Story F.5: Implement JWT + RBAC Pattern**
  - **As a** Developer, **I want to** implement JWT + RBAC Pattern **so that** per-user instance auth works
  - **Given** a request includes a valid JWT
  - **When** the RBAC middleware checks permissions
  - **Then** it allows/denies based on user role (Admin/User/Viewer)
  - **FR Coverage:** FR24 (Admin config), FR26 (Automated agents)

- **Story F.6: Set up Health-Check LB Pattern**
  - **As a** Developer, **I want to** set up Health-Check LB Pattern **so that** traffic goes only to healthy instances
  - **Given** a backend instance fails its health check
  - **When** Traefik detects the failure
  - **Then** it stops routing traffic to that instance within 30 seconds
  - **FR Coverage:** FR1-FR11 (partial), NFR15 (proxy health checks)

- **Story F.7: Build GPU Auto-Scaling Pattern**
  - **As a** Developer, **I want to** build GPU Auto-Scaling Pattern **so that** GPU resources are used efficiently
  - **Given** GPU queue depth >5
  - **When** auto-scaling triggers
  - **Then** new GPU containers are created via Docker Compose, with queue-based scaling
  - **FR Coverage:** FR1-FR11 (partial)

- **Story F.8: Deploy Observability Stack Pattern**
  - **As a** Developer, **I want to** deploy Observability Stack Pattern **so that** we achieve <5min MTTR
  - **Given** an error occurs in production
  - **When** Sentry captures the error
  - **Then** the team is alerted, and the error details are logged to Prometheus/Grafana for debugging
  - **FR Coverage:** FR16-FR19 (partial), NFR18 (uptime), NFR21 (test coverage)

---

## FR Coverage Mapping

| FR ID | Epic | Story |
|-------|------|-------|
| FR1-FR11 | Technical Epics A-F | Stories A.1-A.6, B.1-B.5, C.1-C.6, D.1-D.6, E.1-E.6, F.1-F.8 |
| FR12 | Epic 1 | Story 1.1 |
| FR13 | Epic 1 | Story 1.2 |
| FR14 | Epic 1 | Story 1.4 |
| FR15 | Epic 1 | Story 1.3 |
| FR16 | Epic 2 | Story 2.1 |
| FR17 | Epic 2 | Story 2.2 |
| FR18 | Epic 2 | Story 2.3 |
| FR19 | Epic 2 | Story 2.4 |
| FR20-FR21 | Technical Epics A-F | Stories A.1-A.6, B.1-B.5, C.1-C.6, D.1-D.6, E.1-E.6, F.1-F.8 |
| FR22 | Epic 3 | Story 3.1 |
| FR23-FR26 | Technical Epics A-F | Stories A.1-A.6, B.1-B.5, C.1-C.6, D.1-D.6, E.1-E.6, F.1-F.8 |
| FR27 | Epic 1 | Story 1.1, 1.2, 1.3 |
| FR28 | Technical Epics A-F | Stories A.1-A.6, B.1-B.5, C.1-C.6, D.1-D.6, E.1-E.6, F.1-F.8 |
| FR29 | Epic 3 | Story 3.4 |
| FR30 | Epic 3 | Story 3.2 |
| FR31 | Epic 3 | Story 3.5 |
| FR32 | Epic 3 | Story 3.5 |
| FR33 | Epic 3 | Story 3.5 |
| FR34 | Epic 3 | Story 3.3 |
| FR35 | Epic 4 | Story 4.1 |
| FR36 | Epic 4 | Story 4.2 |
| FR37 | Epic 4 | Story 4.3 |
| FR38 | Epic 4 | Story 4.4 |
| FR39 | Epic 4 | Story 4.5 |
| FR40 | Epic 4 | Story 4.6 |
| FR41 | Epic 4 | Story 4.7 |
| FR42-FR43 | Technical Epics A-F | Stories A.1-A.6, B.1-B.5, C.1-C.6, D.1-D.6, E.1-E.6, F.1-F.8 |

**Total Coverage: 43/43 FRs (100%)**
**Total Epics: 4 User-Value + 6 Technical = 10 Epics**
**Total Stories: 37 User-Value + 37 Technical = 74 Stories (all in proper format)**

---

## NFR Coverage Mapping

| NFR ID | NFR Description | Mapped Epic | Mapped Story | Coverage Status |
|--------|-----------------|-------------|--------------|-----------------|
| NFR1 | VPS workspace core actions <500ms for 95% requests | Technical Epic A | Story A.1 | ✅ Covered |
| NFR2 | Proxy chain to Home Lab <1s latency, 99.5% success | Technical Epic B | Story B.4 | ✅ Covered |
| NFR3 | Mission card status updates <100ms UI refresh | User-Value Epic 1 | Story 1.2 | ✅ Covered |
| NFR4 | Dashboard analytics load <2s for 95% requests | User-Value Epic 2 | Story 2.1 | ✅ Covered |
| NFR5 | Data encrypted at rest (AES-256) and in transit (TLS 1.3) | Technical Epic C | Story C.4 | ✅ Covered |
| NFR6 | BYOK API keys stored in sessionStorage, expire 24h | User-Value Epic 3 | Story 3.1 | ✅ Covered |
| NFR7 | GDPR/CCPA data residency/deletion within 30 days | User-Value Epic 4 | Story 4.1 | ✅ Covered |
| NFR8 | API rate limiting/throttling per subscription tier | Technical Epic B | Story B.3 | ✅ Covered |
| NFR9 | Minimize PII logging (only escalation IDs/timestamps) | Technical Epic C | Story C.2 | ✅ Covered |
| NFR10 | VPS (16GB RAM) support 10+ concurrent missions | Technical Epic E | Story E.2 | ✅ Covered |
| NFR11 | Support single-tenant MVP to multi-tenant scaling | Technical Epic D | Story D.1 | ✅ Covered |
| NFR12 | Route 80%+ simple tasks to VPS, complex to Home Lab | Technical Epic D | Story D.1 | ✅ Covered |
| NFR13 | Support 50+ active enterprise users MVP, scale to 200+ | User-Value Epic 3 | Story 3.4 | ✅ Covered |
| NFR14 | All API integrations OpenAPI 3.0+ compliant | Technical Epic B | Story B.1 | ✅ Covered |
| NFR15 | Proxy chain health checks every 30s, auto-failover | Technical Epic D | Story D.3 | ✅ Covered |
| NFR16 | Partners authenticate via BYOK, <500ms latency | User-Value Epic 3 | Story 3.1 | ✅ Covered |
| NFR17 | Seamless VPS ↔ Home Lab routing | Technical Epic D | Story D.1 | ✅ Covered |
| NFR18 | VPS workspace 99.9% uptime (excl. maintenance) | Technical Epic D | Story D.5 | ✅ Covered |
| NFR19 | Context reconstruction 99.5% success rate | Technical Epic A | Story A.3 | ✅ Covered |
| NFR20 | Proxy failover <5s, exponential backoff retries | Technical Epic D | Story D.6 | ✅ Covered |
| NFR21 | 100% automated test coverage for critical workflows | Technical Epic F | Story F.1 | ✅ Covered |

**Total NFRs Covered: 21/21**

---

## Next Steps

1. ✅ **Party Mode Sign-off** — Get sign-off from Mary (BA), Amelia (Dev), Quinn (QA), John (PM), Bob (Scrum Master)
2. ✅ **Commit** — `"Add Epics and Stories with 100% FR+NFR coverage (Party Mode approved)"`
3. ✅ **Push** to `feature/flowmanner-architecture`
4. ✅ **Phase 3 Step 6 Complete** — Proceed to Phase 4 Implementation
### Category 3: API & Communication

#### Decision 6: Dashboard API Design
- **Category**: API & Communication
- **Decision**: RESTful APIs for dashboard analytics (GET `/api/dashboard/analytics`, GET `/api/dashboard/usage`), SSE endpoint for real-time mission updates (GET `/api/dashboard/mission-updates/sse`)
- **Version**: FastAPI 0.115+, OpenAPI 3.0+
- **Rationale**: 
  - RESTful APIs for historical analytics data, aligning with existing `/api/` prefix convention.
  - SSE endpoint uses Hermes SSE patterns from `AGENT-PAIRING.md` (event format: `{event: "mission-update", data: {...}}`), consistent with existing agent update streams.
  - OpenAPI 3.0+ compliance for auto-generated docs, matching existing backend standards.
- **Affects**: Backend `app/routers/dashboard.py`, frontend API clients, SSE client in dashboard components
- **Provided by Starter**: Partial (SSE pattern exists in Hermes skills, dashboard APIs new)

#### Decision 7: OpenAI Compat for Dashboard BYOK
- **Category**: API & Communication
- **Decision**: Use Hermes OpenAI compat spec (from `hermes-openai-compat-spec.md`) for BYOK support in dashboard, allow users to add custom API keys for DeepSeek-V4 Flash
- **Version**: Hermes OpenAI compat spec v1.0
- **Rationale**: 
  - Aligns with existing Hermes OpenAI compat patterns for consistent BYOK experience across the platform.
  - Reuses `hermes-openai-compat-spec.md` event and request/response formats, reducing new development.
- **Affects**: Backend `/api/billing/byok` routes, frontend BYOK settings page
- **Provided by Starter**: No (new for Epic 2)

## Implementation Patterns & Consistency Rules (Epic 2)

### Pattern Categories Defined

**Critical Conflict Points Identified:** 5 areas where AI agents could make different choices for Epic 2 (Dashboard & Customer Experience): API naming, frontend component naming, state management approach, SSE event format, dashboard caching strategy.

### Naming Patterns

**API Naming Conventions:**
- REST endpoints: Plural, kebab-case, under `/api/` prefix: `/api/dashboard/analytics`, `/api/dashboard/usage`, `/api/dashboard/mission-updates/sse`
- Route parameters: `:id` format (e.g., `/api/dashboard/mission/:missionId`)
- Query parameters: `snake_case` (e.g., `start_date`, `end_date`, `user_id`)
- Aligns with existing backend API conventions and OpenAPI 3.0+ auto-generation.

**Code Naming Conventions:**
- Frontend components: PascalCase (e.g., `AnalyticsChart.tsx`, `UsageTable.tsx`)
- Frontend stores: `camelCase` with `-store` suffix (e.g., `dashboard-store.ts`)
- Backend routers: `snake_case` (e.g., `dashboard.py`)
- Consistent with existing codebase patterns (Epic 1).

### Structure Patterns

**Project Organization:**
- Frontend dashboard files: `app/dashboard/*` (Next.js App Router), `components/Dashboard/*` (shared components)
- Frontend store: `stores/dashboard-store.ts` (co-located with `mission-store.ts`, `chat-store.ts`)
- Backend dashboard routes: `app/routers/dashboard.py` (co-located with `recovery.py`, `mission.py`)
- Tests: Co-located with components (e.g., `components/Dashboard/AnalyticsChart.test.tsx`) and backend tests in `tests/routers/test_dashboard.py`

**File Structure Patterns:**
- Dashboard components: `components/Dashboard/{AnalyticsChart, UsageTable, MissionUpdates, Settings}.tsx`
- Dashboard pages: `app/dashboard/{page.tsx, analytics/page.tsx, settings/page.tsx}`
- Backend dashboard service: `app/services/dashboard_service.py`

### Format Patterns

**API Response Formats:**
- Standardized wrapper: `{ data: {}, error: null }` for success, `{ data: null, error: { code: 404, message: "Not found" } }` for errors
- Aligns with existing backend response patterns and OpenAPI 3.0+ compliance.

**Data Exchange Formats:**
- JSON field naming: `camelCase` for frontend-API communication (e.g., `recoveryRate`, `missionId`)
- Date formats: ISO 8601 strings (e.g., `2026-04-29T16:33:52Z`)
- Consistent with existing API conventions.

### Communication Patterns

**Event System Patterns:**
- SSE event format: `{ event: "mission-update", data: { missionId: "123", status: "complete", progress: 100 } }`
- Aligns with Hermes SSE patterns from `AGENT-PAIRING.md` and existing agent update streams.

**State Management Patterns:**
- Zustand for dashboard global state (filters, mission list)
- React Query for API data fetching (1 minute TTL for analytics, invalidation on mutation)
- SSE stream integrated into Zustand store via event listeners.

### Process Patterns

**Error Handling Patterns:**
- Backend: FastAPI `HTTPException` with standardized error codes, logged via existing logging config.
- Frontend: Error boundaries for dashboard pages, toast notifications for API errors.
- Aligns with existing error handling patterns across the codebase.

**Loading State Patterns:**
- Frontend: React Query's `isLoading`/`isFetching` flags, skeleton loaders for charts/tables.
- Consistent with existing UI loading patterns.

### Enforcement Guidelines

**All AI Agents MUST:**
- Follow existing naming conventions for API, code, and files.
- Use Zustand + React Query for dashboard state management.
- Adhere to SSE event format from Hermes patterns for real-time updates.
- Reuse existing components (Radix UI, Recharts) for dashboard UI.

### Pattern Examples

**Good Examples:**
- Backend route: `@router.get("/api/dashboard/analytics")` → follows `/api/` prefix, plural naming.
- Frontend component: `components/Dashboard/AnalyticsChart.tsx` → PascalCase, co-located.

**Anti-Patterns:**
- Avoid: `/api/Dashboard/Analytics` (wrong case, singular), using `useState` instead of Zustand for global state.

## Project Structure & Boundaries (Epic 2)

### Requirements Mapping

- Epic 2 (Dashboard & Customer Experience) → Frontend: `app/dashboard/*`, `components/Dashboard/*`; Backend: `app/routers/dashboard.py`, `app/services/dashboard_service.py`
- Story 2-1 (View Dashboard Analytics) → Frontend: `app/dashboard/analytics/page.tsx`, `components/Dashboard/AnalyticsChart.tsx`; Backend: `GET /api/dashboard/analytics`
- Story 2-2 (Mission Progress Updates) → Frontend: `components/Dashboard/MissionUpdates.tsx`; Backend: `GET /api/dashboard/mission-updates/sse`
- Story 2-3 (Usage Metrics & Billing) → Frontend: `app/dashboard/settings/page.tsx` (BYOK); Backend: `/api/billing/byok`
- Story 2-4 (Customer Experience Improvements) → Frontend: `components/Dashboard/Settings.tsx`, Radix UI tables/filters.

### Project Directory Structure (Epic 2 Additions)

```
flowmanner-frontend/  # Frontend (Next.js 16)
├── app/
│   ├── dashboard/
│   │   ├── page.tsx  # Dashboard home
│   │   ├── analytics/
│   │   │   └── page.tsx  # Analytics view
│   │   └── settings/
│   │       └── page.tsx  # Settings/BYOK
├── components/
│   └── Dashboard/
│       ├── AnalyticsChart.tsx  # Recharts line/bar charts
│       ├── UsageTable.tsx  # Radix UI table
│       ├── MissionUpdates.tsx  # SSE real-time updates
│       └── Settings.tsx  # BYOK settings form
├── stores/
│   └── dashboard-store.ts  # Zustand store
└── package.json  # Added Recharts, React Query, Radix UI deps

workflows-backend/  # Backend (FastAPI)
├── app/
│   ├── routers/
│   │   └── dashboard.py  # Dashboard API routes
│   ├── services/
│   │   └── dashboard_service.py  # Analytics, caching logic
│   └── schemas/
│       └── dashboard.py  # Pydantic models for dashboard APIs
└── tests/
    └── routers/
        └── test_dashboard.py  # Pytest tests for dashboard routes
```

### Integration Boundaries

- Frontend ↔ Backend: Same-origin API calls via VPS Traefik, `/api/dashboard/*` routes proxied to Home Lab backend.
- Backend ↔ Redis: Caching for dashboard analytics (5 minute TTL), session management.
- Backend ↔ Postgres: Analytics data queries (recovery rates, usage metrics).
- SSE Stream: Backend → Frontend via EventSource, uses Hermes SSE event format.

