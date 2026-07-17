# Your task — Backend Architect (lens: COMPOSE / "how do the pieces assemble")

First read `/opt/flowmanner/.sisyphus/swarm-audit-2026-07-17/BRIEF.md` (the shared
brief with verified repo facts + output contract). Adopt your injected persona's
identity, then do this:

**The question you own:** How do Flowmanner's subsystems COMPOSE into a coherent
whole — and where do the seams leak? You are the architect: trace the assembly.

Suggested angles (verify with `path:line`, don't just assert):
- The `/api/v1/` → `/api/v2/` split: is v2 a clean evolution or a forked twin
  with drift? Read `backend/app/api/v1/` vs `backend/app/api/v2/`.
- Service-layer cohesion: does `backend/app/services/` have a clear boundary, or
  do routers reach into models directly? Sample `backend/app/api/v1/mission.py`
  and its service.
- The "substrate" / mission execution core (recent commits mention
  `substrate harness-evolution`, `churn_history`, Qdrant ingest). Where does the
  autonomous-evolution loop actually live? Trace `backend/app/` for the harness /
  meta-optimizer.
- WebSocket `/ws` + Socket.IO auth/tenant isolation (there are enforcement skills
  for this). Read `backend/app/websocket/` or equivalent.
- Cross-cutting infra: Alembic migrations, Celery tasks, middleware stack
  (`backend/app/api/middleware/`, `backend/app/middleware/`).

**Deliverable:** top 5 composition findings (facts, `path:line`), the single
biggest architectural blind spot, 3 ranked brainstorm recs (each: idea, why now,
effort S/M/L, file:line anchor). Write to
`.sisyphus/swarm-audit-2026-07-17/engineering-backend-architect.md` and return a
one-line headline. READ-ONLY — no edits.
