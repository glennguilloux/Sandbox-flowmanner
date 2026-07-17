# Your task — Product Manager (lens: PRIORITIZE / "what is highest value-to-effort")

First read `/opt/flowmanner/.sisyphus/swarm-audit-2026-07-17/BRIEF.md`. Adopt your
injected persona's identity, then do this:

**The question you own:** Of everything Flowmanner CAN do, what should Glenn ship
next for the best value-to-effort, and what is built-but-unshipped? You prioritize.

Suggested angles (evidence with `path:line` or file references):
- Feature completeness vs reality: which of the 60+ endpoint modules are real vs
  stubs? (The reality-checker persona verifies this — you prioritize the result.)
- The `marketplace`, `community`, `changelog`, `roadmap` platform modules —
  are they live revenue surfaces or skeletons?
- `seed_templates.py` (267 KB mission catalog) — how rich is the built-in value?
  Is it surfaced to users?
- Personas/agents (`agent_definitions`, 215 of them) as a product: is the
  multi-agent/persona capability a headline feature or buried?
- Onboarding: what does a brand-new user actually experience? Trace
  `backend/app/api/v1/` onboarding/auth flows; is there a clear first-run.

**Deliverable:** top 5 prioritization findings (fact vs rec, evidence),
the single biggest "built but unshipped / mispriced" gap, 3 ranked brainstorm
recs with RICE-style rationale (idea, why now, effort S/M/L, anchor). Write to
`.sisyphus/swarm-audit-2026-07-17/product-manager.md` and return a one-line
headline. READ-ONLY — no edits.
