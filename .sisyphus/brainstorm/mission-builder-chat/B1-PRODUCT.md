# B1 — Mission Builder × Chat: PRODUCT posture

**Author:** Alex (PM persona) · **Status:** Brainstorm / read-only · **Date:** 2026-07-19
**Recommendation confidence:** ~70% (no usage analytics available; grounded in code + owner signal)

---

## 1. User journey today

A user can build a mission and run it — but that run dies inside the Builder. `handleRun` calls `startRun(savedId, {})` and then `startPolling` to animate the canvas locally (`FlowEditor.tsx:1347-1351`). Nothing about that run is ever handed to Chat. The Chat page has **zero** mission awareness: `chat/page-client.tsx` imports threads, branches, and steps only — no mission, run, or agent-spawn concept exists (`page-client.tsx:1-105`).

The single "bridge" is a canvas tile, and it is a dead-end in practice:
- The `mission_status` tile is only creatable **manually** from the Chat "Add tile" dropdown (`Canvas.tsx:226`).
- That dropdown creates the tile with an **empty payload**, so `MissionStatusTile` immediately renders `"No missionId in tile payload."` (`MissionStatusTile.tsx:49,55-58`). The one integration point is non-functional for a normal user.
- Even when fed an ID, it is read-only polling of `/api/v2/missions/{id}/status` every 5s (`MissionStatusTile.tsx:64,78`) — a progress bar, not an interaction.

**Net gap:** building and running lives in the Builder; conversing lives in Chat; the two share no object, no navigation, and no live handoff. A mission a user just designed cannot be talked to, and a chat cannot reach into a mission.

## 2. Core question — Builder FEEDS Chat

Take a position: **the Builder should FEED Chat** (a saved mission becomes a runnable, reusable agent that a user talks to), *not* Chat driving the Builder.

Why: Chat-drives-Builder (natural language spawns graphs) is a much larger bet with weak evidence and a brittle failure mode — a misgenerated 11-node-type graph (`nodes/*.tsx`) is worse than no graph. Builder-feeds-Chat reuses what already exists (`startRun`, run polling, the tile) and matches the owner's felt pain: the disconnect *after* building. A "third hub" is premature; we have no data justifying a new surface. Ship the feed direction first, keep chat-authoring as a *Later* bet.

## 3. Target user & jobs-to-be-done

There are two jobs, likely the **same person at different moments**, not two personas:
- **Builder-moment:** "I want to compose/verify a repeatable multi-step workflow" (power user, deliberate, visual).
- **Operator-moment:** "I want to *use* that workflow on a real input and steer/observe it conversationally" (fast, low-ceremony).

**Minimum lovable flow:** In the Builder, click **Run** → a Chat thread opens automatically, pre-wired to that run, showing live status *and* an input box that talks to the running/finished mission. One click, Builder → Chat, no manual tile, no copy-pasted ID.

## 4. Proposed product shape (ranked)

1. **"Run in Chat" handoff (highest value / lowest cost).** `handleRun` (`FlowEditor.tsx:1333`) creates a chat thread seeded with the run and auto-inserts a *populated* `mission_status` tile (fixes the empty-payload bug at `Canvas.tsx:226`). Outcome: the user never loses their run. Surface: shared (Builder trigger + Chat thread/canvas).
2. **Mission → reusable chat agent.** A saved mission is selectable as an agent in the Chat launcher, so users re-run designed workflows on new inputs without reopening the graph. Outcome: missions become durable, conversational tools. Surface: Chat (launcher/thread) + a thin mission-list read.
3. **Two-way status → control.** Upgrade the tile from read-only polling to actionable — approve/abort/retry from Chat (backend already exposes abort/retry per `FlowEditor.tsx:1381` TODO note). Outcome: Chat becomes mission control. Surface: Chat tile + existing run endpoints.

*Explicit no for now:* chat-authors-the-graph. Defer until move #1 proves users want the two surfaces linked at all.

## 5. What "done" looks like

The relationship is done when a user who finishes a mission in the Builder lands, with one click, in a Chat thread that shows that exact run live and lets them act on it — and can later re-invoke that mission as a named agent from Chat without touching the canvas. The Builder is where you *compose*; Chat is where you *operate and converse*; a single shared run object connects them with no manual ID plumbing.

---

**Recommendation:** Ship move #1 first — wire `FlowEditor.handleRun` to open a Chat thread with a correctly-populated `mission_status` tile — turning the currently-broken manual bridge (`Canvas.tsx:226`, `MissionStatusTile.tsx:55`) into a one-click Builder→Chat handoff.
