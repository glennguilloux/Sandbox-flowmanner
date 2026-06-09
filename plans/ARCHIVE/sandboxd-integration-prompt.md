# FlowManner x sandboxd Integration — Deep-Dive Brainstorm for DeepSeek

> Hand this prompt to DeepSeek (exec --auto mode) to get a comprehensive think-out-loud roadmap report.

---

## Prompt for DeepSeek

### Context

FlowManner is an AI workflow/agent platform (FastAPI + Next.js). Users create "Missions" that are tasks for AI agents, build DAG-based workflows that chain LLM calls with tool execution, and interact via chat. It runs on a single homelab server (i7-11700K, 62GB RAM, 2x RTX 5060 Ti) with a cheap IONOS VPS for the frontend.

We just installed **sandboxd** (https://github.com/tastyeffectco/sandboxd) on the homelab. sandboxd provides on-demand Docker sandbox containers per user/session, each with its own isolated Linux environment, live preview URLs via Traefik, AI coding agents (OpenCode, Claude Code) pre-installed, stop-on-idle + wake-on-request, and a full REST API for lifecycle, file I/O, command execution, and agent task submission.

**The key question:** What is the highest-impact integration roadmap for bringing sandboxd's capabilities into FlowManner? We need a phased plan that a solo founder can execute, starting with features that differentiate FlowManner from generic chat UIs.

### Current Architecture (What Exists)

#### Backend (FastAPI, Python 3.11)
Location: `/opt/flowmanner/backend/app/`

| Area | Key Files | Purpose |
|------|-----------|---------|
| **Entry point** | `main_fastapi.py` | FastAPI app, middleware stack |
| **API v1** | `api/v1/` (72 modules) | All REST endpoints |
| **Services** | `services/` (82 files) | Business logic layer |
| **Models** | `models/` (47 files) | SQLAlchemy ORM models |
| **Tools** | `tools/` (110+ files) | Agent tools (BaseTool subclasses) |
| **Tasks** | `tasks/celery_app.py` | Celery background jobs |
| **Missions** | `models/mission_models.py` | Mission, MissionTask, MissionLog |
| **Workflows** | `models/graph.py` | Workflow, WorkflowExecution, WorkflowState (DAG) |
| **Agents** | `services/agent_service.py`, `agent_registry_service.py` | Agent management |
| **Chat** | `services/chat_service.py` | Chat interactions |
| **Browser** | `services/browser_service.py`, `services/browser_manager.py` | Browser automation |
| **Sandbox (existing)** | `tools/python_sandbox.py`, `tools/nodejs_sandbox.py` | Subprocess-based code execution with rlimits |

#### Existing Sandbox Tools (subprocess-based, NOT Docker)
- `python_sandbox.py`: Runs Python in subprocess with import denylist, memory/timeout limits via rlimits. Blocked: subprocess, socket, requests, pickle, etc.
- `nodejs_sandbox.py`: Runs Node.js in subprocess with require denylist. Blocked: child_process, net, tls, etc.
- Both use `_rlimits.py` for resource limits (memory ceiling, max processes)
- **Limitation**: These are process-level isolation only. No filesystem isolation, no network isolation, no persistent workspace, no preview URLs.

#### Frontend (Next.js/TypeScript)
Location: `/home/glenn/FlowmannerV2-frontend/`

| Route | Purpose |
|-------|---------|
| `/[locale]/dashboard/` | Main dashboard |
| `/[locale]/dashboard/evaluation/` | Agent evaluation |
| `/[locale]/dashboard/swarm/` | Multi-agent swarm |
| `/[locale]/dashboard/settings/` | User settings |
| `/[locale]/agents/` | Agent management |
| `/[locale]/knowledge/` | Knowledge base |
| `/[locale]/integrations/` | Integrations |
| `/[locale]/mission-dashboard/` | Mission overview |

#### Infrastructure
- Homelab: FastAPI + PostgreSQL + Redis + Qdrant + RabbitMQ + Celery + Jaeger + llama.cpp
- VPS (74.208.115.142): Nginx -> WireGuard -> Homelab. Serves Next.js frontend.
- DNS: flowmanner.com + www.flowmanner.com -> VPS
- Deploy: `deploy-frontend.sh` (~4min) and `deploy-backend.sh` (~2min)

#### sandboxd (just installed)
- Control plane API: `http://127.0.0.1:9090`
- Preview URLs: `http://s-<id>-<port>.preview.localhost`
- Data dir: `/var/lib/sandboxed`
- Base image: `sandboxd-base:1.0.0` (449MB, includes Node 20, Python 3, Go, Bun, pnpm, uv, Claude Code, OpenCode)
- Key APIs: POST /sandbox (create), POST /sandbox/{id}/exec, POST /v1/sandboxes/{id}/tasks (agent task), GET/PUT files, SSE events, stop/start/purge

### What to Think About

#### 1. Replace vs Extend the Existing Sandboxes
FlowManner already has `python_sandbox.py` and `nodejs_sandbox.py` that run code in subprocesses with rlimits. sandboxd offers full Docker isolation with persistent workspaces, preview URLs, and agent tasks.

- Should sandboxd *replace* the existing subprocess sandboxes entirely, or coexist alongside them?
- What's the migration path? The existing tools are registered in the tool system and agents already use them.
- Are there cases where subprocess execution is actually preferred (speed, no Docker overhead)?

#### 2. Agent Tool Integration
FlowManner agents use a tool system (`BaseTool` subclasses registered via `register_tool`). The brainstorm identified several new tools:
- `sandbox_exec` — run code in an isolated Docker container
- `sandbox_write_file` — write files to a sandbox workspace
- `sandbox_read_file` — read files from a sandbox workspace
- `sandbox_preview` — get the live preview URL for a sandbox

- How should these relate to the existing `python_sandbox` and `nodejs_sandbox` tools?
- Should there be a single `sandbox` tool that handles all operations, or multiple specialized tools?
- How does sandbox lifecycle map to mission lifecycle? Create on mission start, destroy on completion?

#### 3. Live Preview URLs for Mission Outputs
When an agent builds a web app, the user gets a clickable live preview URL instead of just a code block.

- Where does the preview URL surface in the chat UI? As a button? An iframe embed? Both?
- How do preview URLs work through the VPS -> WireGuard -> Homelab path? Currently sandboxd previews are on `*.preview.localhost` — they'd need to be accessible from the user's browser via flowmanner.com.
- What's the routing: `s-<id>-3000.preview.flowmanner.com` -> VPS Nginx -> sandboxd Traefik?
- TLS for preview URLs? sandboxd supports Let's Encrypt wildcard certs.
- Sandbox TTL: how long does a sandbox live after the mission completes?

#### 4. Workflow DAG Integration
FlowManner has a workflow engine with DAG execution (Workflow -> WorkflowExecution -> WorkflowState per node).

- What would a "Sandbox Node" type look like in the DAG?
- How does data flow in/out? Node input -> sandbox exec -> node output?
- Can a workflow have multiple sandbox nodes that share a workspace, or should each be independent?
- How do you visualize sandbox state (building, running, error) in the workflow UI?

#### 5. The Agent Playground (Growth Funnel)
A public-facing page where visitors describe an app and get a working prototype in 60 seconds.

- Route: `/playground` or `/build`
- How does rate limiting work? Per IP for anonymous, per user for signed-in?
- Should the playground use the same agent system or a simplified direct sandboxd task?
- What's the conversion funnel: playground demo -> sign up -> save sandbox -> paid plan?
- Cost control: each playground build spins up a Docker container. What are the resource implications for the homelab with 62GB RAM?

#### 6. Multi-User Sandbox Workspaces
Each FlowManner workspace gets a persistent sandbox for team collaboration.

- How does sandboxd's container-per-sandbox model map to FlowManner's workspace model?
- Wake-on-request is perfect for this — the sandbox sleeps when the team isn't active.
- File browser UI: how to render the sandbox filesystem in the FlowManner dashboard?
- Permission model: who can access/modify the workspace sandbox?

#### 7. Resource Management on a Single Server
The homelab has 62GB RAM. sandboxd containers have memory ceilings and idle reaping.

- How many concurrent sandboxes can the homelab realistically handle?
- What's the memory budget per sandbox? How does that coexist with the existing Docker stack (PostgreSQL, Redis, Qdrant, RabbitMQ, backend, Celery, Jaeger)?
- Should sandboxd run on a separate machine eventually, or is the homelab sufficient for early-stage?
- What monitoring/alerting is needed?

### Output Format

Produce a **phased roadmap document** saved to `/opt/flowmanner/plans/sandboxd-integration-roadmap.md` with:

1. **Executive Summary** — What we're building and why, in 3 sentences
2. **Architecture Decision Records** — Key decisions (replace vs extend, routing, lifecycle)
3. **Phase 1: Foundation** (1-2 weeks) — The minimum viable integration
   - Concrete tasks with file paths
   - API design (new endpoints, new tools)
   - Frontend changes
   - Verification steps
4. **Phase 2: Live Previews** (2-3 weeks) — The "wow" feature
   - Routing through VPS
   - TLS setup
   - Frontend preview components
5. **Phase 3: Workflow Integration** (3-4 weeks) — Power user features
   - Sandbox node in DAG
   - Data flow design
   - Visualization
6. **Phase 4: Growth** (4-6 weeks) — Playground and workspaces
   - Public playground page
   - Team sandbox workspaces
   - Rate limiting and cost control
7. **Resource Budget** — Memory, CPU, disk calculations for the homelab
8. **Risks and Open Questions**

**Be bold. Be opinionated. Don't hedge. Show your reasoning. Think out loud.**
**This is a roadmap for a solo founder — be realistic about timelines but ambitious about vision.**
**Respond in English.**
