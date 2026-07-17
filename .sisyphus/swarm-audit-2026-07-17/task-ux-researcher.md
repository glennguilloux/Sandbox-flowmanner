# Your task — UX Researcher (lens: PERCEIVE / "what is built but unseen or unreachable")

First read `/opt/flowmanner/.sisyphus/swarm-audit-2026-07-17/BRIEF.md`. Adopt your
injected persona's identity, then do this:

**The question you own:** From a user's seat, where is the gap between what
Flowmanner offers and what a user can actually perceive/reach? Translate your
UX discipline to SOURCE evidence (you may not have a live UI — reason from the
API surface, schemas, and docs).

Suggested angles (evidence with `path:line` / file refs):
- API vs UI parity: `openapi.json` (1.3 MB) has 60+ modules — does the frontend
  actually surface them? (Frontend source is on homelab at
  `/home/glenn/FlowmannerV2-frontend/` — read it if present, else infer from
  backend.)
- New-user comprehension: is there documentation/a tour? Read `docs/`,
  `templates/README.md`, `ROADMAP-INDEX.md`.
- The agent/persona experience: is choosing among 215 personas guided or a
  wall of text? Check `backend/app/agent_definitions/` structure + any
  discovery endpoint.
- Error/empty states: what does the API return on common failures? (Read a
  schema or two in `backend/app/schemas/`.)

**Deliverable:** top 5 perception/reachability findings (fact vs rec, evidence),
the single biggest "built but invisible" gap, 3 ranked brainstorm recs (idea,
why now, effort, anchor). Write to
`.sisyphus/swarm-audit-2026-07-17/design-ux-researcher.md` and return a one-line
headline. READ-ONLY — no edits.
