# W1 — Tools Allowlist & 3-Gate Mechanics (VERIFIED 2026-07-10)

**Date:** 2026-07-10
**Worker:** roadmap deep-analysis (re-claimed `t_77c90c66` after phantom claim cleared)
**Grounding:** `/opt/flowmanner/backend/app` — every count below re-grepped live on 2026-07-10.
**Corrected premise:** the task body instructed "confirm `docs/DUAL-WRITE-DECISION.md` does NOT exist (blocked decision)." **That is stale.** The doc EXISTS and the decision is **EXECUTED** (dual-write write-path removed 2026-07-07; `commands.py` has zero `dual_write_*` calls; `DualWriteService` deleted). See `docs/DUAL-WRITE-DECISION.md` + the patched `backend/app/api/_mission_cqrs/AGENTS.md`.

---

## 0. CRITICAL STALE-DOC WARNING

Two prior docs are **wrong** on the exact subject of this analysis:

| Doc | Claim (stale) | Verified reality (2026-07-10) |
|-----|---------------|-------------------------------|
| `PLATFORM-FOUNDATION-BRIEF-2026-07-07.md` §1 | `opt_in` = 11, `default_on` = 8, `hidden` = 3 | `opt_in` = **20**, rest confirmed (8 / 3) |
| `.sisyphus/analysis/W1-tools-allowlist.md` (2026-07-07) | lists a specific 11-tool `opt_in` set (arxiv_paper_finder, crypto_market_data, dall_e_image_gen, deep_web_crawler, fact_check_validator, global_news_aggregator, google_search_api, html_to_markdown, ocr_text_extractor, pdf_parser, wikipedia_fetcher) | **That exact set is no longer the opt_in set.** Current opt_in = a *different* 20 tools (browser_screenshot, sitemap_crawler, smart_web_scraper, css_selector_query, graphql_fetcher, …). The brief's 11 are now **untagged → hidden**. |

**Implication:** the tagging work was redone/replaced between 2026-07-07 and 2026-07-10. Any roadmap slice that depends on "which tools are exposed" must use the §1 numbers below, not the brief or the W1 doc.

---

## 1. Measured tool visibility (live, 2026-07-10)

- **115** handler files in `backend/app/tools/*.py` (excl. `__init__`).
- **Tagged = 31**: `default_on` = **8**, `opt_in` = **20**, `hidden` = **3**.
- **Untagged = 84** → fall back to `"hidden"` (fail-safe default at `chat_service.py:2298`).

### `default_on` (8) — always exposed
`browser_navigate`, `browser_sandbox`, `sandboxd_exec`, `sandboxd_file_list`, `sandboxd_file_read`, `sandboxd_file_write`, `sandboxd_preview`, `sandboxd_serve`

### `opt_in` (20) — exposed when available (read-mostly ops)
`browser_screenshot`, `browser_snapshot`, `chart_data_extractor`, `css_selector_query`, `google_analytics_reporter`, `graphql_fetcher`, `image_exif_extractor`, `infiniscroll_extractor`, `integration`, `keyword_density_analyzer`, `memory_summarization`, `schema_inference_engine`, `seo_content_scorer`, `sitemap_crawler`, `smart_web_scraper`, `stock_price_tracker`, `table_to_csv_extractor`, `viral_trend_analyzer`, `visual_diff_checker`, `xpath_node_extractor`

### `hidden` (3) — never in chat
`gmail_sender`, `google_workspace_hub`, `linkedin_publisher`

---

## 2. The 3 gates (verified in `chat_service._get_chat_openai_tools`, line ~2240)

Exposed chat tool set = **Gate 1 ∩ Gate 2**, with **Gate 3 deferred to execution**.

- **Gate 1 — Visibility (curation).** `chat_service.py:2296-2302`: `vis = getattr(tool.metadata, "visibility", "hidden") or "hidden"`; `hidden` → skipped. sandboxd tools additionally gated by `SANDBOXD_ENABLED` flag (1b). **This is curation, not security** (`chat_service.py:2269`).
- **Gate 2 — Workspace allowlist (Redis-cached).** `chat_service.py:2305-2310`: if `workspace_tool_allowlist` is set for the workspace, intersect. NULL allowlist = all permitted. Model: `WorkspaceToolAllowlist` (`models/workspace_models.py:214`).
- **Gate 3 — Scope (security, enforced at execution).** `chat_service.py:2336-2337`: `required_scopes` checked in `_execute_tool_call`. Tools with no `required_scopes` are unrestricted. Missing scopes → `capability denied`; no cached scopes → deny (defense-in-depth).

**Key design note (unchanged from brief):** visibility is curation; `required_scopes` is the security boundary. Adding a tool = tag it in-file via `ToolMetadata.visibility`; **no central allowlist edit**.

---

## 3. Why 84 untagged → hidden is fail-closed by design (NOT a bug)

- `ToolMetadata.visibility` defaults to `"hidden"` (`app/tools/base.py`). Any handler not explicitly tagged is invisible in chat.
- The safety rationale: a new tool ships *invisible* until a human curates it. Writes/default-on exposure requires deliberate tagging. This matches ADR-001 (curation model) and the agreed "never flip default to opt_in" decision.
- Confirmed at `chat_service.py:2298`: untagged → `continue` (skipped). No tool leaks into chat un-reviewed.

---

## 4. Concrete next-tag candidates (read-only, currently invisible)

13 untagged handlers are clearly read-only by name and safe to promote to `opt_in` (exposes reads, keeps writes hidden):

| Tool | Why safe to expose | Current |
|------|-------------------|---------|
| `arxiv_paper_finder` | read research papers | hidden (untagged) |
| `crypto_market_data` | read market prices | hidden (untagged) |
| `fact_check_validator` | read/verify claims | hidden (untagged) |
| `global_news_aggregator` | read news | hidden (untagged) |
| `google_search_api` | read web search | hidden (untagged) |
| `html_to_markdown` | read/convert | hidden (untagged) |
| `ocr_text_extractor` | read image text | hidden (untagged) |
| `pdf_parser` | read PDF text | hidden (untagged) |
| `wikipedia_fetcher` | read wiki | hidden (untagged) |
| `audio_sentiment_analyzer` | read/analyze audio | hidden (untagged) |
| `expense_receipt_parser` | read receipt (note: may write; review first) | hidden (untagged) |
| `differentiators` | read/analyze | hidden (untagged) |
| `stable_diffusion_pipeline` | **generates images — treat as `hidden`, NOT opt_in** | hidden (untagged) |

**Recommendation:** tag the first 11 (all pure reads) `opt_in`. Leave `stable_diffusion_pipeline` hidden (generation, not a read). Review `expense_receipt_parser` for any write side-effect before tagging.

This would bring `opt_in` to ~31 and total tagged to ~42 — still far below "tag all 115," preserving the fail-closed posture for writes.

---

## 5. Dual-write note (corrected premise)

`docs/DUAL-WRITE-DECISION.md` **exists** and records an **EXECUTED** decision: Mission canonical, Blueprint/Run retained as a dormant read model. The task body's instruction to "confirm it does NOT exist" is obsolete — do not act on it. `backend/app/api/_mission_cqrs/AGENTS.md` dual-write references were patched to match (2026-07-10).

---

## 6. Verification gates passed

- [x] Every count re-grepped against `backend/app/tools` (no trust of brief/W1 doc).
- [x] Gate logic read from `chat_service.py` directly.
- [x] No-deploy: analysis only, no code edits to backend (only doc patch + this report).

---

*Generated by roadmap deep-analysis worker. The brief (2026-07-07) and the prior W1 doc (2026-07-07) are STALE on tool tallies — use §1 of this file.*
