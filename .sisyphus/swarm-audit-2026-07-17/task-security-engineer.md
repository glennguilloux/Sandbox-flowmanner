# Your task — Security Engineer (lens: VERIFY / "what breaks under an attacker")

First read `/opt/flowmanner/.sisyphus/swarm-audit-2026-07-17/BRIEF.md`. Adopt your
injected persona's identity, then do this:

**The question you own:** Where is Flowmanner's attack surface and what would an
adversary exploit first? You threat-model the whole stack.

Suggested angles (verify with `path:line`):
- Auth chain: JWT (`backend/app/core/security.py`?), 2FA (pyotp), API keys
  (`api_keys.py`), OIDC. Any hardcoded secrets, weak alg, missing expiry checks?
- WebSocket `/ws` auth + tenant isolation — is every subscribe authorized and
  tenant-scoped? (There are dedicated enforcement rules for this in the repo's
  skills.)
- Multi-tenant data isolation: can one tenant read another's missions/agents/
  memory? Search `backend/app/models/` and queries for tenant_id filtering.
- Input validation on the 60+ endpoints — Pydantic coverage vs raw dict access.
- Agent memory / LLM routing: prompt-injection exposure where external content
  flows into agent prompts (RAG, webhooks, integrations).
- Secrets in `.env`, docker-compose, `mcp_gateway/client_config.json`.

**Deliverable:** top 5 security findings (facts, `path:line`, severity),
the single biggest exploitable gap, 3 ranked brainstorm recs (idea, why now,
effort, file:line anchor). Focus on REAL issues you can evidence. Write to
`.sisyphus/swarm-audit-2026-07-17/engineering-security-engineer.md` and return a
one-line headline. READ-ONLY — no edits.
