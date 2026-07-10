# W4 — Memory, RAG & Marketplace Subsystem Analysis

**Date:** 2026-07-07
**Worker:** 4 of 4 (parallel analysis)
**Scope read:** personal_memory_service, personal_memory_extractor, episodic_memory_service, memory_digest_service, memory_correction_service, memory_extraction_pause_service, memory_citation_service, chat_context._inject_memory_context, rag_service + rag/ subpackage, marketplace_service + nexus/marketplace_db, plus wiring in chat_service / tool_router / episodic_memory_worker.
**Constraint:** analysis only — no code edits, deploys, or commits.

---

## 1. Memory tiers and privacy guarantees

Flowmanner has a genuinely multi-tier, privacy-aware memory subsystem. It is far deeper than "chat with memory." Six tiers exist:

**Tier A — Personal memory (`PersonalMemoryClaim`, `personal_memory_service.py`)**
The atomic unit: a `(subject, predicate, object)` triple plus `claim_type` ∈ {fact, preference, observation, sensitive}, `scope` ∈ {personal, workspace, program, private}, `sensitivity` ∈ {normal, sensitive, restricted}, plus `confidence`, `importance`, `source_type`, `expires_at` (TTL) and `deleted_at` (soft delete).
- Every read is hard-scoped to `(user_id, workspace_id)` together; the API makes it structurally impossible to build a read that omits the workspace filter. Cross-tenant reads return 404 (not 403) to avoid leaking existence.
- Soft-deleted and expired rows are invisible to all read paths by default (no opt-in flag for expiry).
- Taxonomy columns are immutable via PATCH; reclassifying a claim's kind/scope requires recreating it (provenance protection).

**Tier B — Extraction (`personal_memory_extractor.py`)**
LLM extractor (default `deepseek-v4-flash`, ~$0.001/run) turns a conversation/mission/feedback chunk into candidate claims, with a deterministic `RegexPersonalMemoryExtractor` fallback for outages. The regex fallback deliberately tier-gates: PII (email/phone/card) → `sensitive`/`private`; identity → `fact`/`personal`; project facts → `fact`/`workspace`; preferences/imperatives → `preference`/`personal`. The extractor persists nothing — the caller dedupes and persists. **Wired into runtime:** `chat_service.py` (lines ~927–959) runs per-conversation pause-check then extraction with a 5s timeout on every turn.

**Tier C — Episodic memory (`episodic_memory_service.py`)**
Sparse per-mission episode traces stored in Postgres + Qdrant (`episodes` collection, all-MiniLM-L6-v2 / 384-dim). `record_episode()` redacts at **write time** (API keys, `/home/...` & `/Users/...` paths, env secrets, long LLM outputs). `retrieve_relevant()` is hybrid BM25 (Postgres tsvector) + vector (Qdrant), reciprocal-rank-fused, capped at 5, scoped by `(workspace_id, user_id)`. **Wired into runtime:** `episodic_memory_worker.py` records episodes; `tool_router.py` (~line 444) retrieves episodes during agent runs.

**Tier D — Digest (`memory_digest_service.py`)**
`build_preview()` composes a "what I learned about you" preview from recent personal claims — pure DB read + aggregation, **no LLM, no mutation**. It defensively excludes `private`-scope claims and honors soft-delete/expiry. `record_delivery()` logs delivery attempts. Hard-capped at 100 claims; default 7-day lookback.

**Tier E — Correction / privacy audit trail (`memory_correction_service.py`)**
Append-only `memory_correction_events` table recording correction/forget/view/edit events per claim. Scoped to `(user_id, workspace_id)`; `get_provenance()` returns per-claim event history with zero-count buckets so the UI is stable. **CRITICAL GAP:** this service is the audit, but it is NOT yet wired to `PersonalMemoryService._safe_audit` (which is still a no-op `_NoOpAudit`). So today the privacy audit trail is writeable-but-not-yet-invoked — provenance rows exist structurally but are not generated on create/forget/recall.

**Tier F — Pause (`memory_extraction_pause_service.py`)**
Per-conversation extraction pause, TTL-bounded 60s–7d (no "pause forever"). `is_paused()` is a cheap LIMIT-1 check consulted by the extractor before each run; `resume_conversation()` hard-deletes active pauses. Privacy posture: "short TTL only, opt-in, never silent permanent."

**Tier G — Citation (`memory_citation_service.py` + `chat_context._inject_memory_context`)**
`recall_for_chat()` does substring recall + a **defensive exclusion** of `sensitivity ∈ {sensitive, restricted}` and `scope == private` (the stop-rule mitigation for "sensitive memory shown in chat"). Top-5, confidence floor 0.7. `format_memory_block()` builds a system-message block (LLM never sees the citation chip label — decoupled from the `c-<8hex>` short-UUID the frontend renders from SSE `memory_recall_used` / `memory_citation` events). `_inject_memory_context` inserts the block at index 1 (right after the system prompt) pre-LLM. **Wired into runtime:** `chat_service.py` (~lines 1677–1684) recalls then injects every turn.

**Privacy guarantees that actually hold today:** workspace-isolation on every read (enforced at the query layer, not just the model); soft-delete + TTL expiry invisible by default; chat-side exclusion of sensitive/restricted + private claims; write-time redaction of episodes; pause TTL; 404-not-403 isolation.
**Privacy gaps to close before Marketing can lean on "private by design":** (1) the correction/audit trail is not yet invoked — `PersonalMemoryService._safe_audit` is a no-op; (2) personal-memory recall is substring-only (T19) — semantic/embedding recall (T20+) is not in `recall_for_chat`, so recall quality is weak and can miss relevant claims or surface noisy ones; (3) `private`-scope claims are excluded from digest/chat but still exist in the DB with no separate encryption or access tier beyond the scope filter.

## 2. RAG retrieval shape (Qdrant)

There are **two parallel RAG code paths** that do not share a collection scheme — this is the most important architectural nuance for the roadmap.

**Path 1 — `rag_service.RAGService` (legacy/single-collection).**
- One collection from `settings.QDRANT_COLLECTION_NAME` (a single shared collection, no user scoping in the service itself).
- `query_documents()` does `client.search(collection, query_text=..., score_threshold=settings.RAG_SIMILARITY_THRESHOLD)` — i.e. it relies on Qdrant's built-in `query_text` hybrid (text→embedding internally). Returns `{id, text, score, source, metadata}`.
- `get_context()` concatenates top-N docs into a `[Document N] (Source: …)` block for injection into missions/agents.
- Consumed by `substrate/node_executor.py` (RAG_QUERY node) and `task_executor.py` (RAG task type). **No per-user filter** — whatever is in that single collection is searchable.

**Path 2 — `rag/` subpackage (per-user collections, the real "chat with your docs").**
- `vector_store.QdrantVectorStore` uses **per-user collections**: `f"{settings.RAG_COLLECTION_PREFIX}{user_id}"`, created on demand with COSINE distance and `settings.EMBEDDING_DIMENSION`.
- `upsert_chunks()` indexes chunks with payload `{book_title, text, topics, relevance_score, chunk_index, total_chunks, created_at}`.
- Ingestion entry point: `api/v1/rag.py POST /ingest` → chunking → embedding → `vector_store.upsert_chunks(user_id)`. Also `tools/differentiators.py` ingests.
- Retrieval: `rag/retrieval_service.py` + `rag/prompt_synthesizer.py` build prompts; `api/v1/rag.py POST /context/search` uses `RAGService(collection_name=prefix+user.id)` against the per-user collection.
- So per-user isolation IS present in Path 2 (collection name = user id), but **Path 1's `RAGService` ignores it** and queries a shared collection.

**How it feeds missions/chat:**
- Missions: RAG_QUERY / RAG task types → `RAGService.query_documents` → context block injected into the task prompt (Path 1).
- Chat: `api/v1/rag` `/context/search` (+ the prompt synthesizer) feeds a user's own document collection into a generated system prompt (Path 2).
- Episodic memory (Tier C) is a *separate* Qdrant collection (`episodes`) with its own worker + BM25 fusion — not part of the document RAG path.

**RAG maturity assessment:** The plumbing works, but it is fragmented. The "backbone of chat-with-your-docs" (per the foundation brief) is actually Path 2 (per-user), while `rag_service.py` (the module the brief cites) is Path 1 (shared, no user scoping) and is the one `substrate`/mission execution calls. There is no unified retrieval service bridging the two; embedding dimension, collection naming, and metadata schema differ by path. For the front door, RAG is real but should be presented as "bring your own docs, per-workspace isolated" — and the Path-1 shared-collection gap must be closed before any cross-user/marketplace doc surface is exposed.

## 3. Marketplace maturity gap

**The marketing claim ("seed-only hardcoded listings, not user-generated") is only half true, and the nuance matters for the roadmap.**

- `backend/app/services/marketplace_service.py` with `_SEED_LISTINGS` is the **legacy seed module**: 10 hardcoded template records (Lead Enrichment, Cold Email, Chat-with-Docs RAG, Invoice Extraction, Social Cross-Post, Email Triage, Abandoned Cart, Slack Hub, Employee Onboarding, AI Sales Call Analyzer). `seed_marketplace_listings()` idempotently inserts them under a synthetic system user; it is called from `lifespan._seed_marketplace()` at startup. This is exactly the "seed-only" layer the brief describes — and it is thin: name/description/integrations/tags only, `price=0`, no real installable artifact.

- **BUT the live v2 API does NOT use that module.** `api/v2/marketplace.py` routes to `nexus/marketplace_db.py` (`MarketplaceDB`), which has **full user-generated CRUD**: `list_tool()`, `list_capability()`, `install()`, `get_by_author()`, `get_user_installations()`, `update_listing()`, `delete_listing()`, `rate()` + reviews. `install()` actually registers the item into the user's in-process `CapabilityRegistry` (wires `tool.execute` / original capability handler) and bumps `install_count`. `uninstall` is a 501 stub (acknowledged not-yet-implemented). So the backend CAN already accept user-published listings and installs — the model (`MarketplaceListingModel`) carries `author_id`, `pricing_model`, `price`, `verified`, `featured`, `average_rating`, `install_count`, `status`, `requirements`.

**What "expose marketplace on the front door" really requires (vs just showcasing seeds):**

1. **Decide which module is canonical.** The front door must not read `_SEED_LISTINGS` (legacy) while the API writes `nexus/marketplace_db`. Pick one source of truth; the seed module should seed `MarketplaceListingModel` (it currently writes a *different* shape) or be retired.
2. **Catalog depth.** Seed listings are marketing copy with no executable payload. Real marketplace needs: importable workflow/agent definitions (blueprint/run or mission-template), versioning, `requirements` resolution, and a working `uninstall` (currently 501).
3. **Trust & safety surfaces.** `verified` / `featured` flags exist but nothing sets them — there is no moderation, no publisher identity/verification, no abuse reporting, no takedown path. Exposing user-generated listings publicly without these is a liability.
4. **Discovery & monetization.** `pricing_model`/`price` exist but there is no checkout, entitlement, or license enforcement; `install_count`/`average_rating` only become meaningful with real traffic.
5. **Public (unauthenticated) read path.** Today every marketplace endpoint requires `get_current_user`. The front door needs a public, cached, read-only listing surface (featured/recent/category) that does NOT require auth and does NOT leak author PII.
6. **Multi-tenant isolation for installs** — `install()` registers into a global in-process registry keyed by `user:{user_id}:…`; for a multi-tenant deployment this needs workspace scoping and persistence beyond process memory.

**Bottom line:** Showcasing seeds is already possible with zero backend work (the 10 records exist). Making the marketplace *real* (user-published, installable, trustworthy, publicly browsable) is a multi-week build touching catalog model, moderation, public read API, install/uninstall lifecycle, and monetization — not a "flip the switch" task.

## 4. What is safe to surface on the front door NOW vs what needs building first

**Safe to surface NOW (real, wired, privacy-respecting):**
- **Memory engine as a feature claim**, backed by the live runtime: personal memory extraction + recall + citation is active in `chat_service.py` every turn; the defensive exclusion of sensitive/restricted + private claims is in force; per-conversation pause (TTL) exists; workspace isolation is enforced at the query layer. A "your AI remembers you — and you control it" message is honest. The Memory Inspector (claims list, digest preview, pause toggle, correction history) can be featured because the services behind it are real and scoped.
- **Episodic "learns from past runs"** claim — `episodic_memory_worker` records + `tool_router` retrieves with write-time redaction; safe to feature.
- **"Bring your own docs / RAG"** — Path 2 (per-user Qdrant collections) is isolated and works; safe to feature as a per-workspace capability.
- **Marketplace *showcase*** — the 10 seed listings render fine as a static "template gallery" on the front door (read-only, no auth, no install promises).

**Needs building first (do NOT put on the front door until done):**
- **"Private by design / full audit trail"** — must first wire `MemoryCorrectionService` into `PersonalMemoryService._safe_audit` (currently no-op) so the correction/forget/view audit actually records. Until then the audit-trail claim is unbacked.
- **Semantic memory recall** — `recall_for_chat` is substring-only; upgrade to embedding recall (T20+) before claiming "understands you deeply," or recall will feel shallow.
- **RAG cross-user / marketplace-docs surface** — must close the Path-1 shared-collection gap (no user scoping in `rag_service.py`) before any non-per-user doc retrieval is exposed.
- **Live marketplace (user-published, installable, browsable without login)** — requires the 6 items in §3: canonical module, catalog depth + working uninstall, moderation/verification, public read API, monetization, workspace-scoped install persistence. The seeds can be shown; the *interactive* marketplace cannot be honestly launched yet.
- **Install from front door** — `uninstall` is 501 and `install` writes to an in-process registry; do not advertise one-click install publicly until lifecycle + persistence + multi-tenant isolation exist.

**Through-line:** The memory and episodic tiers are genuinely shippable and can anchor the front-door narrative today (memory control UI is real). RAG is shippable as a per-user feature but architecturally split. The marketplace is the one true gap: seeds are showable, but a real, user-generated, installable, public marketplace is the largest remaining build and should be scoped as a Phase-2+ epic, not implied as live on the landing page.
