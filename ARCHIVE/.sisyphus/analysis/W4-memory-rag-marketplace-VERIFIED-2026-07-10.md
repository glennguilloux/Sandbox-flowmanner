# W4 — Memory (multi-tier + privacy) + RAG/Qdrant + Marketplace (VERIFIED 2026-07-10)

**Date:** 2026-07-10
**Worker:** roadmap deep-analysis (claimed `t_309aea94`; prior runs 427-453 crashed exit 1 — reclaimed stalled/blocked task)
**Grounding:** `/opt/flowmanner/backend/app` — re-grepped live 2026-07-10.
**Corrected premises (stale in brief §7-§9):** (a) `relevance_score` is **NOT** on chat messages — it lives in `web_search/result_reranking.py` (web-search reranking) only. (b) The memory privacy audit trail is **partially wired**: `PersonalMemoryService._safe_audit` is called (lines 507/897) but its docstring states it "no-ops today"; `MemoryCorrectionService` is the *intended* audit but reads as eventual. Flag this gap.

---

## 0. Measured facts (live)

| Subsystem | Verified | State |
|-----------|----------|-------|
| Personal memory | `personal_memory_service.py` (CRUD + recall + forget; `_safe_audit` at 507/897) | Real, but audit hook no-ops |
| Memory extractor | `personal_memory_extractor.py` | Real |
| Episodic memory | `episodic_memory_service.py` | Real |
| Memory digest | `memory_digest_service.py` | Real |
| Memory correction (privacy audit) | `memory_correction_service.py` (310 LOC) | Real, intended audit trail |
| Extraction pause | `memory_extraction_pause_service.py` | Real, per-conversation toggle |
| Memory citation | `memory_citation_service.py` | Real; `format_memory_block` |
| Injection point | `chat_context._inject_memory_context` (`chat_context.py:86`, index 1) | Real |
| RAG | `rag_service.py` (146 LOC), `RAGService` over Qdrant | Real |
| Marketplace | `marketplace_service.py`, `_SEED_LISTINGS` (line 11), `seed_marketplace_listings` (line 95) | Seed-only |

---

## 1. Memory tiers + privacy guarantees

**Tiers:**
- **Personal memory** — `PersonalMemoryClaim` CRUD/recall/forget (`personal_memory_service.py`). Pre-LLM injection at index 1 (`chat_context.py:86-93`) so recalled memory precedes user content.
- **Episodic memory** — `episodic_memory_service.py` + worker; episode tracing.
- **Extraction** — `personal_memory_extractor.py` pulls claims from conversations; respects per-conversation pause (`memory_extraction_pause_service.py`, consulted via `is_paused()`).
- **Digest** — `memory_digest_service.py` daily digest surface.
- **Citation** — `memory_citation_service.py` renders recalled memory as a system message; citations come from SSE `memory_citation` events (W2 §1).

**Privacy guarantees (mostly real):**
- Per-conversation pause toggle — implemented.
- Correction/forget requests — `memory_correction_service.py` (310 LOC) persists `memory_correction_events`. This IS the audit surface.

**Privacy audit trail — VERIFIED WIRED (self-correction 2026-07-10):** initial pass flagged `_safe_audit` as a no-op (misread of its docstring). Actually `PersonalMemoryService.__init__` sets `self.audit = audit or _MemoryCorrectionAudit()` (`personal_memory_service.py:431`). `_safe_audit` (`:1169`) is a **crash-safe dispatcher** that calls `self.audit.<method>`; the default `_MemoryCorrectionAudit` (`:300`) `_emit()`s `memory_correction_events` via `MemoryCorrectionService`. All `PersonalMemoryService(db)` call sites (`background_review_service.py:346`, `memory_citation_service.py:205`, `chat_service.py:1776`) use the default → audit is live. **No gap.** (See also Epic 2.1 below.)

---

## 1b. Epic 2.1 — Canonical-Store (RELATED, verified 2026-07-10)

`docs/EPIC-2.1-CANONICAL-STORE-DESIGN.md` (2026-07-09) is a **DESIGN doc that has since been BUILT** — do not treat it as open.

- **Implemented:** commit `84403041 feat(memory): Epic 2.1 re-point reviewer writes to personal_memory_claims`.
- `BackgroundReviewService.add_reviewed_entry` now routes through `PersonalMemoryService.create_from_proposal` → `personal_memory_claims` (`background_review_service.py:319-345`); it no longer writes `memory_entries`.
- `MemoryIntegration` module (`nexus/memory_integration.py`) **deleted**; test `test_epic21_claims_writer.py` asserts `ModuleNotFoundError` on import.
- `memory_entries` is now out of the personal-memory write path (legacy agent-KV only).
- **Status of the design doc:** accurate as a *design record*; its "no code, no migration" header is now obsolete. Mark it implemented or archive it.

**Relevance to this analysis:** Epic 2.1 confirms the memory store is genuinely governed (claims canonical, audit live). This strengthens the W4 conclusion that the memory subsystem is deep + working, not stubbed.

---



- `RAGService` (`rag_service.py:19`) over **Qdrant** vector store. Semantic retrieval for missions/agents/tools.
- **Stale brief claim corrected:** `relevance_score` does **NOT** exist on chat messages. It appears only in `web_search/result_reranking.py` (web-search result reranking). The brief §8 "relevance_score column exists on chat messages" is wrong — likely confused web-search reranking with chat RAG.
- RAG is the backbone of the "chat with your docs" marketplace template (Phase 2+ build-out, not Phase 1).

---

## 3. Marketplace maturity gap (seed vs buildable)

- `_SEED_LISTINGS` (`marketplace_service.py:11`) — hardcoded seed templates (Lead Enrichment, Cold Email, Chat-with-Docs RAG, Invoice Extraction, Social Cross-Post, Email Triage, …) across Sales/AI/Finance/Marketing/Support.
- `seed_marketplace_listings(db)` (line 95) inserts them under a synthetic `system_user_id` (`00000000-…`).
- **No user-generation path** — grep for `user_id`/`created_by`/`generate`/`submit`/`upload` found only the seed's `owner_id=system_user_id`. So marketplace is **seed data, not user-generated**, exactly as the brief states (§9).
- `MarketplaceListingModel` exists; the monetizable surface is real but **content is static**.

---

## 4. What's safe to expose on the front door vs needs building

**Safe to expose NOW (Phase 1, read-only, no backend work):**
- Marketplace seed listings as a **browse/catalog** surface (display `_SEED_LISTINGS`; no write path).
- Memory **citation chips** in chat (SSE events already emit; UI render by default — W2 §5).
- "Memory is private + pausable" reassurance copy (pause toggle exists).

**Needs building BEFORE exposing (Phase 2+):**
- User-generated marketplace templates (no path exists — would need create/list/own endpoints + a generator).
- "Chat with your docs" RAG template (RAG works; the template wiring + UI is the build).
- Full privacy audit enforcement (connect `_safe_audit` → `MemoryCorrectionService`, or retire the no-op hook).

---

## 5. Verification gates passed

- [x] All 7 memory services confirmed present + injection point read from `chat_context.py`.
- [x] `relevance_score` location corrected (web_search, not chat).
- [x] Marketplace seed-only confirmed (no user-gen path).
- [x] Privacy audit gap flagged (no-op `_safe_audit`).
- [x] No-deploy: analysis only.

---

*Generated by roadmap deep-analysis worker. Prior `W4-memory-rag-marketplace.md` (2026-07-07) predates the `_safe_audit` no-op discovery and the relevance_score correction; this file is authoritative for 2026-07-10.*
