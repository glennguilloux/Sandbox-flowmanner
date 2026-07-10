# FlowManner Agent Handoff System

**Created:** 2026-06-11
**Purpose:** Give every future agent enough grounded context to work across FlowManner backend, frontend, infra, and product features without re-reading the whole repo or inventing assumptions.

This folder is the durable handoff layer for serious FlowManner work. It sits beside the existing large reference docs, but is intentionally shorter, status-driven, and updateable.

## What this system contains

| Path | Use |
|---|---|
| `INDEX.md` | Entry point for the next agent. Start here. |
| `DEEP-DIVE-PLAYBOOK.md` | How to perform a grounded deep-dive before changing code. |
| `TOPIC-DOSSIER-TEMPLATE.md` | Standard format for backend/domain/infrastructure topic dossiers. |
| `FEATURE-DEEP-DIVE-TEMPLATE.md` | Standard format for product feature deep-dives spanning frontend/backend. |
| `SESSION-HANDOFF-TEMPLATE.md` | Compact end-of-session handoff for unfinished work. |
| `ACTIVE-WORK.md` | Current deep-dive backlog and status board. |
| `topics/README.md` | Catalog of topic dossiers. |
| `topics/00-system-map.md` | Fast orientation map across machines, APIs, execution engines, data, and docs. |
| `topics/_TEMPLATE.md` | Minimal per-topic dossier shell. |

## How to use before serious backend work

1. Re-read `AGENTS.md` and the relevant machine-specific agent file.
2. Run `git status --short && git branch --show-current && git rev-parse --short HEAD`.
3. Open `INDEX.md` and pick the topic or feature you are about to touch.
4. Read the matching topic dossier from `topics/`.
5. If no dossier exists, copy `topics/_TEMPLATE.md` to `topics/<number>-<area>.md` and fill it from live source, not from memory.
6. Use `DEEP-DIVE-PLAYBOOK.md` for the discovery commands and verification gates.
7. Only after the dossier is updated, write code or deploy.

## Status labels

| Label | Meaning |
|---|---|
| `Draft` | Notes exist but have not been verified against current source. |
| `Grounded` | Files/routes/models referenced in the dossier have been checked in the current repo. |
| `Ready` | Dossier is sufficient for another agent to start implementation work. |
| `Archived` | Replaced by a newer dossier or no longer relevant. |

## Canonical upstream docs to keep linked

| Doc | Why it matters |
|---|---|
| `Docs/FLOWMANNER-COMPLETE-SPEC-FOR-GPT.md` | Full system spec for external AI brainstorming. |
| `Docs/FLOWMANNER-CANONICAL-KNOWLEDGE.md` | Canonical concepts, entities, relationships, and design principles. |
| `Docs/FLOWMANNER-ROADMAP.md` | Production-to-V2 roadmap and phase gates. |
| `docs/REBUILD-ROADMAP.md` | Current rebuild state, hard truths, and stop gates. |
| `Docs/ARCHITECTURE-CONTEXT-WINDOW-SURVIVAL-GUIDE.md` | Session-specific architecture audit survival notes. |
| `SESSION-RITUAL.md` | End-of-session exit audit, commit, and push ritual. |

## Rules for future agents

- Do not claim a bug is fixed unless you ran the relevant probe in the current turn and paste the output.
- Do not edit files on the VPS directly. The VPS is a deployment target, not the source of truth.
- Source edits only take effect after rebuild/deploy because Docker images have no code volume mounts.
- Prefer repo docs and live source over stale summaries.
- Keep active handoff docs short. Move completed phase detail into archives when a file gets too large.
- English only.
