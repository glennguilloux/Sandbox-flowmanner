# Brief for Claude Opus — Flowmanner "looks so bad, mechanism is broken" (2026-07-07)

**Purpose:** Drive an Opus browser session about why the live product feels broken
(design + mechanism). Opus CANNOT log into flowmanner.com, so this brief is the
evidence + questions to paste into the Opus chat, with the screenshot attached.

**Attach this screenshot:** `/home/glenn/.hermes/cache/screenshots/browser_screenshot_c1574dd6e5fe4f83a602739c8616746d.png`
(landing page at https://flowmanner.com/en — shows the nav bug + generic services)

---

## 0. WHAT'S ACTUALLY TRUE TODAY (verify before trusting any older doc)

An earlier Opus round (July 2026) and a Hermes critique flagged these as broken.
**Most are now FIXED by the deployed chat-wiring sprint (2026-07-07). Do not re-litigate them:**

- ❌ ~~"Triple state orchestration (ToolEventContext + ChatStore + SSE) causes flicker"~~
  → FIXED. `page-client.tsx:14-15` comment: "Now uses ChatStore directly as single
  source of truth (no more ToolEventContext sync)." ToolEventContext was collapsed into ChatStore.
- ❌ ~~"Hardcoded tool allowlist exposes only 13 of 46 tools"~~
  → FIXED. `chat_service.py:1471-1481` now computes the exposed set as the intersection
  of 3 gates: **visibility** (per-tool `ToolMetadata.visibility`) × **workspace allowlist**
  × **scope gate** (`required_scopes` in `_execute_tool_call`). The hardcoded set is gone.
- ❌ ~~"chat_service.py is 1,400 lines, decompose it"~~
  → Partially done. 3 leaf modules extracted (`llm_providers.py`, `chat_context.py`,
  `sse_protocol.py`); `fresh_session()` wrapper consolidated 4 fresh-session patterns;
  `BackgroundTaskManager` holds refs on fire-and-forget tasks. Monolith still ~2,300 lines
  but the worst debt is addressed.

**THE REAL CURRENT STATE (verified 2026-07-07 against live code):**

- Backend has **115 tool files** in `backend/app/tools/`.
- Only **22 are tagged** with `visibility=` in their `ToolMetadata`:
  - `default_on` = 8, `opt_in` = 11, `hidden` = 3  → **19 tools reachable in chat**
  - The other **93 tools are UNTAGGED and default to `hidden`** (safety fallback at
    `chat_service.py:1478`: `vis = getattr(tool.metadata, "visibility", "hidden") or "hidden"`).
- So the "wire, don't build" thesis still holds — but the remaining gap is **tagging 93
  tools**, not rewriting the allowlist (done). Most of Flowmanner's arsenal is invisible
  by default.

---

## 1. THE UPFRONT "LOOKS SO BAD" SIGNALS (what a visitor sees first)

These are reproducible on the live site right now:

**a) Production nav leaks a debug/drag element.**
The main menu renders a top-level `<menuitem>` "Drag to reorder Chat" containing a
"Drag to reorder" button + "Chat" link. This is a drag-handle/debug affordance that
should never be in the shipped nav. Evidence from the live DOM snapshot:
```
menubar "Main menu"
  menuitem "Drag to reorder Chat"        ← leaked debug element
    button "Drag to reorder"
    link "Chat"
  menuitem "Menu"
  menuitem "Products" / "Resources" / "More"
```
(See attached screenshot — top-left, the faint overlapping "Chat / Menu / Products" text
is this element rendering badly.)

**b) Branding is inconsistent.**
- Landing page `<title>`: `"AI Workflow Consulting — FlowManner — FlowManner"`
  (double "FlowManner", and "AI Workflow Consulting" branding)
- `/chat` sign-in page `<title>`: `"FlowManner — AI Mission Platform"`
- These two don't agree on what the product even is (consulting? mission platform?).

**c) Landing page is generic / low-density.**
The vision pass on the screenshot called it "professional," but the "How it works" and
"Services" sections are near-empty (3 emoji-bullet services with "From €X · 15 minutes").
It reads like a template, not a product that has 115 backend tools and a full chat platform.

---

## 2. QUESTIONS FOR OPUS (paste these into the Opus chat)

> Context: Flowmanner is a self-hosted AI platform (FastAPI backend + Next.js frontend).
> The backend has 115 tool implementations and a full chat/mission/canvas system, but the
> live product feels broken and amateur. I've attached a screenshot of the landing page.
> The critique of your earlier plan is mostly stale (the allowlist + state-orchestration
> issues are fixed). I need you to focus on what's actually wrong NOW.

**Q1 — Triage the "looks so bad" front-end signals.**
Given (a) the leaked "Drag to reorder Chat" debug element in the production nav,
(b) the inconsistent branding ("AI Workflow Consulting" vs "AI Mission Platform" vs
double "FlowManner"), and (c) the thin landing page — rank these by how much they hurt
perceived quality, and give the cheapest concrete fix for each (file-level, not vague).
Which is a one-line CSS/conditional fix vs which needs a real component decision?

**Q2 — The 93-invisible-tools gap.**
115 tools exist; 93 are untagged and default to `hidden`, so only 19 are reachable in chat.
The fix is "tag the 93." But tagging 93 tools is a survey that could eat a session.
What's the right strategy: (a) tag all 93 with category+visibility in one sweep,
(b) tag only the high-value next batch and leave the long tail `hidden`, or
(c) flip the default so untagged = `opt_in` (exposed unless explicitly hidden) and only
tag the dangerous write-tools as `hidden`? Which minimizes risk (a write-tool leaking
into chat is a security incident) while maximizing reachable capability?

**Q3 — Is the product over-engineered or under-built?**
The chat layout is a 3-column (ThreadSidebar | Canvas+InstrumentPanel+QuickStatsBar |
ChatRightSidebar) with zen mode, MatrixRain/TopographicBackground, LaunchPad. The
landing page is thin but the internals are huge. Is the right move to (a) strip the
decorative/complex UI to a focused two-pane, (b) keep it but fix the leaks, or
(c) invest in making the landing page + nav reflect the actual depth? Argue from the
visitor's first-30-seconds experience.

**Q4 — Where should the next agent spend effort for max perceived-quality gain?**
Given the wiring is mostly done, propose the top 3 concrete changes (each ≤ half a day)
that would make a visitor say "this is real" instead of "this looks broken." Be specific
about files/components if you can infer them; otherwise name the subsystem.

**Q5 — The stale-critique trap.**
Your earlier plan assumed chat_service.py was 1,400 lines with a hardcoded allowlist and
a triple-state frontend. All three are now false. If you were to re-plan the next sprint
from TODAY's state (computed allowlist done, state collapsed to ChatStore, 93 tools hidden),
what does the revised Phase 1 look like? Don't repeat the old tasks.

---

## 3. DECISIONS OPUS'S ROUND-2 DOC LEFT OPEN (from Opus-chat-architecture-deepdive-round2)
These still need Glenn's call, but they're architecture not "looks bad" — raise only if
Opus asks about the mechanism roadmap:
1. Allowlist migration scope (tag all 117 vs the exposed+Task-1.1 batch)
2. Fire-and-forget tiers (BackgroundTaskManager now vs Celery for memory-extraction sites)
3. SSE keepalive + Nginx `proxy_buffering off` (VPS change — Glenn does it)
4. Strategy-viability UX (auto-route to frontier vs prompt-to-switch)
5. Dual-write: read `docs/DUAL-WRITE-DECISION.md` before deciding
6. Virtualization: amend Task 2.3 to "memoize markdown + remove render cap" (already partly done)
