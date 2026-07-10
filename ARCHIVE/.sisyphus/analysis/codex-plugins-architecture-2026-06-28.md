# OpenAI Codex Plugins — Architecture Tricks & Applicable Patterns

**Date:** 2026-06-28
**Source:** https://github.com/openai/plugins (OpenAI's official Codex plugins repo)
**Target audience:** FlowManner engineering — ideas we can adopt or adapt

---

## 1. The Big Picture: What OpenAI Built

The `openai/plugins` repo is **not** the old ChatGPT plugins-quickstart (that's dead). This is the **new Codex plugins system** (launched March 2026) — a structured way to package and distribute agent capabilities across Codex desktop, CLI, and IDE.

The core insight: **plugins bundle three orthogonal components into versioned, installable packages:**

| Component | Purpose | FlowManner analogue |
|-----------|---------|---------------------|
| **Skills** | Prompt-based instructions (SKILL.md) that guide agent behavior | Our `.hermes/skills/` (Hermes already has this) |
| **Apps** | Connectors to external services (`.app.json`) — OAuth flows, auth, tool discovery | Our marketplace integrations (Slack, Notion, etc.) |
| **MCP Servers** | Remote tools or shared context via Model Context Protocol (`.mcp.json`) | We don't ship MCP servers; we consume them |

A single plugin can define *how* the agent should approach a task (skill), *connect* it to the tools involved (app), and *provide* any specialized capabilities needed (MCP server). The three components are **composable** — you pick what you need.

---

## 2. Tricks Worth Stealing

### Trick 1: Skill-Bound Subagent Orchestration with `$phase` Invocation

**What they do:** The `codex-security` plugin has a top-level `security-scan` skill that acts as an orchestrator. It **invokes other skills by name** using a `$skill-name` syntax:

```
1. $threat-model
2. $finding-discovery
3. $validation
4. $attack-path-analysis
5. Generate final output
```

Each sub-skill has its own SKILL.md with its own workflow, preconditions, and output shape. The orchestrator skill enforces **strict linear ordering** and treats itself as a "top-level orchestrator for the four skills plus final report."

**Why it matters for us:** We already have skills in Hermes. But we don't have a pattern where one skill explicitly orchestrates others by name with sequencing guarantees. This would let us build composite workflows (e.g., `$investigate → $fix → $verify`) that are more than just prompt chains — they're **guaranteed-phase workflows**.

**Adaptation idea:** A "marketplace integration setup" skill that orchestrates: `$choose-phase → $generate-migration → $generate-model → $generate-api → $verify-scan`. Each phase is independently testable and can be run standalone.

---

### Trick 2: Capability Preflight — Declare Requirements Before Execution

**What they do:** Before any security scan runs, there's a **capability preflight** check (`preflight/capability-profiles.toml`). The skill says:

> "Dispatch and await preflight execution with the `security_scan` profile **before** substantive scan work."

Preflight results are: `ready` (continue), `ready` with warnings, `blocked` (stop and ask), or `incomplete` (actionable remediation needed). The skill **does not proceed** until preflight is resolved.

**Why it matters:** This is a **guard rail pattern** we don't have. When our agents start complex workflows (deploy, migration, integration setup), there's no pre-check that validates the environment is actually ready. We discover failures mid-execution.

**Adaptation idea:** A preflight check before `deploy-backend.sh --migrate` that verifies: DB reachable, migrations directory clean, Docker daemon running, disk space adequate. Before `deploy-frontend.sh`: VPS SSH reachable, Docker compose target alive. The preflight result is explicit — `ready`, `ready-with-warnings`, `blocked` — and the workflow **stops for human input** on `blocked`.

---

### Trick 3: Cross-Skill Dependencies with Explicit `references/` Directories

**What they do:** Nearly every skill has a `references/` folder containing structured reference docs that other skills can rely on:

- `notion-spec-to-implementation` has `reference/spec-parsing.md`, `reference/standard-implementation-plan.md`, `reference/task-creation.md`
- `notion-knowledge-capture` has `reference/team-wiki-database.md`, `reference/decision-log-database.md`, `reference/faq-database.md`
- `figma-use` has `references/plugin-api-standalone.index.md`, `references/working-with-design-systems/wwds.md`

These are **not** inline docs. They're separate files loaded on demand by the agent when the skill triggers. The SKILL.md tells the agent *when* to load them and *what* to grep for.

**Why it matters:** Our Hermes skills are self-contained SKILL.md blobs. There's no way for skill A to reference a shared data structure that skill B also uses. This means we duplicate context or lose it.

**Adaptation idea:** Marketplace integration skills could share a `references/marketplace-schema.md` with the canonical field definitions for all phases. Integration-specific skills could add their own `references/slack-api-reference.md`, `references/notion-api-reference.md`, etc. Skills would say: "Load `references/marketplace-schema.md` first, then proceed."

---

### Trick 4: Tool-Call Guardrails — "If Tool Not Found, Stop Retrying"

**What they do:** The Notion plugin has **explicit guardrails** in every skill:

> "If a Notion MCP call returns `Tool not found`, treat that tool as unavailable for the rest of the current task. Do not retry it with different arguments or call it again later."

> "Use one literal search query per `Notion:search` call. If several query variants are useful, issue separate searches instead of writing `or` or `+` inside one query string."

These aren't just tips — they're **hard rules baked into the skill**. The agent will follow them consistently across invocations.

**Why it matters:** Our agents sometimes retry failed tool calls with slightly different arguments, burning tokens and time. The "stop retrying missing tools" pattern alone would save real cycles.

**Adaptation idea:** Add tool-call guardrails to our marketplace integration skills: "If a specific Slack API call returns 403, treat the Slack integration as unauthorized and stop. Do not retry with different scopes. Ask the user to re-authenticate."

---

### Trick 5: Workspace Routing — App vs CLI Paths

**What they do:** The `security-scan` skill has a **dual-path entry**:

```
**App Path Condition:** Use the Codex Security app setup tools *only* when the host context
explicitly identifies itself as the Codex desktop app AND both required setup continuation
tools are available. Tool availability alone ≠ app host.

**Non-App Path (Codex CLI/Terminal/Chat):** Use the prompt-only terminal/chat workflow.
```

Same skill, different execution path depending on runtime context. The app path gets richer UI (workspace panels, scan progress). The CLI path gets prompt-only output.

**Why it matters:** Our agents run in different contexts — TUI, Telegram, cron, web. But skills don't adapt to context. A deploy skill works the same way whether you're in Telegram (where you can't see full logs) or in the TUI (where you can).

**Adaptation idea:** Skills that detect their runtime and adapt behavior. In Telegram: "Summarize deploy status in ≤4096 chars, link to full logs." In TUI: "Stream full deploy output, prompt for rollback on failure." The skill itself declares the routing, not the caller.

---

### Trick 6: Mandatory Skill Loading Before Tool Calls

**What they do:** The `figma-use` skill is declared as a **mandatory prerequisite**:

> "**MANDATORY prerequisite** — you MUST invoke this skill BEFORE every `use_figma` tool call. NEVER call `use_figma` directly without loading this skill first."

The skill contains critical API rules (color ranges, font loading, read-only arrays) that the agent needs to avoid bugs. Without the skill loaded, the agent will produce broken output.

**Why it matters:** We have tools where misuse causes real problems (DB operations, deploy scripts, migration runs). But we don't enforce skill loading before tool use.

**Adaptation idea:** Skills for dangerous tools that say "MUST be loaded before `deploy-backend.sh --migrate`". The skill contains the pitfalls (don't retry timed-out deploys, check Docker compose status first, never run two deploys simultaneously). The agent loads it automatically when the task mentions the tool.

---

### Trick 7: Incremental Execution — "Work in Small Steps, Validate After Each"

**What they do:** The Figma `figma-use` skill has this as the **#1 most important practice**:

> "Work incrementally in small steps. Break large operations into multiple tool calls. Validate after each step. This is the single most important practice for avoiding bugs."

And then the skill enforces it: "Forbidden: any `use_figma` call that mutates the canvas until all Step 2 rows in the checklist are filled."

**Why it matters:** Our agents sometimes try to do too much in one shot (run a migration + deploy + smoke test in one command). When it fails, we lose context about *where* it failed.

**Adaptation idea:** Make "incremental execution" a first-class skill pattern. "Run migration. Verify migration. Only then proceed to deploy. Only then run smoke test." Each step is a separate tool call with explicit verification between steps.

---

### Trick 8: The Marketplace as a JSON Catalog, Not a Registry

**What they do:** Marketplaces are just JSON files:

```json
{
  "name": "local-repo",
  "plugins": [
    {
      "name": "my-plugin",
      "source": { "source": "local", "path": "./plugins/my-plugin" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    }
  ]
}
```

There are **two marketplace scopes:**
- **Repo-scoped:** `$REPO_ROOT/.agents/plugins/marketplace.json` — team-shared
- **Personal:** `~/.agents/plugins/marketplace.json` — individual developer

And a separate API-key marketplace at `.agents/plugins/api_marketplace.json`. The CLI can add marketplaces from GitHub repos, local paths, or URLs:

```bash
codex plugin marketplace add owner/repo
codex plugin marketplace add ./local-marketplace-root
```

**Why it matters:** Our marketplace system is backend-driven (database rows, API endpoints). The Codex approach is **file-driven** — a marketplace is a JSON file that lives next to your code. This means:
1. Marketplaces are version-controlled with the code
2. Different repos can have different plugin sets
3. Adding a marketplace is a one-line CLI command, not a database migration

**Adaptation idea:** We could support a "marketplace companion file" — a `.flowmanner/marketplace.json` checked into the repo that lists which integrations are configured for this project. The backend marketplace is still the source of truth for installed/configured integrations, but the companion file declares intent and makes marketplace additions reviewable in PRs.

---

### Trick 9: Default Prompts — "Seed Prompts" for Plugin Discovery

**What they do:** Every plugin manifest has `interface.defaultPrompt` — an array of seed prompts that show up as quick-start options:

```json
"defaultPrompt": [
  "Run a Codex Security scan on this repository.",
  "Run a Codex Security diff scan on this PR.",
  "Triage existing security findings against this repository."
]
```

When a user installs a plugin and isn't sure what to do, these prompts teach them the capability surface.

**Why it matters for us:** Our marketplace integrations are invisible until a user navigates to settings. There's no "so you installed Slack — here's what you can do" moment. The first interaction becomes a discovery problem, not an execution problem.

**Adaptation idea:** Each marketplace integration ships with 2–3 seed prompts shown in the chat UI after onboarding completes. Slack: "Summarize my team's recent messages," "Find action items from yesterday's standup." Notion: "Turn this spec into implementation tasks," "Capture this decision." These become the first thing a user sees after connecting — zero-friction activation.

---

### Trick 10: Authentication Policy — `ON_INSTALL` vs `ON_USE`

**What they do:** The marketplace catalog declares an authentication policy per plugin:

```json
"policy": {
  "installation": "AVAILABLE",
  "authentication": "ON_INSTALL"  // or "ON_USE"
}
```

- **`ON_INSTALL`** (default for 137/140 plugins): Auth flow runs at install time. The plugin is ready to use immediately.
- **`ON_USE`** (only 3 plugins — `build-web-apps`, `build-web-data-visualization`, `codex-security`): Auth deferred until first use. Makes sense when auth is heavy (security scans need credentials scoped to the repo) or when most installs won't actually use the capability.

**Why it matters:** We currently auth at connection time (OAuth flows during onboarding), which is the `ON_INSTALL` pattern. But some integrations have heavy auth (e.g., scopes that require admin approval in Slack workspaces) where deferring would reduce onboarding drop-off.

**Adaptation idea:** Support `auth_timing: "on_connect" | "on_first_use"` in our integration manifest. Lightweight integrations (webhooks, read-only) auth on connect. Heavy integrations (admin-scoped Slack, write-back Jira) defer until the first actual API call that needs it.

---

### Trick 11: Plugin Manifest Validation with Strict Release Gates

**What they do:** The Codex plugin system has a **release validation pipeline** (enforced via PR #161) that checks plugins before they enter the marketplace:

- Required plugin.json fields: `version`, `author.name`, `skills`, `interface.developerName`, `interface.brandColor`, `interface.longDescription`, `interface.{privacyPolicyURL, termsOfServiceURL, websiteURL, screenshots}`
- Every skill **must** have an `agents/openai.yaml` file
- Every skill manifest **must** have `interface.short_description`
- **Prohibited keys** are explicitly listed: `license`, `user-invocable`, `compatibility`, `alwaysApply` in SKILL.md frontmatter; `hooks`, `mcpServers` in plugin.json
- Plugins with root `.mcp.json` are **dropped from release import** entirely (cloudflare, build-ios-apps were cut)

This is aggressive validation — not lint warnings, but hard blocks.

**Why it matters:** Our marketplace integrations are validated by backend logic, but there's no schema enforcement at the manifest level. A malformed integration slips through until runtime. There's no pre-release gate.

**Adaptation idea:** A `marketplace-integration-schema` (JSON Schema or Pydantic model) that all integrations must pass before the marketplace API accepts them. Required fields, prohibited fields, type constraints. The TTTC onboarding wizard generates conformant manifests. If it doesn't validate, it doesn't ship.

---

### Trick 12: Dual-Scope Marketplaces — Repo vs Personal

**What they do:** There are two marketplace scopes:

| Scope | Location | Who sees it |
|-------|----------|-------------|
| **Repo-scoped** | `$REPO_ROOT/.agents/plugins/marketplace.json` | Everyone who clones the repo |
| **Personal** | `~/.agents/plugins/marketplace.json` | Only this developer |

Repo-scoped marketplaces are team-shared. Personal marketplaces are for individual tooling. The CLI merges them at resolution time.

**Why it matters:** Our integrations are global per-user. If I add a Jira integration, it's there for every repo I work on. But some integrations are repo-specific (e.g., a specific Slack workspace channel for a specific project's deploy notifications). Currently there's no way to scope integrations to a project.

**Adaptation idea:** `.flowmanner/integrations.json` per project (like `.vscode/settings.json`) that declares which integrations are active and configured for *that project*. The backend config is still user-global, but project-level manifests can subset/override it. "This project uses Slack #deploys and Notion, but not Jira."

---

### Trick 13: The `agents/openai.yaml` Layer — Skill-to-Agent Interface Contract

**What they do:** Every skill has an `agents/openai.yaml` that defines how the skill presents to the Codex agent runtime:

```yaml
interface:
  display_name: "Security Scan"
  short_description: "Run repository or scoped-path security scan"
  default_prompt: "Run a Codex Security scan on this repository..."
```

This is a **separate file from SKILL.md**. The SKILL.md contains the *behavior* (workflows, rules, references). The `agents/openai.yaml` contains the *interface contract* (name, description, default prompt). The agent runtime reads the YAML; the agent reads the SKILL.md.

**Why it matters:** Our SKILL.md files mix interface and behavior. The frontmatter has `name` and `description` interleaved with the skill instructions. This means changing how a skill *presents* requires editing the same file that defines how it *behaves*.

**Adaptation idea:** Split Hermes skills into `SKILL.md` (behavior — workflows, rules, pitfalls) and `skill.yaml` (interface — name, description, trigger conditions, default prompt). The skill loader reads `skill.yaml` first; the agent only loads full `SKILL.md` when the skill is activated. This is a low-priority refactor but would make our future marketplace skill packaging cleaner.

---

### Trick 14: Orchestrator–Worker Pattern with Ordinal Completion Tracking

**What they do:** The `deep-security-scan` skill uses a coordinator/worker pattern:

1. **Coordinator** creates a shared worklist, assigns file-ranges to workers, tracks completion receipts
2. **Workers** (exactly 6 per round) independently run discovery on their assigned ranges
3. After all workers complete, the coordinator **semantically merges** candidates, deduplicates, then runs centralized validation/attack-path analysis **once**
4. Goal completion requires: *every* worklist row has a completion receipt, *every* candidate has required ledger receipts, and the final report is written

The key insight: **the coordinator doesn't just dispatch — it tracks ordinal completion.** A row is done only when it has an explicit receipt. A finding is validated only when its ledger entry has a receipt. This eliminates the "I think I'm done" problem.

**Why it matters:** Our subagent delegation (`delegate_task`) returns a summary, but there's no structured receipt system. The parent agent gets a prose description, not a machine-readable completion artifact. When a subagent claims "all 50 files checked," we believe it.

**Adaptation idea:** For complex multi-step workflows (codebase audits, batch migration generators), add a lightweight receipt system. Each subtask returns `{status: "completed" | "skipped" | "failed", items_processed: N, items_total: M, artifacts: [...]}`. The coordinator checks `items_processed == items_total` before declaring "done." No more trusting prose summaries.

---

### Trick 15: Product-Restricted Plugins (`products: ["CODEX"]`)

**What they do:** Some plugins are restricted to specific products via policy:

```json
"policy": {
  "products": ["CODEX"]
}
```

15 plugins are Codex-exclusive. This means the same plugin catalog can serve multiple OpenAI products (ChatGPT, API, Codex) with different availability per product.

**Why it matters:** As FlowManner grows, we'll have different surfaces (web app, mobile, API, agent SDK). Some integrations make sense everywhere (Slack notifications). Others only make sense in specific surfaces (e.g., a "deploy from CI" integration only matters in the agent SDK).

**Adaptation idea:** Add a `surfaces` field to integration manifests: `["web", "agent", "mobile", "api"]`. The marketplace API returns only integrations available for the requesting surface. This costs nothing now and prevents a painful migration later.

---

### Trick 16: Finding Ledger — Every Discovery Gets an Explicit Stardust Trail

**What they do:** The security plugin maintains a **candidate ledger** — a structured file tracking every finding through its lifecycle:

| Field | Purpose |
|-------|---------|
| Candidate ID | Unique identifier |
| Status | `open`, `reportable`, `suppressed`, `deferred`, `not_applicable` |
| Discovery receipt | What was found, where, when |
| Validation receipt | Method, evidence, confidence |
| Attack-path receipt | Exploit chain analysis |

**Every candidate must have a receipt in every phase** — even suppressed ones need an explicit reason. The ledger is the source of truth for "what happened," not the agent's memory.

**Why it matters:** When our agents do multi-step investigations (bug triage, integration debugging), they rely on conversation context for tracking what they've checked. If the context window resets, the investigation restarts from scratch. No durable record.

**Adaptation idea:** For long-running workflows, write an investigation log (`.hermes/investigations/<id>.md`) that the agent can reload. Each step appends a timestamped entry: "Checked X, result Y, next: Z." If the agent context resets, it reads the log and picks up where it left off. This is especially valuable for cron-triggered investigations where session state doesn't persist.

---

### Trick 17: Escalated Sandbox Permissions — Declared, Not Sneaked

**What they do:** The Netlify deploy skill has an explicit escalation pattern:

> "If deployment fails due to network issues, rerun with escalated permissions: `sandbox_permissions=require_escalated`"

The skill **asks the user before escalating**. It doesn't silently `--no-verify` or force-through. The user is informed and consents.

**Why it matters:** Our deploy scripts sometimes need elevated permissions (SSH to VPS, Docker daemon access, DB connections). Currently these are either allowed unconditionally or blocked with no recourse. There's no middle ground of "ask once and temporarily escalate."

**Adaptation idea:** A `--escalate` flag pattern for our scripts. `deploy-backend.sh --migrate` runs in restricted mode by default (no DB access). If migration is needed, it prints: "Migration requires database access. Run with `--escalate=migrate` or confirm in TUI." The escalation is one-time and explicit.

---

## 3. Summary: What's Worth Building

| Priority | Trick | Effort | Impact |
|----------|-------|--------|--------|
| 🔴 **Now** | Trick 4: Tool-call guardrails ("stop retrying") | Low — add to existing skills | High — saves tokens + frustration |
| 🔴 **Now** | Trick 7: Incremental execution | Low — pattern in skills | High — prevents cascading failures |
| 🔴 **Now** | Trick 17: Escalated permissions | Low — flag pattern | Medium — safer deploys |
| 🟡 **Soon** | Trick 1: `$phase` sub-skill orchestration | Medium — new skill pattern | High — composable workflows |
| 🟡 **Soon** | Trick 2: Capability preflight | Medium — preflight scripts | High — catches env issues early |
| 🟡 **Soon** | Trick 9: Default/seed prompts | Medium — UI change | High — activation + discovery |
| 🟡 **Soon** | Trick 16: Investigation ledgers | Medium — file-based log | Medium — durable audit trail |
| 🟢 **Later** | Trick 3: `references/` shared docs | Low — directory convention | Medium — reduces context duplication |
| 🟢 **Later** | Trick 5: Workspace routing (app vs CLI) | Medium — runtime detection | Medium — better UX per surface |
| 🟢 **Later** | Trick 6: Mandatory skill loading | Medium — trigger system | Medium — prevents tool misuse |
| 🟢 **Later** | Trick 8: File-driven marketplace companion | Medium — new JSON schema | Medium — PR-reviewable config |
| 🟢 **Later** | Trick 10: Auth timing policy | Medium — backend change | Low–Medium — niche UX win |
| 🟢 **Later** | Trick 11: Strict manifest validation | Medium — schema + CI gate | Medium — prevents bad data |
| 🟢 **Later** | Trick 12: Repo vs personal marketplaces | High — scoping layer | Low — niche until many projects |
| ⚪ **Maybe** | Trick 13: Skill/agent interface split | Low–Medium — refactor | Low — cleanliness only |
| ⚪ **Maybe** | Trick 14: Ordinal completion receipts | High — receipt system | Medium — overkill for current scale |
| ⚪ **Maybe** | Trick 15: Product-restricted plugins | Low — manifest field | Low — one surface today |

---

## 4. What OpenAI Got Wrong (Lessons for Us)

1. **140 plugins but only 1 security plugin.** The ecosystem is breadth-first, not depth-first. Most plugins are shallow wrappers. We should prefer 5 deep integrations over 50 shallow ones.

2. **Prohibiting `.mcp.json` in release.** The validation pipeline bans MCP server packaging. This means the most powerful integration pattern (giving the agent new tools) is *not allowed in the official marketplace*. We should do the opposite — make MCP-native integrations first-class.

3. **`skills` can only reference files within the plugin.** Skills in a plugin can't import from other plugins. The `$skill-name` cross-plugin invocation works, but there's no shared reference material. Our `references/` trick (Trick 3) works best when references are *cross-plugin*.

4. **No telemetry on skill usage.** The `resource:figma-use` logging parameter is the closest thing — it tracks which skill was loaded when a tool was called. But there's no feedback loop about whether the skill *worked*. We should track skill effectiveness, not just invocation.

5. **The orchestrator pattern is over-specified.** The deep-security-scan skill has 6 workers per round, ordinal receipts, and non-negotiable invariants. This is necessary for security (false negatives are dangerous) but overkill for most workflows. Our orchestration should be lighter — order matters, completion matters, but we don't need military-grade process tracking for deploy scripts.

---

## 5. Codex Plugin Anatomy (Reference)

For anyone implementing these patterns, here's the canonical structure of a Codex plugin:

```
my-plugin/
├── .codex-plugin/
│   └── plugin.json          # Manifest: name, version, author, skills/, apps, mcpServers, interface
├── skills/
│   └── my-skill/
│       ├── SKILL.md         # Behavioral instructions (workflows, rules, pitfalls, references)
│       └── agents/
│           └── openai.yaml  # Agent interface contract (display name, short desc, default prompt)
├── .app.json                # App connector (OAuth, auth flows, tool discovery)  [optional]
├── .mcp.json                # MCP server definition                                [optional]
├── assets/                  # Logos, icons, screenshots
├── references/              # Shared reference docs loaded on demand by skills
├── examples/                # End-to-end walkthroughs
└── scripts/                 # Executable helpers (preflight, generators, etc.)
```

**Key manifest fields** (`plugin.json`):
- `interface.defaultPrompt` — seed prompts shown on install
- `interface.capabilities` — `["Interactive", "Read", "Write"]`
- `interface.category` — marketplace categorization
- `policy.authentication` — `"ON_INSTALL"` or `"ON_USE"`
- `policy.products` — product restriction (e.g., `["CODEX"]`)
- `skills` — path to skills directory
- `apps` — path to app config
- `mcpServers` — path to MCP config

**Skill manifest** (SKILL.md frontmatter):
- `name`, `description` — identity
- `metadata.short-description` — one-liner for UI
- `disable-model-invocation: false` — allow/disable auto-invocation by the model

**Agent interface** (`agents/openai.yaml`):
- `interface.display_name`, `interface.short_description` — how the skill appears in agent tool surface
- `interface.default_prompt` — what the agent sends when it first activates the skill
