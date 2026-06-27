# no-mistakes Deep Dive: Tricks & Patterns for FlowManner

**Date:** 2026-06-28
**Source:** [kunchenguid/no-mistakes](https://github.com/kunchenguid/no-mistakes) (3.2k★, Go, MIT)
**Purpose:** Extract architectural tricks, pipeline design patterns, and prompt-engineering insights applicable to FlowManner's agentic workflow system.

---

## 1. What no-mistakes Is

A **local safety gate** that sits between "code committed" and "code pushed." It runs a multi-step validation pipeline (intent → rebase → review → test → document → lint → push → PR → CI) before allowing changes to reach a configured push target. Written in Go, uses SQLite for run state, talks to local LLM agents (Claude Code, Codex, Copilot, OpenCode, ACPX) via subprocess bridges.

The key insight: **it doesn't trust agents.** Every step is a gate that can pause, auto-fix, or escalate to a human.

---

## 2. Trick #1: Intent as a First-Class Pipeline Citizen

**What they do:** The *very first step* in the pipeline is `IntentStep` — it reads local agent transcripts (Claude Code sessions, Codex histories, Copilot chats) to infer *what the human was trying to accomplish*, then places that intent into `StepContext.UserIntent` so every downstream step's prompt includes it.

**Why it matters for review:** Without intent, a reviewer (human or LLM) can only judge diff content. With intent, the reviewer can distinguish *deliberate decisions* from *mistakes*. A `TODO` left in code might be a bug — or it might be intentional scaffolding the author planned to address later.

**How they extract it:**
- `internal/intent/` has agent-specific readers (`reader_claude.go`, `reader_codex.go`, `reader_copilot.go`, `reader_opencode.go`, `reader_pi.go`, `reader_rovodev.go`)
- A `matcher.go` correlates git commit timestamps with agent session timestamps
- A `disambiguator.go` handles multiple candidate sessions
- A `summarizer.go` compresses transcripts into a short intent string
- `redact.go` strips secrets and adversarial text before the intent is stored/logged
- Results are cached in the DB (`cache.go`) to avoid re-processing

**FlowManner takeaway:** When FlowManner agents produce changes (sandbox code execution, workflow steps), the *human's original request/intent* should be propagated alongside the diff. Our current workflow engine stores the task but doesn't inject it into review/quality-check prompts. Adding this would make LLM-based review significantly more accurate — intent tells the reviewer which surprising diffs are deliberate.

---

## 3. Trick #2: Permission-Triaged Findings (auto-fix / ask-user / no-op)

**What they do:** Every finding from a pipeline step gets an `Action` field:

| Action | Meaning | Who decides |
|--------|---------|-------------|
| `auto-fix` | Mechanical, low-risk — agent can fix without asking | Pipeline auto-cycles |
| `ask-user` | Challenges user intent or product behavior — **must escalate** | Human decides |
| `no-op` | Informational only | No action needed |

**Why this is clever:** It turns a binary pass/fail gate into a **triage system**. Most lints and security issues are `auto-fix` — the pipeline can loop to fix them automatically without human involvement. But anything that touches product behavior *must* go to the human. This prevents the #1 failure mode of automated review: silently "fixing" intentional design decisions.

**FlowManner takeaway:** Our sandbox code review should classify its findings, not just report them. A missing `try/except` is `auto-fix`. Removing a feature flag the user explicitly toggled is `ask-user`. Mixing these up destroys trust. We should add a `finding_action` field to our review output format.

---

## 4. Trick #3: The Auto-Fix Loop with Capped Retries

**What they do:** The executor's `executeStep` method has a built-in fix loop:

```
step.Execute() → findings → auto-fixable? → agent fixes → commit → re-execute → ... → human approval
```

Key constraints:
- `autoFixAttempts < autoFixLimit` — hard cap prevents infinite loops
- Each fix gets committed as `no-mistakes(<step>): <summary>` — deterministic message format
- The previous findings are passed to the next round via `StepContext.PreviousFindings`
- Fix agent prompts explicitly say: *"Before changing code, identify whether each finding is a local defect or a symptom of a deeper design, abstraction, validation, ownership, or test-coverage flaw. Prefer the smallest correct root-cause fix within the changed area over patching only the reported line."*
- Fix prompts also say: *"Do not add code comments explaining your fixes."* — prevents comment-clutter from auto-fixes

**The fix-then-review pattern for CI:** When CI fails, the pipeline doesn't just surface the error — it runs a fix agent that reads the CI output, attempts a fix, commits it, and re-runs CI. This is the `ci_fix.go` + `ci.go` pair.

**FlowManner takeaway:** Our sandbox code execution can fail for trivial reasons (missing import, syntax error). Instead of returning the error to the user, we should attempt 1-2 auto-fix cycles with the error output as context before giving up. The cap is critical — without it, the agent spiral-fixes itself into garbage.

---

## 5. Trick #4: Worktree Steering (Soft Sandbox via Prompt)

**What they do:** `steering.go` wraps every agent invocation with a prepended preamble:

```
Workspace boundary (important):
- Confine source, project, user-data, and system file changes to the current
  working directory, which is a git worktree. Do not intentionally create,
  modify, move, or delete those files anywhere outside it.
- Do not modify system state outside the worktree. In particular, do not
  install or upgrade system packages (brew install/upgrade, etc.), do not
  modify applications under /Applications, and do not change global or
  user-level tool configuration.
- This is prompt steering, not true enforcement: treat the worktree boundary
  as a soft boundary you must follow.
```

And the wrapping is **idempotent** — if the agent is already wrapped, it returns unchanged. This prevents double-preambling.

**FlowManner takeaway:** Our sandbox already has Docker isolation (hard enforcement), but we should add similar steering prompts to agent calls that run *outside* the sandbox — e.g., Celery tasks that modify the filesystem. The phrase "This is prompt steering, not true enforcement" is a nice honesty touch that also makes the agent take the boundary more seriously (it knows it's being asked, not forced).

---

## 5.5. Trick #4b: Structured Output Injection (Schema-Appended Prompts)

**What they do:** When a step needs structured output from an agent (e.g., a JSON findings list), no-mistakes doesn't use function-calling or tool-use. Instead, it appends a JSON Schema contract to the prompt:

```
## no-mistakes final output contract

When the task is complete, your final assistant message must be a single
JSON object that matches this JSON Schema. Return only the JSON object.
Do not wrap it in Markdown fences. Do not include prose before or after
the JSON.

<schema here>
```

And the ACPX agent (`acpx.go`) passes `--format json --json-strict --approve-all --non-interactive-permissions deny --suppress-reads` to enforce structured output from the CLI.

**FlowManner takeaway:** For Hermes subagents and sandbox code execution, this is the simplest reliable path to structured output — no API feature dependencies, just prompt engineering. We already use similar patterns for our review skill. The key detail is the explicit "Do not wrap in Markdown fences" — models love to fence JSON blocks.

---

## 6. Trick #5: Finding Deduplication via Fingerprinting

**What they do:** When findings merge across rounds or steps, deduplication uses a two-tier key system:

1. **Finding Key:** Strip ID, Action, Source, UserInstructions → exact structural match
2. **Finding Fingerprint:** Same as above, plus zero the Line number → fuzzy match (same issue on any line)

The matching logic is sophisticated: a fingerprint match only counts if the fingerprint appears *exactly once* in both the item set and the candidate set. This prevents accidentally deduplicating a real pattern (e.g., the same missing-validation bug on lines 42 and 87 — both are real, not duplicates).

**FlowManner takeaway:** When we aggregate review findings across multiple sandbox code executions or sequential agent turns, we'll hit duplicate findings. A simple ID-based dedup isn't enough — the same issue expressed differently by different agents needs fingerprint-level matching. The "exactly once in both sets" guard is the key insight.

---

## 7. Trick #6: Execution Timer Excludes Approval Wait Time

**What they do:** In `executeStep`, the executor explicitly pauses the execution timer during approval waits:

> Tracks *execution-only* time (`executionMS`), explicitly excluding approval wait periods.

This means the telemetry/metrics show how long the *agent* took, not how long the *human* took to respond. The `StepContext.Log` and `StepContext.LogChunk` callbacks also distinguish between "user-visible" logs and "file-only" logs.

**FlowManner takeaway:** Our Celery task timing should separate wall-clock time from "agent thinking time" vs "user wait time." This is essential for profiling — if a sandbox step took 60s, was that 55s of LLM inference or 55s of the user being idle?

---

## 8. Trick #7: Skip-Remaining Cascade

**What they do:** Any step can return `SkipRemaining: true`, which causes the executor to mark *all subsequent steps* as `StepStatusSkipped` and break the loop. This is used by the `rebase` step — if the rebase results in an empty diff (all changes were already in the base branch), there's nothing to review, test, or push.

**FlowManner takeaway:** Our workflow engine should support a "short-circuit" outcome that terminates the remaining pipeline gracefully. Currently, if a FlowManner workflow step produces no meaningful output, subsequent steps still run against empty inputs. A `skip_remaining: true` flag would save LLM calls and reduce latency.

---

## 9. Trick #8: Pipeline "Owns" Findings and Fixes During a Run

**What they do:** The SKILL.md explicitly states:

> While a run is active, never fix findings by editing the code yourself — the pipeline owns both the findings and the fixes.

This is a governance rule, not a technical enforcement. But it prevents the common failure mode where: (1) pipeline surfaces a finding, (2) human or agent manually tweaks the code, (3) pipeline re-runs on a moved baseline and produces different/conflicting findings.

**FlowManner takeaway:** When FlowManner runs an automated review → fix cycle, the fix agent should be the *only* thing modifying code during that cycle. If the user makes concurrent edits, the pipeline should detect the conflict (HEAD SHA changed) and abort/restart rather than continuing on a stale diff.

---

## 10. Trick #9: Multi-Agent Backend with Unified Interface

**What they do:** `internal/agent/` has 6+ agent implementations, all implementing a single `Agent` interface:

```go
type Agent interface {
    Name() string
    Run(ctx context.Context, opts RunOpts) (*Result, error)
    Close() error
}
```

Each backend (Claude, Codex, Copilot, OpenCode, ACPX, RovoDev, PI) has adapter logic for:
- CLI argument construction
- Output format parsing (JSON, SSE, stream)
- Token usage extraction (messy — each CLI reports differently)
- Retry logic with transient-error classification

The `WithSteering()` wrapper is the **decorator pattern** — it prepends the workspace boundary prompt to every agent call, regardless of backend.

**FlowManner takeaway:** FlowManner's LLM calls go through a single `llm_client` abstraction, but we don't have a unified "agent run" interface that handles retries, steering, and structured output extraction. Building one (similar to the `Agent` interface with `RunOpts`/`Result`) would let us swap LLM providers faster and add cross-cutting concerns (steering, telemetry) in one place.

---

## 11. Trick #10: CI Monitoring with Auto-Merge Detection

**What they do:** The CI step doesn't just check "are checks green?" — it monitors for a window *after* checks pass to see if the PR gets merged. But the key design choice:

> The CI step deliberately keeps watching the PR after checks pass, so `axi run` returns `checks-passed` the moment checks are green rather than blocking on the human merge.

This separates *validation complete* from *merge complete*. The pipeline returns control to the user immediately, then monitors in the background.

**FlowManner takeaway:** Our sandbox preview system should do the same — return "ready" to the user when the container is healthy, not when the first request completes. Background health checking is more useful than blocking on first-response success.

---

## 12. Trick #11: Self-Dogfooding — All PRs Must Come Through the Tool

**What they do:** From `CONTRIBUTING.md`:

> **All pull requests to this repository must be raised through `no-mistakes`.** This repo *is* no-mistakes. Contributions should be done using the tool itself, which helps us find the rough edges.

This is a quality flywheel: the tool improves itself by eating its own dog food at the contribution level, not just the dev level.

**FlowManner takeaway:** FlowManner's own workflow engine should dogfood itself — every feature, every deploy, every code change should flow through the same pipeline that we sell to users. Currently, our deploys are manual shell scripts. If we can't eat our own dog food, our users will sense it.

---

## 13. Trick #12: Deterministic Commit Messages for Machine-Authored Changes

**What they do:** `deterministicFixCommitMessage()` produces:

```
no-mistakes(review): add null check for user input
```

The format is `no-mistakes(<step>): <summary>`. This makes it trivial to distinguish human commits from machine commits in git log, and to find/undo all auto-fix commits for a specific step.

**FlowManner takeaway:** Our sandbox code execution produces git diffs in the container, but we don't trace which agent made which change. Adding a deterministic commit message prefix (e.g., `flowmanner(sandbox): ...`) would make audit trails far cleaner. For Hermes subagent work, `hermes(delegate): ...` would similarly clarify ownership in git history.

---

## 14. Architecture Summary: Applicable Patterns for FlowManner

| no-mistakes Pattern | FlowManner Applicability | Effort |
|---|---|---|
| Intent propagation into review prompts | High — inject user task into code review | Low |
| Finding action triage (auto-fix / ask-user / no-op) | High — sandbox review classification | Medium |
| Auto-fix loop with cap | Medium — sandbox error retry | Medium |
| Worktree steering preamble | Medium — Celery agent boundaries | Low |
| Schema-appended structured output | Low — we already do this | — |
| Finding fingerprint dedup | Medium — cross-turn review aggregation | Medium |
| Execution timer vs approval timer | Low — nice for metrics | Low |
| Skip-remaining cascade | Medium — workflow short-circuit | Low |
| Pipeline owns findings/fixes | High — prevent concurrent edit conflicts | Medium |
| Unified Agent interface | High — LLM provider abstraction | High |
| CI monitoring separation | Low — different architecture | — |
| Self-dogfooding requirement | Vision — FlowManner eats its own workflow | High |
| Deterministic machine commit messages | Low — easy audit trail win | Low |

---

## 15. Key Takeaway

no-mistakes is not just a "safety gate" — it's a **multi-agent orchestration framework** that happens to be configured for code review. The deep tricks are:

1. **Intent as context, not just diff** — The difference between "is this code correct?" and "does this code do what the human intended?"
2. **Permission-tiered findings** — Not all problems require the same response path
3. **The fix loop is the product** — The value isn't finding bugs, it's fixing them autonomously while respecting human authority
4. **Prompt steering as soft enforcement** — Works surprisingly well when paired with hard boundaries (git worktrees, Docker)
5. **Dogfooding at the contribution level** — Not using the tool to build the tool, but requiring the tool to accept changes to the tool

For FlowManner's next phase (agentic workflows that actually ship code), patterns #1-3 are the highest-leverage imports. Our agents currently produce output without understanding *why* they were asked. Adding intent propagation and finding triage would make our workflows significantly more trustworthy.
