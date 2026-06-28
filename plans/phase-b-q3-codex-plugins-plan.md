# Phase B (Q3 2026) — Codex Plugins Adoption Plan

**Date:** 2026-06-28
**Status:** Planned (not started)
**Prerequisite:** Phase A complete (Tricks 2, 4, 7, 11, 16, 17 — committed as `2dff954`)
**Constraint:** 1-person team, self-hosted homelab, llama.cpp Qwen3.6-27B (32k context)

---

## Overview

Phase B covers the three "Defer to Q3" items from the adoption plan:

| # | Trick | Effort | User Value | Dependencies |
|---|-------|--------|------------|--------------|
| 3 | Cross-Skill `references/` | S (< 1 day) | Low | None |
| 1 | `$phase` Orchestration | M (1–3 days) | Medium | Phase A incremental-execution.md |
| 9 | Default/Seed Prompts | M (1–3 days) | High | Frontend repo access |

**Recommended order:** 3 → 1 → 9 (quick win → reliability improvement → cross-repo UI work)

---

## Trick 3: Cross-Skill `references/` Directory

**Effort:** < 1 day
**Risk:** Low

### What

Create `.hermes/skills/references/` for shared reference documents that multiple skills can link to, avoiding context duplication.

### Why

FlowManner has 20+ integrations (Slack, GitHub, Notion, Linear, etc.) that share common patterns:
- OAuth flow (scopes, callback URL, token refresh)
- Pagination patterns (cursor-based, offset-based)
- Rate limiting (429 handling, backoff)
- Webhook registration

Currently each integration skill would duplicate these patterns. A shared reference saves tokens.

### Implementation

**Step 1:** Create `.hermes/skills/references/oauth-flow.md` — the shared OAuth reference:
```markdown
# OAuth Flow Reference
## Standard FlowManner OAuth Pattern
1. User initiates from Settings → Integrations → Connect
2. Backend builds auth URL with client_id, redirect_uri, scopes
3. User authorizes in provider's UI
4. Provider redirects to callback with auth code
5. Backend exchanges code for access_token + refresh_token
6. Tokens stored in `integration_credentials` table
7. Token refresh happens automatically on 401

## Common Scopes Pattern
- Read-only: `<service>:read`
- Read-write: `<service>:read`, `<service>:write`
- Admin: `<service>:admin` (avoid unless necessary)

## Error Handling
- 401 → attempt token refresh once, then re-auth prompt
- 403 → stop (see guardrails.md — no retry)
- 429 → respect Retry-After header, max 1 retry
```

**Step 2:** Create `.hermes/skills/references/webhook-patterns.md` — shared webhook reference.

**Step 3:** In existing/future integration skills, add a dependency line:
```markdown
> **Dependency:** Read `.hermes/skills/references/oauth-flow.md` before modifying auth code.
```

### Risks

- **Context bloat:** If the LLM auto-reads all references, it wastes tokens. **Mitigation:** Only link references when the task specifically touches that area. Use conditional phrasing: "If modifying auth code, read the reference first."
- **Stale references:** If the OAuth flow changes and the reference isn't updated, skills will give wrong guidance. **Mitigation:** Add a `Last updated:` date to each reference file.

---

## Trick 1: `$phase` Orchestration

**Effort:** 1–3 days (mostly observe/iterate with llama.cpp)
**Risk:** Medium

### What

Add explicit phase markers to complex skill files so the 27B model can track where it is in a multi-step workflow. Think of it as structured checkpoints within a SKILL.md.

### Why

Phase A's `incremental-execution.md` enforces "one step at a time" but doesn't tell the agent *which phase* it's in. For complex workflows (deploy with migration + validation + rollback), the agent can lose track of whether it's in the "preflight," "execution," or "validation" phase — especially after a context reset.

### Granularity

**Exactly 3 phases.** More than 3 confuses 27B models. Fewer adds no value over incremental-execution.md.

### Implementation

**Step 1:** Create `.hermes/skills/deploy-orchestration.md` with `$phase` markers:

```markdown
# Deploy Orchestration

## Execution Phases

Always begin your response by stating the current phase.

### $phase: preflight
- Run `scripts/pre-deploy-check.sh`
- Verify `[PREFLIGHT: READY]` token in output
- If `[PREFLIGHT: BLOCKED]`, stop and report the failed checks
- Check for `[ESCALATION REQUIRED]` tokens
- **Exit criteria:** All checks pass, no blockers

### $phase: execution
- Run the deploy command (`deploy-backend.sh` or `deploy-frontend.sh`)
- One command only — do NOT chain migrate + deploy
- If `--migrate`: run deploy first, then migrations separately
- **Exit criteria:** Containers recreated, health check passes

### $phase: validation
- Verify health endpoint returns 200
- Check container logs for errors
- If migrations ran: verify alembic head matches expected
- **Exit criteria:** System is healthy and stable

## Rules
- Never skip a phase
- If a phase fails, stop and do not proceed to the next phase
- On context reset, re-read this file and determine which phase to resume
```

**Step 2:** Test with 3 real scenarios on llama.cpp:
1. Simple deploy (no migration) — does the agent follow all 3 phases?
2. Deploy with migration — does it separate deploy from migrate?
3. Simulated failure in phase 2 — does it stop and not proceed to phase 3?

**Step 3:** Iterate on phase names and exit criteria based on what the 27B model actually follows.

### Risks

- **Format hallucination:** Qwen-27B might forget to emit `$phase` or hallucinate a 4th phase. **Mitigation:** Combine with Phase A incremental-execution.md. The `$phase` is a tracking aid, not a gate — the real enforcement is "one step at a time."
- **Phase confusion after context reset:** The agent might resume in the wrong phase. **Mitigation:** Add explicit "on context reset" instructions to re-read the skill file.
- **Diminishing returns:** For simple tasks, `$phase` adds overhead without value. **Mitigation:** Only use `$phase` for deploy/migration workflows, not for routine edits.

---

## Trick 9: Default/Seed Prompts

**Effort:** 1–3 days (heavy part is frontend UI)
**Risk:** Medium

### What

Add `default_prompts` to plugin manifests so users see clickable suggestion chips when they install a plugin — solving the "blank page" problem.

### Why

When a user installs a plugin, they don't know what to do with it. Seed prompts give them a starting point: "Try asking me to [X]."

### Implementation

**Phase 9a: Backend (manifest + API) — 0.5 days**

1. Add field to `PluginManifest` in `backend/app/sdk/manifest.py`:
```python
default_prompts: list[str] = Field(
    default_factory=list,
    max_length=3,
    description="Suggested prompts shown to the user after plugin install (max 3, each ≤ 200 chars)",
)
```

2. Add `@field_validator` for prompt length:
```python
@field_validator("default_prompts")
@classmethod
def validate_default_prompts(cls, v: list[str]) -> list[str]:
    if len(v) > 3:
        raise ValueError("Maximum 3 default_prompts allowed")
    for i, prompt in enumerate(v):
        if len(prompt) > 200:
            raise ValueError(f"default_prompts[{i}] exceeds 200 characters")
    return v
```

3. Add to `PluginResponse` in `backend/app/api/v1/plugins.py`:
```python
default_prompts: list[str] = []
```

4. Map in `_to_plugin_response()`:
```python
default_prompts=[],
# (populated from manifest_json when available)
```

5. Update tests in `backend/tests/test_plugin_manifest.py`.

**Phase 9b: Frontend UI — 1–2 days**

> ⚠️ This requires working in the frontend repo at `/home/glenn/FlowmannerV2-frontend/`.

1. Update TypeScript types for `PluginResponse` to include `default_prompts: string[]`
2. In the chat UI component, render seed prompts as clickable chips:
   - Show when: plugin is active AND chat is empty (no messages yet)
   - Style: pill-shaped buttons below the chat input
   - Click behavior: populate the chat input with the prompt text
3. Wire up the plugin API client to pass `default_prompts` through

### Backward Compatibility

- `default_prompts` has `default_factory=list` → existing manifests without the field get `[]`
- `extra="forbid"` is already on `PluginManifest` → the new field is declared, not extra
- No migration needed — it's an additive Pydantic field
- No DB schema change — `default_prompts` can be stored in the existing `manifest_json` column

### Risks

- **Frontend scope creep:** The chat UI component may be complex. **Mitigation:** Start with a minimal implementation (just chips, no animations). Polish later.
- **Stale prompts:** If a plugin's capabilities change but prompts don't, users get misleading suggestions. **Mitigation:** Max 3 prompts, keep them generic.
- **Context window cost:** If prompts are displayed inline in the chat, they consume tokens. **Mitigation:** Prompts are UI-only — they populate the input box, not the system prompt.

---

## Implementation Timeline

| Week | Trick | Deliverable |
|------|-------|-------------|
| Week 1 | 3 | `.hermes/skills/references/oauth-flow.md` + `webhook-patterns.md` |
| Week 2 | 1 | `.hermes/skills/deploy-orchestration.md` with `$phase` markers + 3 test scenarios |
| Week 3–4 | 9a | `PluginManifest.default_prompts` field + API response + tests |
| Week 4–5 | 9b | Frontend seed prompt chips in chat UI |

---

## Success Criteria

- [ ] Trick 3: At least 2 reference files created, referenced by at least 1 skill
- [ ] Trick 1: Deploy orchestration skill with 3 phases tested on llama.cpp
- [ ] Trick 9a: `default_prompts` field in manifest, API returns it, tests pass
- [ ] Trick 9b: Seed prompt chips visible in chat UI after plugin install
