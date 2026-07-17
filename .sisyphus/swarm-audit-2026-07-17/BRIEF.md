# Flowmanner Multi-Expert Swarm Brief — "Analyze & Brainstorm"

**Date:** 2026-07-17 · **Author:** Hermes orchestrator (default profile)
**Method:** `persona-delegation` skill + `multi-expert-swarm-audit` recipe.
Each expert is a Flowmanner persona injected into a Kanban worker card
(`fmw1`/`fmw2`/`fmw3`). Read-only. No code changes, no build, no deploy.

## Mission
Flowmanner is a workflow-automation platform (think: orchestrate AI agents,
missions, swarms, integrations). Glenn, the owner, wants a **4-hour multi-angle
analysis + brainstorm**: where is the platform strong, where is it fragile, what
hidden value is unmonetized/unshipped, and what concrete next moves would move
the needle. You are ONE expert lens in a squad of six. Your job is NOT to write
the final report — it is to write YOUR expert ledger with file:line evidence, so
the synthesizer (an `fmw_synth` profile) can cross-reference all six.

## Verified repo facts (re-check; do not trust stale docs)
- **Repo root:** `/opt/flowmanner`. Backend source: `backend/` (~12.7M lines of
  Python across 42,083 `.py` files — a very large FastAPI codebase).
- **Architecture (3 machines):**
  - VPS `74.208.115.142` → Nginx :443 → frontend (Next.js) + API proxy.
  - Homelab `172.16.1.1` / `10.99.0.3` → backend FastAPI :8000, PostgreSQL,
    Redis, Qdrant, RabbitMQ, Celery, llama.cpp.
  - Ops/Dev `172.16.1.2`.
  - Internet → VPS `/api/*` → WireGuard → Homelab:8000. `/ws` WebSocket tunnel
    likewise.
- **Backend stack:** FastAPI 0.115, Uvicorn, SQLAlchemy 2.0 async + Alembic,
  Celery 5.3 + RabbitMQ, Redis, Qdrant (vector), LangChain, PyJWT + passlib +
  pyotp (2FA), Pydantic 2, OpenTelemetry→Jaeger, structlog, prometheus-client.
- **API surface:** 60+ endpoint modules under `/api/v1/`, plus a `/api/v2/`
  next-gen layer. Categories: auth, core (chat/agent/mission/graph/files),
  workspace, advanced (swarm/templates/triggers/webhooks), intelligence
  (llm/search/rag/memory), operations, platform (marketplace/community),
  integration, quality, admin.
- **215 expert personas** live in `backend/app/agent_definitions/**/*.md`
  (the same mechanism you are part of). A `seed_templates.py` (267 KB) holds the
  built-in mission template catalog.
- **OpenAPI spec:** `openapi.json` (1.3 MB) — the full contract surface.
- **Personas/agents themselves:** `backend/app/agent_definitions/` is the
  library that powers Flowmanner's own multi-agent "persona" feature.

## Active warnings (read before recommending anything deploy/auth-related)
- Memory stores are **per-machine** (agentmemory). Do not assume homelab memory
  is visible on VPS/ops.
- Frontend deploy ~4 min; backend rebuild ~2 min. Never edit VPS files directly;
  all edits on homelab, rebuild + deploy. Source edits need a rebuild (no volume
  mounts on backend container).

## Hard constraints for every worker
1. **READ-ONLY.** Do not edit, commit, push, build, or deploy. This is analysis.
2. Work in your assigned worktree only. Do not touch other workers' branches.
3. Every claim MUST cite `path:line` evidence (or a file + the function/module).
   No ungrounded opinions.
4. Respect your persona's own scope rules (e.g. a reviewer DOES NOT implement;
   an onboarding mapper states facts only). Brainstorming ideas are fine, but
   label them as recommendations, separate from observed facts.
5. Write your output to `.sisyphus/swarm-audit-2026-07-17/<your-slug>.md`
   (create the file in your worktree) and also return a one-line headline.

## OUTPUT CONTRACT (every expert)
Write a ledger with these sections:
- **Lens & question you own** (the one verb: catalog / verify / compose /
  prioritize / pitch / perceive).
- **Top 5 findings** — each with: observation, `path:line` evidence, severity
  (critical/high/medium/low), and whether it is fact vs recommendation.
- **Biggest single miss / blind spot** the platform currently has (your lens).
- **3 concrete brainstorm recommendations** specific to Flowmanner, ranked, each
  with: the idea, why now, rough effort (S/M/L), and the file:line anchor it
  would touch.
- **Confidence** (high/medium/low) and the single most important claim you want
  the synthesizer to cross-check.

Be specific. "SQL injection on line 42 of auth.py" beats "auth could be better."
