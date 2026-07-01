# EXIT AUDIT — Codex Plugins Adoption Plan (Phase A + B)

**Date:** June 28, 2026
**Session type:** Codex Plugins Adoption Plan implementation (Phase A complete + Phase B complete)
**Machine:** Homelab (172.16.1.1)
**Commits:** `2dff954` (Phase A) + uncommitted (Phase B — Trick 9a)
**Backend status:** ✅ Healthy (not redeployed — no backend deploy needed for this session)

---

## What Changed

### Phase A — 6 "Adopt Now" Tricks (committed as `2dff954`)

| Trick | Name | Type | File(s) |
|-------|------|------|---------|
| 11 | Manifest Validation Gates | Code | `backend/app/sdk/manifest.py`, `backend/tests/test_plugin_manifest.py` |
| 2 | Capability Preflight Tokens | Script | `scripts/pre-deploy-check.sh` |
| 17 | Escalated Permissions Tokens | Script | `deploy-backend.sh` |
| 4 | Tool-Call Guardrails | Skill | `.hermes/skills/guardrails.md` (gitignored) |
| 7 | Incremental Execution | Skill | `.hermes/skills/incremental-execution.md` (gitignored) |
| 16 | Investigation Ledger | Skill + Dir | `.hermes/skills/investigation-ledger.md`, `.hermes/investigations/.gitkeep` (gitignored) |

### Phase B — 3 "Defer to Q3" Tricks (uncommitted)

| Trick | Name | Type | File(s) |
|-------|------|------|---------|
| 3 | Cross-Skill References | Skill | `.hermes/skills/references/oauth-flow.md`, `.hermes/skills/references/webhook-patterns.md` (gitignored) |
| 1 | `$phase` Orchestration | Skill | `.hermes/skills/deploy-orchestration.md` (gitignored) |
| 9a | Default/Seed Prompts (backend) | Code | `backend/app/sdk/manifest.py`, `backend/app/api/v1/plugins.py`, `backend/tests/test_plugin_manifest.py` |
| — | Phase B Plan | Doc | `plans/phase-b-q3-codex-plugins-plan.md` |

---

## Files Changed (tracked)

| File | Change |
|------|--------|
| `backend/app/sdk/manifest.py` | Added `ConfigDict(extra="forbid")`, `@model_validator` rejecting prohibited fields (mcpServers, hooks, skills, apps), `default_prompts` field with validator (max 3, ≤200 chars) |
| `backend/app/api/v1/plugins.py` | Added `default_prompts` to `PluginResponse`, extraction from `manifest_json` in `_to_plugin_response()` |
| `scripts/pre-deploy-check.sh` | Added `[PREFLIGHT: BLOCKED]` / `[PREFLIGHT: READY]` machine-readable tokens at end of main() |
| `deploy-backend.sh` | Added `[ESCALATION REQUIRED: migrate]` when `--migrate` passed, `[ESCALATION REQUIRED: sudo]` pre-check when precheck skipped |
| `backend/tests/test_plugin_manifest.py` | 21 tests covering extra=forbid, prohibited fields, minimal manifests, example roundtrip, default_prompts validation |
| `plans/phase-b-q3-codex-plugins-plan.md` | Phase B implementation plan (Tricks 1, 3, 9) |
| `.sisyphus/analysis/codex-plugins-adoption-plan-2026-06-28.md` | Full adoption plan document (17 tricks) |

---

## Files Created (gitignored — local agent instructions)

| File | Purpose |
|------|---------|
| `.hermes/skills/guardrails.md` | Tool-call guardrails (max 1 retry, stop on 403/404/timeout) |
| `.hermes/skills/incremental-execution.md` | One-step-at-a-time execution rules |
| `.hermes/skills/investigation-ledger.md` | Durable file-based investigation log (4k char limit) |
| `.hermes/skills/deploy-orchestration.md` | 3-phase deploy protocol ($phase: preflight → execution → validation) |
| `.hermes/skills/references/oauth-flow.md` | Shared OAuth reference (5 providers, token refresh, Fernet encryption) |
| `.hermes/skills/references/webhook-patterns.md` | Shared webhook reference (20 providers, signature verification patterns) |
| `.hermes/investigations/.gitkeep` | Investigation ledger directory |

---

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| `test_plugin_manifest.py::TestPluginManifestExtraForbid` | 4 | ✅ All pass |
| `test_plugin_manifest.py::TestPluginManifestProhibitedFields` | 6 | ✅ All pass |
| `test_plugin_manifest.py::TestPluginManifestMinimal` | 5 | ✅ All pass |
| `test_plugin_manifest.py::TestPluginManifestDefaultPrompts` | 6 | ✅ All pass |
| **Total** | **21** | ✅ **All pass (0.05s)** |

### llama.cpp $phase Protocol Tests (Qwen3.6-27B)

| Scenario | Expected | Result |
|----------|----------|--------|
| Simple deploy prompt | Starts with `$phase: preflight` | ✅ Correct |
| Deploy with migration | Sequences preflight → execution, separates deploy from migrate | ✅ Correct |
| Preflight blocked | Stays in `$phase: preflight`, does NOT proceed | ✅ "Per the deploy protocol, I must stop here and await your direction" |

### Token Parseability Tests

| Script | Token | Found |
|--------|-------|-------|
| `pre-deploy-check.sh` | `[PREFLIGHT: BLOCKED]` | ✅ "1 check(s) failed, 4 passed" |
| `deploy-backend.sh --dry-run --migrate` | `[ESCALATION REQUIRED: migrate]` | ✅ |
| `deploy-backend.sh --dry-run` (no migrate) | Neither token | ✅ Correct |

---

## Key Design Decisions

1. **`extra="forbid"` on PluginManifest** — Catches unknown fields at the Pydantic level. Combined with a `@model_validator` that provides better error messages for Codex-style prohibited fields (mcpServers, hooks, skills, apps). The validator runs first, so prohibited fields get the custom message; unknown fields get the generic `extra_forbidden` error.

2. **`default_prompts` is additive and backward-compatible** — `default_factory=list` means existing manifests without the field get `[]`. No DB migration needed — stored in the existing `manifest_json` column.

3. **`max_length=3` removed from Field** — The `@field_validator` provides a clearer error message ("Maximum 3 default_prompts allowed") than Pydantic's generic "too_long" error. The validator alone enforces the limit.

4. **Skill files are gitignored** — `.hermes/` is in `.gitignore`. All skill files, references, and investigations are local agent instructions, not tracked code. This is intentional — they're per-machine state.

5. **3 phases, not 4+** — The `$phase` protocol uses exactly 3 phases (preflight, execution, validation). Testing confirmed Qwen3.6-27B handles 3 phases reliably. More phases would confuse the 27B model.

6. **Preflight tokens are the last line of output** — `[PREFLIGHT: BLOCKED/READY]` appears after all colored log output so the agent can parse it without ANSI color stripping.

---

## Issues Encountered & Resolved

| Issue | Resolution |
|-------|------------|
| `max_length=3` on Field fires before validator | Removed `max_length=3` from Field, rely on validator for custom message |
| Duplicate `[ESCALATION REQUIRED: sudo]` in both scripts | Removed from `pre-deploy-check.sh`, kept only in `deploy-backend.sh` (fires when `--skip-precheck`) |
| Escaping issue with `$(whoami)` in sudo token | Changed to single quotes with `<user>` placeholder |
| llama.cpp JSON parsing failed (newlines in skill content) | Used `jq --rawfile` to properly escape content into JSON payload |
| `[PREFLIGHT: BLOCKED]` lacked actionable guidance | Updated to "Review [FAIL] lines above for remediation steps" |

---

## What's NOT Done (Phase B remaining)

| Item | Status | Blocker |
|------|--------|---------|
| Trick 9b: Frontend seed prompt chips | Not started | Requires frontend repo (`/home/glenn/FlowmannerV2-frontend/`) |
| Commit Phase B changes | Not done | Uncommitted: manifest.py, plugins.py, test_plugin_manifest.py, phase-b plan |
| Deploy to production | Not done | No backend code deploy needed — changes are additive Pydantic fields |

---

## Next Session Priorities

1. **Commit Phase B changes** — `git add` the 4 untracked/modified files and commit with descriptive message
2. **Trick 9b (Frontend)** — Add seed prompt chips to the chat UI in the frontend repo
3. **Update example manifest** — Add `default_prompts` example to `backend/app/sdk/examples/flowmanner-plugin.yaml`

---

## Files to Read Next Session

| File | Why |
|------|-----|
| `plans/phase-b-q3-codex-plugins-plan.md` | Full Phase B plan with success criteria |
| `.sisyphus/analysis/codex-plugins-adoption-plan-2026-06-28.md` | Complete 17-trick adoption plan |
| `backend/app/sdk/manifest.py` | Current PluginManifest with all Phase A+B fields |
| `backend/app/api/v1/plugins.py` | PluginResponse with default_prompts |
| `backend/tests/test_plugin_manifest.py` | 21 tests covering all manifest validation |
