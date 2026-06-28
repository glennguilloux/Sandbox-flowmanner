# Phase B (Q3 2026) — Codex Plugins Adoption Plan

**Date:** 2026-06-28
**Status:** Phase A complete + Phase B (Trick 9a) complete. Tricks 1, 3, 9b deferred.
**Prerequisite:** Phase A complete (Tricks 2, 4, 7, 11, 16, 17 — committed as `2dff954`)
**Constraint:** 1-person team, self-hosted homelab, llama.cpp Qwen3.6-27B (32k context)

---

## Session Status (2026-06-28 closeout)

### Completed in this session
- **Phase A (committed `2dff954`):** Tricks 2, 4, 7, 11, 16, 17 — all 6 "Adopt Now" items landed
- **Phase B / Trick 9a (committed `dcf5fae`):** Backend `default_prompts` field on `PluginManifest`, exposed in `PluginResponse`, 6 new tests (21/21 pass on host Python)
- **Doc commits (`c87bca5`):** This plan + the exit audit

### Deferred (out of scope for this session)
- **Trick 3 (Cross-Skill `references/`):** Skill files written locally to `.hermes/skills/references/` (gitignored). Adopting these as Hermes skills is a Hermes-side decision, not a code change.
- **Trick 1 (`$phase` Orchestration):** Skill file written locally to `.hermes/skills/deploy-orchestration.md` (gitignored). Tested manually with Qwen3.6-27B; results in the exit audit. Production rollout awaits Hermes skill-system support for `$phase:` parsing.
- **Trick 9b (Frontend seed prompt chips):** Lives in `/home/glenn/FlowmannerV2-frontend/`, separate repo. Backend now serves `default_prompts` so the frontend can consume it.

---

## Known Issue — Deploy-Script Health Check Timeout (post-deploy)

**Discovered:** 2026-06-28, immediately after committing `dcf5fae` and `c87bca5`.

### Symptom

The deploy script's post-recreate health-check loop reports:
```
[WARN]  Health check attempt 1/10 failed, retrying in 3s ...
...
[WARN]  Health check attempt 9/10 failed, retrying in 3s ...
[ERROR] Backend (post-recreate readiness) health check FAILED after 10 attempts
```

### Actual outcome

Despite the script error, the backend IS healthy. Verified post-deploy:
- `/health` returns HTTP 200 in ~4ms
- `/api/health` returns HTTP 200 in ~2ms
- `PluginResponse.default_prompts` field is present in the running Pydantic schema (default=`[]`)
- All 6 plugin routes are mounted at `/api/plugins/*`
- Application startup completed cleanly (uvicorn reports "Application startup complete")

### Root cause

The deploy script's health-check budget is **30 seconds** (10 attempts × 3s backoff). On cold start, `tool_discovery_service` loads the `all-MiniLM-L6-v2` sentence-transformers model, which takes ~19 seconds (see backend logs: "Load pretrained SentenceTransformer" → "Embedding model loaded" spans `17:04:26` → `17:04:45`). During this 19-second window, uvicorn is **not yet accepting requests**, so all 10 health probes time out. The script gives up at second 30 — and the embedding model finishes loading at second 22, with uvicorn starting to serve immediately after. The script's exit happens in the small window between "uvicorn started" and "next probe would have succeeded."

### Impact

- Deploys appear to fail in CI/notifications when they actually succeeded
- Operators may reflexively retry, wasting ~2 minutes per unnecessary retry
- Risk of accidental rollback if the operator assumes a real failure

### Proposed fix (NOT applied tonight)

Increase the health-check budget. Three options, in increasing order of effort:

1. **Quick fix:** Bump retries to 20 and backoff to 5s (100s total window, covers cold start with margin)
2. **Better fix:** Make retry count + backoff env-configurable (`DEPLOY_HEALTH_RETRIES`, `DEPLOY_HEALTH_BACKOFF_S`)
3. **Best fix:** Pre-warm the embedding model at Docker build time so cold start is fast (move `all-MiniLM-L6-v2` into the image layer)

### Recommended action for next session

Pursue option 1 or 2. Option 3 is a bigger change (Dockerfile + base image bump) and should be its own session if pursued.

---

## Overview — Original Phase B Plan (still relevant)

Phase B covers the three "Defer to Q3" items from the adoption plan:

| # | Trick | Effort | User Value | Dependencies |
|---|-------|--------|------------|--------------|
| 3 | Cross-Skill `references/` | S (< 1 day) | Low | None |
| 1 | `$phase` Orchestration | M (1–3 days) | Medium | Phase A incremental-execution.md |
| 9b | Default/Seed Prompts (frontend) | M (1–3 days) | High | Trick 9a (DONE — backend serves `default_prompts`) |

**Recommended order:** 9b → 3 → 1 (UI discovery → quick win → reliability improvement)

---

## Trick 9b: Frontend Seed Prompt Chips (NEXT PRIORITY)

**Effort:** 1–3 days
**Risk:** Low
**Repo:** `/home/glenn/FlowmannerV2-frontend/`

### What

When a user installs a plugin (or opens the marketplace listing for one), display the plugin's `default_prompts` as clickable chips in the chat input. Clicking a chip populates the chat input with that prompt.

### Backend contract (already shipped in `dcf5fae`)

`GET /api/plugins/{plugin_id}` returns:
```json
{
  "id": "...",
  "name": "json-transform",
  "default_prompts": ["Transform my JSON", "Map fields between objects", "..."],
  ...
}
```

Frontend can fetch this on the marketplace/install detail page.

### Success criteria
- [ ] Plugin detail page shows the `default_prompts` chips
- [ ] Clicking a chip populates the chat input
- [ ] Empty `default_prompts` → no chips rendered (graceful no-op)
- [ ] Chips respect existing chat input styling (light/dark mode)
- [ ] Mobile-responsive (chips wrap)

### Out of scope
- Persisting which chip was clicked (analytics) — defer
- Per-user customization of chips — defer
- Truncation of long prompts — `validate_default_prompts` enforces ≤200 chars server-side

---

## Trick 3: Cross-Skill `references/` Directory

**Effort:** < 1 day
**Risk:** Low

### What

Two reference files have already been written locally (gitignored):
- `.hermes/skills/references/oauth-flow.md`
- `.hermes/skills/references/webhook-patterns.md`

These can be loaded on demand by any integration skill via the Hermes skill loader. The convention needs to be codified:

1. Skills declare `references:` in their frontmatter
2. When a skill triggers, the loader makes its referenced docs available
3. Multiple skills can share the same reference

### Success criteria
- [ ] Hermes skill loader supports `references:` frontmatter declaration
- [ ] At least 2 skills reference the same shared doc (e.g., `oauth-flow.md` referenced by both `slack-integration.md` and `notion-integration.md`)
- [ ] Token cost reduction measured before/after for a typical integration-setup workflow

---

## Trick 1: `$phase` Orchestration

**Effort:** 1–3 days
**Risk:** Medium (depends on Hermes skill-system support)

### What

Skills declare `$phase: <name>` blocks that other skills can invoke by name with sequencing guarantees. Tested manually with Qwen3.6-27B in the exit audit (3 scenarios, all passed). Production rollout needs:

1. Hermes skill loader parses `$phase:` blocks
2. The agent runtime understands "I am in $phase X, only $skill-name Y is invocable"
3. Cross-skill completion tracking (what ran, what didn't)

### Success criteria
- [ ] A multi-skill workflow (e.g., preflight → execute → validate) can be declared declaratively in one SKILL.md
- [ ] Phase ordering enforced (cannot skip phases)
- [ ] Tested with Qwen3.6-27B on a real workflow (deploy, integration setup)

### Risk
- $phase semantics may need iteration with the local model
- Hermes skill loader may need schema changes

---

## Files Touched This Session

### Committed
- `2dff954` — `feat(sdk): harden PluginManifest with extra="forbid" + Codex field rejection`
- `dcf5fae` — `feat(sdk): add default_prompts to PluginManifest (Trick 9a)`
- `c87bca5` — `docs: add Phase B plan + exit audit for codex-plugins adoption`

### Local only (gitignored, per-machine state)
- `.hermes/skills/guardrails.md` (Trick 4)
- `.hermes/skills/incremental-execution.md` (Trick 7)
- `.hermes/skills/investigation-ledger.md` (Trick 16)
- `.hermes/skills/deploy-orchestration.md` (Trick 1, Phase B)
- `.hermes/skills/references/oauth-flow.md` (Trick 3, Phase B)
- `.hermes/skills/references/webhook-patterns.md` (Trick 3, Phase B)
- `.hermes/investigations/.gitkeep` (Trick 16 directory)

### Modified (deploy scripts)
- `scripts/pre-deploy-check.sh` — emits `[PREFLIGHT: BLOCKED]` / `[PREFLIGHT: READY]` tokens
- `deploy-backend.sh` — emits `[ESCALATION REQUIRED: migrate]` / `[ESCALATION REQUIRED: sudo]` tokens

---

## Next Session Priorities

1. **Fix deploy-script health-check timeout** (KNOWN ISSUE above — 30s budget too tight for cold start)
2. **Trick 9b (Frontend seed prompts)** — render `default_prompts` as clickable chips
3. **Update example manifest** — add `default_prompts: [...]` to `backend/app/sdk/examples/flowmanner-plugin.yaml` so the example is self-documenting
4. **Push commits to origin** — 3 commits ahead of `origin/main` (`2dff954`, `dcf5fae`, `c87bca5`). Per standing rule, Glenn decides when to push.

---

## Files to Read Next Session

| File | Why |
|---|---|
| `docs/EXIT-AUDIT-2026-06-28-codex-plugins-phase-a-b.md` | Phase A+B implementation details, 21 tests passing |
| `.sisyphus/analysis/codex-plugins-adoption-plan-2026-06-28.md` | Full 17-trick adoption plan with verdicts |
| `backend/app/sdk/manifest.py` | Current `PluginManifest` with all Phase A+B fields |
| `backend/app/api/v1/plugins.py` | `PluginResponse` with `default_prompts` extraction |
| `backend/tests/test_plugin_manifest.py` | 21 tests covering all manifest validation |
