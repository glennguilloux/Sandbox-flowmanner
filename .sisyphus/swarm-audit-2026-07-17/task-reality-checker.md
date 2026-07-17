# Your task — Reality Checker (lens: VERIFY-CLAIMS / "is it real or fool's gold")

First read `/opt/flowmanner/.sisyphus/swarm-audit-2026-07-17/BRIEF.md`. Adopt your
injected persona's identity, then do this — translated to SOURCE verification:

**The question you own:** The other experts will be optimistic. Your job is the
honesty gate: separate what-is-real from what-is-stub/fake/aspirational. Default
to "NEEDS WORK" and require overwhelming evidence to certify.

Suggested angles (verify with `path:line`, REQUIRE actual code, not doc claims):
- For 6–8 of the highest-profile endpoint modules (e.g. `swarm.py`,
  `marketplace.py`, `rag.py`, `agent.py`, `mission.py`, `templates.py`,
  `webhooks.py`, `triggers.py`): open the file. Is there a real handler wired to
  a router, or `raise NotImplementedError` / `pass` / TODO? Count real vs stub.
- The "autonomous harness evolution" / meta-optimizer: real loop or scaffold?
  Find it, read it, certify or reject.
- `seed_templates.py`: how many templates are actually valid vs placeholder?
- LLM routing (recent memory note: bare ids fall through to platform key, only
  llamacpp runs keyless) — is the catalog's "enabled:true" honest about what
  actually runs? Check `backend/app/services/llm_providers.py`.

**Deliverable:** a CERTIFY / NEEDS-WORK verdict per module you checked (with
`path:line` proof), the top 5 "fool's gold" risks, the single most dangerous
overclaim in the repo, 3 ranked recs (mostly: "finish X before marketing Y").
Write to `.sisyphus/swarm-audit-2026-07-17/testing-reality-checker.md` and return
a one-line headline. READ-ONLY — no edits.
