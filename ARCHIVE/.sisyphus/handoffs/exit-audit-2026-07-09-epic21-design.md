# EXIT AUDIT — Epic 2.1 Canonical-Store Design Doc

**Date:** 2026-07-09 | **Machine:** homelab `/opt/flowmanner/backend` | **Agent:** Hermes
**Continues from:** `exit-audit-2026-07-09-gov16-feedback-loop.md`.
**Context:** GOV-1.1–1.6 (Epic 1) locked + pushed (HEAD `050af5f0`, `git status` clean,
`origin/main` up to date). Epic 2 (store reconciliation) now unblocked per the GOV-1.6
handoff. This session authors the **2.1 design doc** (design-doc-first item from the
backlog skeleton) and runs the session ritual.

## WHAT CHANGED (one bullet per file, what + why)

- `docs/research/EPIC-2.1-CANONICAL-STORE-DESIGN.md` (NEW): the Epic 2.1 design doc.
  Decides `personal_memory_claims` is the single canonical governed store; demotes
  `memory_entries` to legacy/agent-KV. Designs the promotion pipeline that re-points the
  reviewer's write path (direct + HITL-approved) from `memory_entries` onto
  `PersonalMemoryService` so Epic-1 governance (1.1–1.6) actually applies to reviewer
  memory. All claims cited to live code (file:line).

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- No source files touched. No migrations. No deletions. Pure design-doc session.

## SCOPE NOTES (why this is "design not build")

Epic 2.1 is explicitly a **design-doc-first** item in the backlog skeleton
(`FLOWMANNER-MEMORY-BACKLOG-SKELETON.md` → 2.1: "Design doc first: `MemoryEntry` → claim
promotion vs union-at-recall vs single store. All promoted writes route through 1.1/1.2.").
This session produces the design + decision only. Implementation is left for Glenn's
review/approval (localized writer re-point + a `create_from_proposal` adapter + dead
`MemoryIntegration` disable — see §3.3/§3.4/§5.5 of the doc; **no migration required**).

### Key finding that drove the decision (verified against code)

The reviewer WRITES to `memory_entries` but the live agent READS `personal_memory_claims`
only — an orphaned-write / starved-read split:

- Write path → `memory_entries`: `background_review_service.py:257` `add_reviewed_entry`,
  `:461` `resolve_pending_write` (HITL-approved → `:525`/`:548`), `:833`
  `apply_proposed_writes` (direct ADD → `:874`).
- Read path → `personal_memory_claims` only: `chat_service.py:441` →
  `recall_for_chat` (`memory_citation_service.py:174`) → `PersonalMemoryService.recall`
  (`:206`, `:425`). `grep` for `memory_entries|MemoryEntry` across the live chat path
  returns **zero** reads.
- `memory_entries` readers (`memory_service.py:305` `retrieve_by_query`,
  `nexus/memory_integration.py:47` `inject_memories`) are **unwired** — no caller outside
  their own modules. So `memory_entries` is effectively dead for personal memory.
- Governance gap: `memory_entries` has nullable `workspace_id`, no `claim_type`/`scope`/
  `sensitivity`, no soft-delete/expiry, no `source_type` provenance → GOV-1.2/1.3b/1.4
  cannot apply to it. Making claims canonical is what makes Epic 1's controls real.

### The decision

**Option A — promote `MemoryEntry`→claim** (re-point writer to `PersonalMemoryService`).
Rejected B (union-at-recall: perpetuates the ungoverned store) and C (single new store:
throws away the already-governed claims table + read path). Full reasoning + pipeline
mapping + acceptance criteria in the doc.

## TESTS RUN + RESULT

Doc-only session. Per AGENTS.md critical rule #6, doc-only changes skip the full
`make test`/`make lint`/`make build` suite — verified by the ritual checklist instead.
No source changed, so no pytest run is meaningful (and the doc is gitignored, see STATUS).
(For reference, the GOV-1.6 handoff that this continues left the suite green:
`50 passed` on `test_memory_feedback_loop.py` + calibration + drain + poison + sweep.)

## STATUS (raw output)

```
□ git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean

□ git fetch origin && git log --oneline origin/main..main
(empty = pushed)

□ ls -la docs/research/EPIC-2.1-CANONICAL-STORE-DESIGN.md
-rw------- 1 glenn glenn 18737 Jul  9 14:21 docs/research/EPIC-2.1-CANONICAL-STORE-DESIGN.md

□ git check-ignore -v docs/research/EPIC-2.1-CANONICAL-STORE-DESIGN.md
.gitignore:93:docs/research/   docs/research/EPIC-2.1-CANONICAL-STORE-DESIGN.md
```

**NOTE on tracking:** `docs/research/` is gitignored (`.gitignore:93`) by project
convention — the backlog skeleton that named this task lives there too, and
`.sisyphus/handoffs/` (this audit) is gitignored as well (`.gitignore:80`). These are
intentional *local working artifacts* reviewed by Glenn, not committed to the repo. So
there is **nothing tracked to commit or push** this session — the ritual's
"commit + push" is satisfied vacuously. The design doc is on disk and reviewable at
`/opt/flowmanner/docs/research/EPIC-2.1-CANONICAL-STORE-DESIGN.md`.

If Glenn wants the design doc version-controlled (force-add past the gitignore), say so
and it's a one-line `git add -f`. Left as a decision for Glenn per AGENTS.md rule #5.

## NEXT SESSION HANDOFF

Epic 2.1 design is **written and decisioned** (canonical store = `personal_memory_claims`;
reviewer writes must route through `PersonalMemoryService`). The build is a low-blast-radius
writer re-point (localized to `BackgroundReviewService.add_reviewed_entry` + `supersede_entry`,
plus a new `PersonalMemoryService.create_from_proposal` adapter, plus disabling the dead
`MemoryIntegration`) — **no migration**. Glenn should review the doc, then either (a)
approve build as scoped, or (b) adjust the decision. Once 2.1 is built, 2.2 (frozen
snapshot) and 2.3 (conflict-resolution policy) follow — both are framed by this doc
(§6). No deploy was run (doc-only); if 2.1 build is approved and merged later, Glenn
deploys via `deploy-backend.sh` (no migration, so plain rebuild).

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked (gitignored, left for Glenn): `docs/research/EPIC-2.1-CANONICAL-STORE-DESIGN.md`
  (this session's deliverable), `.sisyphus/handoffs/exit-audit-2026-07-09-epic21-design.md`
  (this audit).
- Deleted files: none.

## END
