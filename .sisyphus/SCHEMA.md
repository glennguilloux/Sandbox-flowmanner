# .sisyphus/ — knowledge-substrate schema

**Status:** PROPOSAL — not yet adopted. Doc-only; verify via `SESSION-RITUAL.md`, not `make test`.
**Source:** Adapted from AI-Builder-Club/skills `new-loop` (`ARCHITECTURE.md` + `KNOWLEDGE_SETUP.md`),
re-flavored to Flowmanner's existing `.sisyphus/` layout and `**Key:**` metadata convention.
**Motivation:** `.sisyphus/` is growing folder-by-folder with no enforced shape. Two concrete wounds:
- `plans/frontend-wiring-roadmap.md` carries `**Status:** ✅ COMPLETE` but its own body says
  "Frontend: Nothing" — a stale stamp with no history of *when* or *why* it changed.
- New subfolders (`analysis/`, `gold-audit/`) were added on feel, not on a justified "kind" gate,
  so cross-cutting retrieval by `ripgrep`/`[[slug]]` stays loose.

This doc is the durable record of the model and the rejected options, so the shape stays
intentional as it grows. It layers discipline on the *existing* folders — it does **not** rename
or relocate anything.

---

## The model (v1 — deliberately minimal)

Two ideas, both already half-present in this repo:

1. **Artifacts are global, foldered by `kind`; `**Workstream:**` is a field (a list), not a folder.**
   Each artifact has exactly one home (by *what it is*). Cross-cutting is handled by a
   `**Workstream:**` field + `[[slug]]` links — never by duplicating or by nesting inside a
   workstream folder. (Flowmanner already does this right: everything plan-like lives in
   `plans/`, not in per-mission folders.)
2. **Every artifact has a two-layer body:** main body = "what's true now"; an appended,
   append-only `## Timeline` = "what happened" (dated). Git holds the mechanical diff; the
   Timeline holds the *narrative* diff an agent can read without `git log`.

---

## Kinds (start with what exists)

| kind | folder | what it is | key metadata |
|---|---|---|---|
| `plan` | `plans/` | a roadmap / decomposition / handoff | `**Status:**`, `**Created:**`, `**Last verified:**`, `**Workstream:**` |
| `analysis` | `analysis/` | an audit / investigation with `path:line` evidence | `**Status:**`, `**Evidence base:**` |
| `gold-audit` | `gold-audit/` | a multi-persona cross-validation ledger | `**Compiled:**`, `**Question answered:**` |

That's enough to run almost any session. **Do not create a new top-level folder** until the
"earn a kind" gate below is met. Retire, don't delete: move stale trees to `plans/OLD/` (the
existing convention) — `OLD/` is the retire path, not a new idea.

### Earn a kind (gate before any new `.sisyphus/<folder>/`)

Default to an existing kind with a `**Kind:**` line in the body. Add a **new top-level folder**
only when it has **all three** of:

- its own **status machine** (distinct lifecycle states, not just draft/done), **and**
- **queryable metadata fields** (things you'd `ripgrep` for), **and**
- a **distinct body shape**.

Otherwise it's an existing kind with a tag, or a backlog line in an existing plan. Examples teams
have earned elsewhere once volume justified them: `task` (committed work as its own files),
`ticket` (helpdesk sync), `content` (publish lifecycle), entity kinds (`lead`, `keyword`).
If you can't name the distinct status machine, you haven't earned the kind yet.

### Workstream field (cross-cutting, not folders)

A plan/analysis can touch several missions. Tag it instead of nesting it:

```
**Workstream:** mission-replay, hil-dashboard, v3-auth
```

Multi-tag + multi-link. Never create `plans/<mission>/` subfolders.

---

## The `## Timeline` two-layer convention (mandatory for substantive artifacts)

Adopted from AI-BC `ARCHITECTURE.md` "Body convention — two layers." Add this to every
non-trivial `.sisyphus/` artifact:

```markdown
## Timeline

YYYY-MM-DD | <actor: hermes/deepseek/glenn/kanban> — <what changed, one line>
```

Rules:
- **Append-only.** Never edit or delete a Timeline line (that's what git is for). To correct,
  append a new line: `2026-07-15 | hermes — corrected Status: COMPLETE→IN-PROGRESS; body said "Frontend: Nothing"`.
- **`frequency` = Timeline entries** for signals/observations (mirrors AI-BC `signal` kind).
- **Detail stays in artifacts; the Timeline is the index.** One terse dated line per change.

### Motivating example — `plans/frontend-wiring-roadmap.md` (current → proposed)

Current header bakes the contradiction into a single mutable stamp:

```
**Status:** ✅ COMPLETE — all three Tier-1 features shipped and verified
**Last verified:** 2026-07-08
```

Proposed (the stamp can't lie anymore — the Timeline shows the correction):

```
**Status:** 🟡 IN-PROGRESS — Tier-1 UI built; backend-shape alignment partial (see Timeline)
**Created:** 2026-07-01
**Last verified:** 2026-07-08

## Timeline

2026-07-01 | hermes — created from MoA backend-vs-frontend gap audit
2026-07-08 | hermes — stamped COMPLETE after 5 feature commits landed
2026-07-11 | glenn — body self-contradicts ("Frontend: Nothing"); downgraded to IN-PROGRESS
```

The point: a reader in 2026-09 sees *why* the status is what it is without spelunking git.

---

## Metrics stay in JSON, not markdown

`boulder.json` already proves the precedent. Numeric time-series / scorecards belong in
`*.json` (or `*.jsonl`), written by **deterministic code/skills, not the LLM** — "collectors
write data; agents write knowledge." Agents read & interpret; they don't regenerate numbers.
Markdown is for *what's true now* + *why*; JSON is for *measurements*.

---

## Rules (DRY + MECE)

1. **One concept = one home** (by kind). Everyone else links via `[[slug]]`.
2. **`**Workstream:**` is a field, not a folder.** Cross-cutting = multi-tag + multi-link.
3. **Collectors write data; agents write knowledge.** Don't pay an LLM to fetch numbers.
4. **Metadata = anything you'd query** (`**Status:**`, `**Workstream:**`, `**Last verified:**`).
   Prose for everything else.
5. **Every substantive artifact gets a `## Timeline`.** Stamp-now, history-forever.

---

## Deferred — add only when the need is real (do NOT pre-build)

| Later | Trigger to add it |
|---|---|
| derived index (sqlite / vector over `.sisyphus/`) | retrieval volume outgrows `ripgrep` (~10⁴⁺ artifacts) |
| reconcile / consolidation daemon | autonomous volume creates dupes / contradictions |
| formal `trigger:` field (cron / webhook) | a plan needs to be machine-activated, not human-opened |
| `task` kind as own files | backlogs outgrow a plan's `## Backlog` section |

The substrate extends to all of these without a rebuild (markdown stays system-of-record; you
layer a cache/daemon on top).

---

## Adoption path (low-friction, doc-only)

1. Land this `SCHEMA.md` (no code change; passes path-aware verification scoping).
2. Add a `## Timeline` to the two highest-value living docs now:
   `plans/frontend-wiring-roadmap.md` and `gold-audit/GOLD-LEDGER.md`.
3. Link this file from `AGENTS.md` (one line under "Docs") so future agents follow it.
4. Apply the "earn a kind" gate to the *next* new folder request — nothing retroactive.

No file moves, no renames, no test suite touched. The gate only fires on *new* structure.
