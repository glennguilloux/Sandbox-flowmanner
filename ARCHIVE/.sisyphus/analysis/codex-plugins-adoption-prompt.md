# Codex Plugins — FlowManner Adoption Plan

> **DeepSeek brainstorm prompt.** Hand this file to DeepSeek (`exec --auto --model deepseek-v4-pro`) for a think-out-loud adoption plan. Save DeepSeek's output to `.sisyphus/analysis/codex-plugins-adoption-plan-2026-06-28.md` so Glenn can review.
>
> Verify the output file exists and has a summary table at the end before reporting success. DeepSeek may truncate or silently self-report — always `wc -l` and `tail` the result.

---

## Context

**Product:** FlowManner — a self-hosted, agentic workflow platform (FastAPI backend + Next.js frontend). The core thesis is "your agents get smarter over time" via team memory + HITL. Cost is constrained to ~$400/mo total infra. Self-hosted LLM (llama.cpp on homelab) is the rule — no OpenAI/Google/Anthropic/DeepSeek as primary or fallback for self-hosted features.

**What already exists:**

| Component | Path | Purpose |
|---|---|---|
| `.fmp` plugin packages | `backend/app/sdk/manifest.py`, `plugin_loader.py` | Zipped plugin archives with `flowmanner-plugin.yaml` manifest |
| `InstalledPlugin` model | `backend/app/models/plugin_models.py` | Per-workspace plugin row, lifecycle states (installed → loaded → enabled → disabled → uninstalled), security review fields, runtime metrics |
| `PluginRuntime` | `backend/app/services/plugin_runtime.py` | Lifecycle coordinator, registers handlers with `NodeHandlerRegistry` |
| Plugin API | `backend/app/api/v1/plugins.py` | CRUD endpoints (install/list/enable/disable/execute/test) under `/api/v1/plugins` |
| Marketplace listings | `backend/app/services/marketplace_service.py` | Seed catalog of workflow templates (not plugins — different concern) |
| Integrations | `backend/app/integrations/adapters/{slack,notion,linear,github,google_drive}.py` | First-class connectors for 5 services, OAuth-based, hardcoded in repo |
| Plugin manifest schema | `backend/app/sdk/manifest.py` (`PluginManifest` Pydantic model) | `name`, `version`, `permissions`, `node_types[]`, `config`, `entry_point`, `min_platform_version` |
| Migrations | `backend/alembic/versions/20260603_phase91_plugins.py`, `phase96_plugin_security.py` | `installed_plugins` table + security scan columns |

**The trigger doc** (already on disk): `.sisyphus/analysis/codex-plugins-architecture-2026-06-28.md` (17 tricks from OpenAI's new Codex plugins system, March 2026). Read it fully before planning.

**The intent:** We want a **ranked, phased, evidence-grounded plan** for which of the 17 Codex tricks to actually adopt in FlowManner — and which to skip. Output should be a concrete roadmap the user can act on over the next 1–3 months, NOT a copy of the source doc with light edits.

---

## Current Architecture (What Exists)

### Plugin system (the part closest to "Codex plugins")

```
backend/app/sdk/
├── base.py              # BasePlugin, BaseNodeHandler — abstract plugin class
├── manifest.py          # PluginManifest (Pydantic) — name, version, perms, node_types, config
├── loader               # (see services/plugin_loader.py)
├── exceptions.py        # ManifestError, PluginLoadError, PluginError
├── cli.py               # Plugin CLI scaffold
└── examples/flowmanner-plugin.yaml  # Reference manifest

backend/app/services/
├── plugin_loader.py     # Unpacks .fmp, validates manifest, imports entry point
├── plugin_scanner.py    # Security scan (Phase 9.6)
├── plugin_runtime.py    # Lifecycle: install → load → enable → disable → uninstall
└── plugin_models.py     # InstalledPlugin SQLAlchemy model

backend/app/api/v1/plugins.py
└── CRUD: list, install (upload .fmp), get, status, enable/disable, uninstall, execute, node-types
```

**Manifest fields today:** `name`, `version`, `description`, `author`, `permissions[]`, `node_types[]`, `config{}`, `entry_point`, `min_platform_version`. **Missing:** skills (no skill concept in plugins), apps (no connector concept in plugins), MCP servers (we consume MCP, don't ship them), interface metadata (no seed prompts, no capabilities list), policy fields (no auth_timing, no surface restriction).

**Permission model:** Whitelist of 5 strings — `network`, `filesystem`, `subprocess`, `env_read`, `env_write`. Validated by Pydantic `field_validator`.

**Lifecycle states:** `installed → loaded → enabled ⇄ disabled → uninstalled`, plus `error`. Security review: `pending / approved / rejected` with `scan_risk_score` and `reviewed_by`.

**Source:** Currently `upload` only (.fmp via API). Schema supports `marketplace` and `git` but neither is wired.

### Integrations (NOT plugins — separate concept)

```
backend/app/integrations/
├── oauth.py             # OAuth flow coordinator
├── sandboxd_client.py   # Bridge to sandboxd for sandboxed execution
├── monitoring/health_check.py
├── adapters/
│   ├── base.py          # Adapter interface
│   ├── slack.py, notion.py, linear.py, github.py, google_drive.py
└── openwhisk/           # OpenWhisk deployment layer (separate infra path)
```

These are **first-class repo code**, not packaged plugins. Adding a new integration requires a backend PR. No marketplace for integrations — only for templates.

### Marketplace (templates, not plugins)

```
backend/app/services/marketplace_service.py
└── Hardcoded seed listings: 20+ workflow templates (Slack Notification Hub, AI Cold Email, etc.)
    Schema: name, type, category, description, integrations[], tags[]
```

Templates are workflow blueprints the user can clone — NOT installable plugin packages.

### Skills (Hermes — agent-side, not user-facing)

`~/.hermes/skills/` — Hermes-side SKILL.md files that guide agent behavior. Independent of the plugin system entirely. The user has a rich Hermes skills setup already (see `AGENTS.md` and the available_skills block).

---

## The Codex Tricks (condensed from the source doc — read the source for full detail)

Source: `.sisyphus/analysis/codex-plugins-architecture-2026-06-28.md`

| # | Trick | One-liner |
|---|---|---|
| 1 | `$phase` skill orchestration | One skill invokes others by name with sequencing |
| 2 | Capability preflight | Check env before substantive work; explicit `ready/blocked` outcomes |
| 3 | Cross-skill `references/` | Shared docs loaded on demand by skills |
| 4 | Tool-call guardrails | "If tool not found, stop retrying" baked into skills |
| 5 | Workspace routing | App path vs CLI path with different UX in same skill |
| 6 | Mandatory skill loading | Skill must be loaded before certain tool calls |
| 7 | Incremental execution | Small steps, validate after each |
| 8 | File-driven marketplace | `marketplace.json` JSON catalog, version-controlled with code |
| 9 | Default/seed prompts | `interface.defaultPrompt[]` shown at install time |
| 10 | Auth timing policy | `ON_INSTALL` vs `ON_USE` per plugin |
| 11 | Manifest validation gates | Strict required/prohibited fields; blocks bad plugins |
| 12 | Dual-scope marketplaces | Repo-scoped vs personal marketplaces |
| 13 | Skill/agent interface split | `SKILL.md` (behavior) vs `agents/openai.yaml` (interface) |
| 14 | Ordinal completion receipts | Coordinator tracks explicit completion per work item |
| 15 | Product-restricted plugins | `policy.products: ["CODEX"]` |
| 16 | Investigation ledger | File-based log of every step + receipt |
| 17 | Escalated permissions | `--escalate` flag pattern, asks user before raising |

The source doc has a "Priority" column (Now / Soon / Later / Maybe) — but that ranking was done in isolation, without considering FlowManner's specific constraints. **Your job is to produce a FlowManner-specific ranking.**

---

## What to Think About

For each trick, decide:

1. **Does it solve a problem FlowManner actually has?** Reference the existing architecture above. If the problem doesn't exist (or is already solved), say so — don't fabricate a fit.

2. **What's the migration cost?** Touching `PluginManifest` is breaking for every existing `.fmp` plugin. Adding a JSON schema is additive. Renaming a field is breaking. Be specific about scope.

3. **What's the user-facing value?** Self-hosted FlowManner customers (1–10 person teams) running integrations for Slack/Notion/Linear/etc. Value = fewer failed deploys, easier plugin authoring, better discovery, less repetition. Avoid framework-purity arguments.

4. **What does it interact with?** Cross-cutting concerns:
   - `backend/app/api/v1/plugins.py` — backwards compatibility forever (per `app/api/AGENTS.md` rule 1: "v1 stays backward-compatible forever")
   - `backend/app/sdk/manifest.py` — `PluginManifest` is the validation choke point
   - `backend/app/models/plugin_models.py` — DB schema changes need Alembic migrations
   - Self-hosted LLM rule: any new feature that talks to an LLM must use llama.cpp on homelab, NOT OpenAI/Claude/DeepSeek
   - Cost: every new field, new endpoint, new schema validation is something the user has to deploy and migrate

5. **Skip vs adopt vs defer?** Be opinionated. "Maybe later" is a real recommendation. "Skip — overkill" is a real recommendation. Don't promote everything to "Now" to seem thorough.

6. **Interaction with existing Hermes skills.** Tricks #1, #3, #4, #6, #7, #13 are about skills. Hermes already has a skill system (`~/.hermes/skills/`). Decide whether these are plugin-system features, Hermes features, or both. Don't double-up.

### Specific questions to answer

- **Trick #1 (`$phase` orchestration):** We have a Hermes skill system AND a plugin system. Which gets the `$phase` pattern? Or both? What's the actual user-facing workflow that would benefit?
- **Trick #2 (capability preflight):** What FlowManner workflows actually have "discover failures mid-execution" today? Deploy scripts? Plugin install? Mission execution? Be concrete.
- **Trick #3 (shared `references/`):** What's currently duplicated in Hermes skills? What's currently duplicated across plugin manifests?
- **Trick #4 (tool-call guardrails):** Where does our agent retry failed tool calls today? Is this a real problem or theoretical?
- **Trick #5 (workspace routing):** Our agents run in TUI, Telegram, cron, web. Do we already have context-aware skills? Is this a Hermes concern, a plugin concern, or both?
- **Trick #7 (incremental execution):** Do our agents actually try to do too much in one shot? Cite specific examples from recent session logs if you find them.
- **Trick #8 (file-driven marketplace):** The current marketplace is hardcoded seed listings. Would file-driven be a real improvement or just a different shape? What's the workflow that would change?
- **Trick #9 (seed prompts):** After onboarding, does the user see any "here's what you can do" moment? If not, where would this go in the UI?
- **Trick #10 (auth timing):** We auth on connect today. Are any integrations heavy enough to warrant deferral? Name them.
- **Trick #11 (strict validation):** What currently slips through to runtime that should be caught at manifest parse?
- **Trick #12 (repo vs personal marketplaces):** Single-tenant FlowManner today. When would multi-scope matter?
- **Trick #13 (skill/interface split):** Is this worth doing as a refactor for skills we've already written, or only for new ones?
- **Trick #14 (completion receipts):** `delegate_task` returns a prose summary. What's the failure cost of trusting prose today? Has this bitten us?
- **Trick #15 (product-restricted):** We have one surface (web app). When would this matter?
- **Trick #16 (investigation ledger):** Cron-triggered investigations, multi-session agents — what's the actual reload pattern? Is there a real failure mode here?
- **Trick #17 (escalated permissions):** What deploy/install operations today have no middle ground between "fully allowed" and "blocked"?

### Output format constraints

Produce exactly these sections:

#### 1. Executive Summary (≤200 words)

What to adopt, what to defer, what to skip, in plain language. No tables. The 3-sentence version.

#### 2. Trick-by-Trick Verdicts

For each of the 17 tricks, a section:

```markdown
### Trick N: <title>
**Verdict:** Adopt Now | Defer to Q3 | Defer to Q4 | Skip
**Effort:** S (< 1 day) | M (1–3 days) | L (3+ days)
**User-facing value:** None | Low | Medium | High
**Interaction risk:** (list concrete things it touches)
**Rationale:** (2–4 sentences grounded in FlowManner's actual architecture)
**Concrete first step:** (the smallest thing that proves the value)
```

If verdict is Skip, "Concrete first step" can be omitted.

#### 3. Cross-Trick Synergies

Which tricks reinforce each other? E.g., Trick #2 (preflight) + #17 (escalated permissions) form a complete safety story. Trick #9 (seed prompts) + #11 (strict validation) both touch the install UX. Map these. Avoid the "adopt everything together" trap.

#### 4. Phased Roadmap

| Phase | Timeframe | Tricks | Dependencies | First concrete artifact |
|---|---|---|---|---|
| Phase A | Next 1–2 weeks | … | … | … |
| Phase B | Q3 2026 | … | … | … |
| Phase C | Q4 2026 / 2027 | … | … | … |

Each row must have ONE concrete artifact (a file path, an endpoint, a manifest field) so "done" is verifiable.

#### 5. Manifest Schema Deltas (only if Phase A includes manifest changes)

Show the exact additive changes to `PluginManifest` in `backend/app/sdk/manifest.py`. Required to be backward-compatible (existing manifests must still load). Each field listed with:
- Name, type, default, why it exists, which trick it serves

#### 6. Risks & Open Questions

What's the downside of adopting too much too fast? What's still unknown? Surface 3–5 honest unknowns. Don't list things you're already decided on.

#### 7. End-of-Plan Summary Table

| # | Trick | Verdict | Effort | Value |
|---|---|---|---|---|
| 1 | $phase orchestration | … | … | … |
| … | … | … | … | … |

Plus a count line: "Adopt Now: N | Defer Q3: N | Defer Q4: N | Skip: N"

---

## Persona & Style

You are **The FlowManner Engineer** — opinionated, grounded in the actual codebase, allergic to framework-purity arguments, calibrated to a 1-person team + part-time AI agents operating at $400/mo.

- **Bold verdicts, no hedging.** "Adopt Now" or "Skip." Not "could be useful."
- **Cite file paths.** Don't describe the plugin loader — point at `backend/app/services/plugin_loader.py:24`.
- **Cost-aware.** Every new field, new endpoint, new migration costs the user a deploy.
- **Self-hosted rule respected.** Never suggest "use OpenAI to classify this" or "use Claude to extract structure." llama.cpp on homelab or nothing.
- **Quietly note DeepSeek's known biases.** It's known to (a) silently batch unrequested work, (b) cite fictional OAuth flows from training data, (c) over-promise on integrations. Correct for these.

**Show your reasoning.** A 1-paragraph "why" is more valuable than a 5-bullet feature list. The user is Glenn — he will challenge weak reasoning in the review session.

---

## Verification before reporting done

After saving your report:

1. `wc -l /opt/flowmanner/.sisyphus/analysis/codex-plugins-adoption-plan-2026-06-28.md` — confirm file exists and is non-trivial (>150 lines)
2. `tail -30` the file — confirm the summary table and count line are present
3. Verify each verdict is one of the allowed strings (Adopt Now | Defer to Q3 | Defer to Q4 | Skip)
4. Count verdicts and confirm they sum to 17

Report:
- Output file path + line count
- Verdict distribution
- Top 3 "Adopt Now" recommendations with first concrete step for each
