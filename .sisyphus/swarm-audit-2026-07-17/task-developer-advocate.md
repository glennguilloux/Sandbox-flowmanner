# Your task — Developer Advocate (lens: PITCH / "what is the best untold story")

First read `/opt/flowmanner/.sisyphus/swarm-audit-2026-07-17/BRIEF.md`. Adopt your
injected persona's identity, then do this:

**The question you own:** If you had 10 minutes with a developer or a potential
customer, what is the single most compelling, UNDERTOLD story Flowmanner can tell
— and what demo would prove it? You are the narrative + community lens.

Suggested angles (evidence with `path:line` / file refs):
- The persona/agent system: 215 expert personas + a multi-agent swarm — that is
  a killer story. Is it documented/shown? Read `agent_definitions`, `swarm.py`,
  `templates/README.md`.
- "Compose AI agents into workflows" — find the clearest end-to-end example in
  the codebase (a real mission template in `seed_templates.py`?).
- Differentiators vs Zapier/Make/n8n/LangChain: where does Flowmanner clearly win
  in code (e.g. the autonomous harness-evolution loop, the persona library)?
- Docs/community surface: `docs/`, `changelog`, `roadmap`, `community` modules —
  is there a story engine?
- A 5-minute demo script a developer could run today (ground it in real endpoints
  in `openapi.json`).

**Deliverable:** top 5 "untold story" findings (fact vs rec, evidence), the
single best demo hook, 3 ranked brainstorm recs (idea, why now, effort, anchor) —
favor: write the narrative, build the demo, ship the docs. Write to
`.sisyphus/swarm-audit-2026-07-17/specialized-developer-advocate.md` and return a
one-line headline. READ-ONLY — no edits.
