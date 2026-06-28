# Codex Plugins — FlowManner Adoption Plan

**Date:** 2026-06-28
**Author:** FlowManner Engineer (AI-assisted)
**Source:** `.sisyphus/analysis/codex-plugins-architecture-2026-06-28.md`
**Constraint:** 1-person team, self-hosted homelab, $400/mo infra, llama.cpp as primary LLM

---

## 1. Executive Summary

Skip the enterprise noise, adopt the behavioral guardrails. FlowManner is a 1-person local homelab setup constrained by llama.cpp context windows, so we ruthlessly prioritize prompt-based instructions (guardrails, incremental execution, ledgers) that save tokens and prevent cascading agent failures. We defer UI-heavy marketplace tweaks (seed prompts, `$phase` orchestration, shared references) to Q3 and strictly skip orchestration features (JSON marketplaces, ordinal receipts, workspace routing, dual-scope registries) that attempt to solve multitenant problems we don't have. Six tricks get adopted now — all small, all behavioral, all addressing real pain points the local LLM hits daily.

---

## 2. Trick-by-Trick Verdicts

### Trick 1: Skill-Bound Subagent Orchestration with `$phase` Invocation

**Verdict:** Defer to Q3
**Effort:** M (1–3 days)
**User-facing value:** Medium
**Interaction risk:** `.hermes/skills/` execution flows
**Rationale:** We only need this when Hermes gets too complex for single-prompt contexts. Right now, standard prompt chains are sufficient. Building native `$phase` handling costs time better spent on core pipelines. The existing deploy scripts already enforce sequencing (build → migrate → health check → rollback) without a skill orchestration layer.
**Concrete first step:** Add a `$phase` text rule to one complex SKILL.md (e.g., the deploy orchestration skill) and observe whether the local LLM follows it reliably.

---

### Trick 2: Capability Preflight

**Verdict:** Adopt Now
**Effort:** S (< 1 day)
**User-facing value:** High
**Interaction risk:** `scripts/pre-deploy-check.sh`, `deploy-backend.sh`
**Rationale:** We already have the skeleton in `pre-deploy-check.sh` — it checks WireGuard, working tree, health URL, pending migrations, and uncommitted models. But the output is human-readable colored text. Formalizing distinct `ready` vs `blocked` token returns prevents the local Llama.cpp model from hallucinating fixes for hard blockers (like WireGuard missing or sudoers not configured). The script already has `CHECKS_FAIL` counting — we just need to emit a machine-readable `[BLOCKED]` or `[READY]` token that Hermes can parse.
**Concrete first step:** Update `scripts/pre-deploy-check.sh` to emit a final line like `[PREFLIGHT: BLOCKED]` or `[PREFLIGHT: READY]` that Hermes can detect without parsing ANSI colors.

---

### Trick 3: Cross-Skill Dependencies with Explicit `references/` Directories

**Verdict:** Defer to Q3
**Effort:** S (< 1 day)
**User-facing value:** Low
**Interaction risk:** `.hermes/skills/` directory structure
**Rationale:** Reduces context duplication, but the agent's context is currently small enough to fit within monolithic SKILL.md files. The plugin system doesn't use skills — it uses Python code. Premature optimization to shard reference docs now. Revisit when we have 10+ integration-specific skills that share common API patterns.
**Concrete first step:** Create `references/` locally for the next major integration skill (e.g., `references/slack-api-reference.md`).

---

### Trick 4: Tool-Call Guardrails — "If Tool Not Found, Stop Retrying"

**Verdict:** Adopt Now
**Effort:** S (< 1 day)
**User-facing value:** High
**Interaction risk:** `.hermes/skills/` text only — no code changes
**Rationale:** Llama.cpp models hallucinate retries violently. When a Slack API call returns 403 or a Docker command fails with "not found," the local LLM will retry with slightly different arguments, burning tokens and time. Hardcoding "If 403, stop retrying and ask user to re-authenticate" in SKILL.md is a zero-cost change that saves real compute cycles. This is the single highest-ROI trick for a self-hosted LLM setup.
**Concrete first step:** Add the guardrail sentence to the current integration setup skill: "If a specific API call returns 403, treat the integration as unauthorized and stop. Do not retry with different scopes."

---

### Trick 5: Workspace Routing — App Path vs CLI Path

**Verdict:** Skip
**Effort:** M (1–3 days)
**User-facing value:** None
**Interaction risk:** Agent execution context injection
**Rationale:** FlowManner is a single UI (web app) + CLI interface used by 1 developer. Dynamic skill responses based on host context (TUI vs Telegram vs cron) are massive overkill. The deploy scripts already work identically regardless of invocation context. If we ever add a Telegram bot, we can add context-aware output formatting then — not now.
**Concrete first step:** N/A

---

### Trick 6: Mandatory Skill Loading Before Tool Calls

**Verdict:** Skip
**Effort:** M (1–3 days)
**User-facing value:** Low
**Interaction risk:** Hermes orchestration loop
**Rationale:** Heavy framework-purity logic. If a tool is dangerous (deploy scripts, migration commands), the agent's system prompt should enforce the prerequisites — not a mandatory skill-loading gate that adds latency to every tool call. Our `AGENTS.md` and `AGENTS.homelab.md` already serve this role: they tell the agent to read deploy docs before running deploy commands. Adding a formal "MUST load skill X before calling tool Y" gate doesn't improve on this.
**Concrete first step:** N/A

---

### Trick 7: Incremental Execution — "Work in Small Steps, Validate After Each"

**Verdict:** Adopt Now
**Effort:** S (< 1 day)
**User-facing value:** High
**Interaction risk:** `.hermes/skills/` execution rules — no code changes
**Rationale:** Multi-step shell executions (deploy-backend.sh → DB migrate → restart) fail silently if batched. The local Llama.cpp model has a tendency to chain multiple commands in one shell invocation, losing the ability to detect where failure occurred. Forcing the LLM to "one tool call per step, validate after each" stops catastrophic overwrites. This is especially critical for deploy workflows where a failed migration followed by a restart can leave the system in an inconsistent state.
**Concrete first step:** Add "One tool call per step. Validate result before proceeding. Never chain deploy + migrate + smoke test in a single command." to the Hermes deploy skill.

---

### Trick 8: File-Driven Marketplace (`marketplace.json`)

**Verdict:** Skip
**Effort:** M (1–3 days)
**User-facing value:** None
**Interaction risk:** `backend/app/services/marketplace_service.py`, `backend/app/models/models.py`
**Rationale:** FlowManner already relies on a DB schema (`MarketplaceListingModel`) with 10 hardcoded seed listings. Migrating this to a file-based registry just changes the underlying store for zero user value in a self-hosted single-tenant setup. The marketplace is templates (workflow blueprints), not plugins — and templates don't need version-controlled catalogs. If we ever add a real plugin marketplace, we can introduce `marketplace.json` then.
**Concrete first step:** N/A

---

### Trick 9: Default/Seed Prompts

**Verdict:** Defer to Q3
**Effort:** M (1–3 days)
**User-facing value:** High
**Interaction risk:** `PluginManifest` schema (`backend/app/sdk/manifest.py`), `v1/plugins.py` API schema, frontend chat UI
**Rationale:** Helps with the "blank page" problem post-install — users install a plugin and don't know what to do with it. But implementing this requires: (1) additive manifest field, (2) API response changes, (3) frontend UI to display seed prompts in the chat. The UI work pushes this out of Phase 1. The manifest field is backward-compatible and can be added early.
**Concrete first step:** Add `default_prompts: list[str]` to `PluginManifest` in `backend/app/sdk/manifest.py` (additive, backward-compatible).

---

### Trick 10: Authentication Timing Policy (`ON_INSTALL` vs `ON_USE`)

**Verdict:** Skip
**Effort:** L (3+ days)
**User-facing value:** Low
**Interaction risk:** `backend/app/integrations/adapters/base.py` OAuth flow, all 5 integration adapters
**Rationale:** Integrations aren't plugins in FlowManner — they are core repo code (`backend/app/integrations/adapters/`) matching single OAuth tenants per service. We have 5 integrations (Slack, Notion, Linear, GitHub, Google Drive), all using `ON_INSTALL` OAuth during onboarding. Adding `ON_USE` deferral requires changes to the adapter base class, the OAuth flow coordinator, and every integration that wants deferred auth. For 1 user, this complexity doesn't pay off. If a Slack workspace requires admin-scoped approval, the user just does it once.
**Concrete first step:** N/A

---

### Trick 11: Manifest Validation with Strict Release Gates

**Verdict:** Adopt Now
**Effort:** S (< 1 day)
**User-facing value:** High
**Interaction risk:** `backend/app/sdk/manifest.py`, `backend/app/services/plugin_scanner.py`
**Rationale:** The `PluginScanner` (`backend/app/services/plugin_scanner.py`) currently gives risk scores and allows bad plugins to proceed with `review_status="pending"`. The `plugin_loader.py` unpacks everything blindly — if the YAML parses and Pydantic validates, it loads. There's no rejection of prohibited fields (`mcpServers`, `hooks`). Adding a `model_validator` that rejects unknown top-level keys and explicitly prohibits dangerous fields prevents junk from entering the environment. This is a Pydantic `extra="forbid"` change plus a few explicit banned-key checks.
**Concrete first step:** Add `model_config = ConfigDict(extra="forbid")` to `PluginManifest` and add a `@model_validator(mode="before")` that rejects `mcpServers` and `hooks` keys.

---

### Trick 12: Dual-Scope Marketplaces — Repo vs Personal

**Verdict:** Skip
**Effort:** L (3+ days)
**User-facing value:** None
**Interaction risk:** Global registry logic, workspace scoping
**Rationale:** You are a 1-person team with 1 workspace. Repo-level vs global registry isolation solves a multi-team enterprise problem we don't have. If we ever add multi-workspace support, we can revisit — but the current `InstalledPlugin.workspace_id` field already scopes plugins per workspace.
**Concrete first step:** N/A

---

### Trick 13: The `agents/openai.yaml` Layer — Skill-to-Agent Interface Split

**Verdict:** Skip
**Effort:** S (< 1 day)
**User-facing value:** None
**Interaction risk:** Hermes skill architecture
**Rationale:** Splitting SKILL.md into behavior (markdown) and interface (YAML) is aesthetic pedantry. It doesn't improve agent success rate, doesn't save tokens, and adds a file to maintain per skill. Our Hermes skills are already loaded by the agent runtime — the frontmatter `name` and `description` serve the interface role. If we ever build a skill marketplace, we can add `skill.yaml` then.
**Concrete first step:** N/A

---

### Trick 14: Ordinal Completion Receipts

**Verdict:** Skip
**Effort:** L (3+ days)
**User-facing value:** Low
**Interaction risk:** Hermes internal state management, subagent delegation
**Rationale:** The orchestrator-worker pattern with ordinal receipts (6 workers, completion tracking, semantic merging) is overkill for a $400/mo local agent setup. Our `delegate_task` returns prose summaries, and while "trusting prose" is theoretically risky, the actual failure cost is low — we're not doing security audits with false-negative consequences. If we ever build multi-agent codebase audits, we can add lightweight receipts then. For now, "run task, check output, proceed" works.
**Concrete first step:** N/A

---

### Trick 15: Product-Restricted Plugins (`policy.products`)

**Verdict:** Skip
**Effort:** S (< 1 day)
**User-facing value:** None
**Interaction risk:** `backend/app/sdk/manifest.py`
**Rationale:** We have one product surface (web app). Adding a `surfaces` field to the manifest costs nothing technically but adds a field that every plugin author must understand and every consumer must filter on. When we have 2+ surfaces (mobile, agent SDK), we can add this. Until then, it's dead weight.
**Concrete first step:** N/A

---

### Trick 16: Investigation Ledger — File-Based Log of Every Step

**Verdict:** Adopt Now
**Effort:** S (< 1 day)
**User-facing value:** High
**Interaction risk:** Agent execution lifecycle — no backend code changes
**Rationale:** Local open-weight models (Llama.cpp, Qwen3.6-27B) lose context fast — especially during multi-step investigations (bug triage, integration debugging, deploy troubleshooting). When the context window resets, the investigation restarts from scratch. A durable file-based log (`.hermes/investigations/<id>.md`) lets the agent reload its progress. This is especially valuable for cron-triggered investigations where session state doesn't persist. The Codex security plugin's "candidate ledger" pattern maps directly: each step appends a timestamped entry with what was checked and what the result was.
**Concrete first step:** Create `.hermes/investigations/` directory and add a Hermes tool/instruction: "When doing multi-step investigation, write each step to `.hermes/investigations/<id>.md`. On context reset, read the file first."

---

### Trick 17: Escalated Permissions — Declared, Not Sneaked

**Verdict:** Adopt Now
**Effort:** S (< 1 day)
**User-facing value:** High
**Interaction risk:** `deploy-backend.sh`, `scripts/pre-deploy-check.sh`
**Rationale:** `WG_CHECK=skip` in `pre-deploy-check.sh` is already a bypass pattern with `FLOWMANNER_DEPLOY_OVERRIDE_REASON` as audit-logged justification. But the deploy scripts have other escalation points that aren't declared: `--migrate` requires DB access (could corrupt data), `sudo -n wg show` requires sudoers configuration, and the agent sometimes hangs on hidden interactive password prompts. Explicitly declaring `--escalate` for migrations/sudo tasks informs the operator and prevents the agent from hanging. The pattern: if a script needs elevated permissions, it should fail fast with a clear message rather than silently waiting for TTY input.
**Concrete first step:** Update `deploy-backend.sh` to emit `[ESCALATION REQUIRED: migrate]` and `[ESCALATION REQUIRED: sudo]` tokens when `--migrate` is passed or sudoers is missing, so Hermes can detect and ask the user.

---

## 3. Cross-Trick Synergies

### The Local LLM Survival Stack: Tricks 4 + 7 + 16

These three form a **coherent behavioral layer** that directly addresses the #1 problem with local Llama.cpp agents: hallucination loops and context loss.

- **Trick 4 (Guardrails)** stops the LLM from retrying failed tool calls — the most common token-wasting behavior.
- **Trick 7 (Incremental Execution)** forces one-step-at-a-time execution — preventing the LLM from chaining 5 commands and losing track of which failed.
- **Trick 16 (Investigation Ledger)** provides durable state across context resets — so the agent can pick up where it left off instead of restarting.

Together, they reduce token consumption by an estimated 30–50% on complex multi-step tasks. They're all prompt-based (no code changes), so they can be adopted in a single afternoon.

### The Fail-Fast Stack: Tricks 2 + 11 + 17

These three form a **safety gate layer** that prevents bad state from propagating.

- **Trick 2 (Preflight)** catches environment issues before execution starts.
- **Trick 11 (Strict Manifests)** catches bad plugin data before it enters the system.
- **Trick 17 (Escalated Permissions)** catches missing permissions before the agent hangs on interactive prompts.

Together, they create a "fail loud, fail early" culture. The agent never discovers mid-execution that the VPN is down, that a plugin has prohibited fields, or that it needs sudo access.

### Anti-Pattern: Don't Bundle Tricks 1 + 3 + 9 Together

These three (orchestration, references, seed prompts) are all "nice to have" Q3 features that touch different parts of the system. They don't reinforce each other — they're independent improvements. Bundling them into a single "marketplace refresh" phase would create a false dependency and delay all three.

---

## 4. Phased Roadmap

| Phase | Timeframe | Tricks | Dependencies | First concrete artifact |
|-------|-----------|--------|--------------|-------------------------|
| **Phase A** | Next 1–2 weeks | 4, 7, 16 | None | `.hermes/skills/` template with guardrails + incremental rules + ledger instructions |
| **Phase A** | Next 1–2 weeks | 2, 17 | `pre-deploy-check.sh` | Updated `scripts/pre-deploy-check.sh` emitting `[PREFLIGHT: BLOCKED]` / `[PREFLIGHT: READY]` tokens |
| **Phase A** | Next 1–2 weeks | 11 | `manifest.py` | `PluginManifest` with `extra="forbid"` and explicit banned keys validator |
| **Phase B** | Q3 2026 (Jul–Sep) | 1, 3, 9 | Phase A stable | `.hermes/skills/references/` folder + `default_prompts` field in manifest |

**Phase A** is all prompt-based + one small Pydantic change. Zero new endpoints, zero new migrations, zero new Docker builds.
**Phase B** requires UI work (seed prompts in chat) and architecture decisions (skill orchestration pattern).

---

## 5. Manifest Schema Deltas (Phase A only)

Additive, backward-compatible modifications to `backend/app/sdk/manifest.py`:

```python
from pydantic import ConfigDict, model_validator

class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # TRICK 11: reject unknown fields

    # ... all existing fields unchanged ...

    # TRICK 11: Explicit prohibited-field rejection
    @model_validator(mode="before")
    @classmethod
    def reject_prohibited_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            prohibited = {"mcpServers", "hooks", "skills", "apps"}
            found = prohibited.intersection(data.keys())
            if found:
                raise ValueError(
                    f"Prohibited fields in manifest: {sorted(found)}. "
                    f"These are not supported by FlowManner's plugin system."
                )
        return data
```

**Why `extra="forbid"`:** Existing `.fmp` manifests only use the declared fields. If someone adds unknown fields, it's either a typo or an attempt to inject unsupported features. Fail fast.

**Why ban `mcpServers`, `hooks`, `skills`, `apps`:** These are Codex plugin concepts that don't exist in FlowManner. If someone copies a Codex plugin manifest and tries to load it, we should reject it cleanly rather than silently ignoring the fields.

**Backward compatibility:** All existing manifests (using only `name`, `version`, `description`, `author`, `permissions`, `node_types`, `config`, `entry_point`, `min_platform_version`) will continue to parse. The only breaking change is for manifests that have unknown top-level keys — which is exactly what we want to catch.

**Empirical verification (2026-06-28 review session):** Searched the repo for every place `PluginManifest(**...)` is constructed or any file that could contain a manifest:

| Surface | Count | Has unknown keys? |
|---|---|---|
| `installed_plugins` DB rows | 0 | n/a (empty table) |
| `flowmanner-plugin.yaml` files in repo | 1 (`backend/app/sdk/examples/flowmanner-plugin.yaml`) | No — exact match to declared fields |
| `.fmp` archives in repo | 0 | n/a |
| Test files importing `PluginManifest` | 0 | n/a |
| Production call sites of `PluginManifest(**...)` | 3 (`plugin_loader.py:57`, `plugin_loader.py:193`, `cli.py:51`) | All forward `**yaml.safe_load(...)` straight through |

Validated the change in isolation by simulating `PluginManifest` with `extra="forbid"` and feeding it:
1. The actual example manifest → parses cleanly (Test 1 PASS)
2. A hypothetical Codex-style bad manifest with `mcpServers`, `hooks`, `skills`, and a generic `unknownField` → all 4 rejected with `extra_forbidden` errors (Test 2 EXPECTED FAIL — desired behavior)
3. A minimal manifest with only `name` + `version` → parses, defaults applied (Test 3 PASS)

**Confirmed: zero migration needed, zero grandfathering needed, pure additive change.** Safe to land immediately without coordinating against existing state.

---

## 6. Risks & Open Questions

1. **Ledger file size vs context window:** If `.hermes/investigations/<id>.md` grows beyond 8k tokens, the local Llama.cpp model will start dropping the tail context when it reads the file back. **Mitigation:** Add a strict max-size rule (e.g., 4k chars) and truncate from the top when exceeded.

2. **Preflight loop risk:** Will the agent get stuck reading `[PREFLIGHT: BLOCKED]` without knowing how to resolve the block? The preflight output must include actionable remediation steps (e.g., "WireGuard not configured — run: sudo ...") so the agent can either fix it or escalate to the user.

3. ~~**Strict validation vs dirty installs:** If a plugin was installed before `extra="forbid"` was added, and its `manifest_json` in the DB has extra fields, will `PluginManifest(**json.loads(plugin_row.manifest_json))` fail on reload?~~ **RESOLVED 2026-06-28 (review session):** `installed_plugins` table is empty (verified via `SELECT COUNT(*) FROM installed_plugins` → 0). The `.fmp` packaging pipeline, manifest validation, and install endpoints are all scaffolded, but no production plugin has been installed yet. The `extra="forbid"` change in Trick 11 is therefore a pure greenfield addition — no grandfathering needed, no migration of existing rows. The runtime loader (`plugin_runtime.py:install` / `plugin_loader.py`) reads from the uploaded `.fmp` archive directly, not from cached `manifest_json` in the DB. Confirmed safe to land immediately.

4. **Guardrail effectiveness with Qwen3.6-27B:** The "stop retrying" guardrail works well with GPT-4-class models. Will a 27B parameter model actually follow the instruction reliably? **Mitigation:** Test with 3 real failure scenarios (403 auth, missing tool, timeout) and measure retry count before/after.

5. **Escalation token parsing:** Adding `[ESCALATION REQUIRED: ...]` to deploy scripts assumes Hermes can parse bracket-enclosed tokens. We need to verify the Hermes system prompt handles this pattern, or adjust the format to match what Hermes already understands.

6. **Zero-plugin state is a window of opportunity, not a permanent condition:** The current empty `installed_plugins` table means Trick 11 can land safely today. But as soon as the first real plugin ships (likely a FlowManner-team-internal one), this window closes. **Recommendation:** Land Trick 11 in the same commit as the first plugin install, or before. Don't let the empty-table state trick us into postponing.

---

## 7. End-of-Plan Summary Table

| # | Trick | Verdict | Effort | Value |
|---|-------|---------|--------|-------|
| 1 | $phase orchestration | Defer to Q3 | M | Medium |
| 2 | Capability preflight | Adopt Now | S | High |
| 3 | Cross-skill references | Defer to Q3 | S | Low |
| 4 | Tool-call guardrails | Adopt Now | S | High |
| 5 | Workspace routing | Skip | M | None |
| 6 | Mandatory skill loading | Skip | M | Low |
| 7 | Incremental execution | Adopt Now | S | High |
| 8 | File-driven marketplace | Skip | M | None |
| 9 | Default/seed prompts | Defer to Q3 | M | High |
| 10 | Auth timing policy | Skip | L | Low |
| 11 | Manifest validation gates | Adopt Now | S | High |
| 12 | Dual-scope marketplaces | Skip | L | None |
| 13 | Skill/agent interface split | Skip | S | None |
| 14 | Ordinal completion receipts | Skip | L | Low |
| 15 | Product-restricted plugins | Skip | S | None |
| 16 | Investigation ledger | Adopt Now | S | High |
| 17 | Escalated permissions | Adopt Now | S | High |

**Adopt Now: 6 | Defer Q3: 3 | Defer Q4: 0 | Skip: 8**
