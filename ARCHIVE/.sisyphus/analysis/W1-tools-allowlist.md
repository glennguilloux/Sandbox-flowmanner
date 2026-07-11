# W1 — Tools Allowlist & 3-Gate Mechanics (Deep Analysis)

**Date:** 2026-07-07
**Worker:** W1 (tools/allowlist analysis)
**Grounding:** `/opt/flowmanner/backend` (real path: `/opt/flowmanner/backend`) — verified against live code, not the brief's assertions.
**Foundation brief:** `.sisyphus/analysis/PLATFORM-FOUNDATION-BRIEF-2026-07-07.md` (read, facts accepted, NOT re-litigated).

---

## 0. Scope verification (measured, not assumed)

- **115 tool handler files** in `backend/app/tools/*.py` (excl. `__init__`) — confirmed by `ls *.py | wc -l` = 115.
- **22 files carry a real `visibility=` tool tag** (see Gate-1 enumeration below). `linkedin_publisher.py`'s `visibility="hidden"` was verified to be a genuine `ToolMetadata` tag (line 88), not the LinkedIn post-visibility field.
- **93 files are untagged** → fall back to `"hidden"` (confirmed: 115 − 22 = 93).
- Tag tally matches the brief exactly: **8 `default_on` / 11 `opt_in` / 3 `hidden`**.

| Tag | Count | Files |
|-----|-------|-------|
| `default_on` | 8 | `browser_navigate`, `browser_sandbox`, `sandboxd_exec`, `sandboxd_file_list`, `sandboxd_file_read`, `sandboxd_file_write`, `sandboxd_preview`, `sandboxd_serve` |
| `opt_in` | 11 | `arxiv_paper_finder`, `crypto_market_data`, `dall_e_image_gen`, `deep_web_crawler`, `fact_check_validator`, `global_news_aggregator`, `google_search_api`, `html_to_markdown`, `ocr_text_extractor`, `pdf_parser`, `wikipedia_fetcher` |
| `hidden` | 3 | `gmail_sender`, `google_workspace_hub`, `linkedin_publisher` |
| untagged | 93 | all remaining handler files |

---

## 1. How the 3 gates intersect

The exposed chat tool set = **visibility (curation) ∩ workspace allowlist ∩ required_scopes (security)**. Gate 1 & 2 run at *schema-build* time (`_get_chat_openai_tools`); Gate 3 runs at *execution* time (`_execute_tool_call`). This split is deliberate: the LLM is shown the schema for everything that passes Gates 1–2, but the security check is deferred to the moment of actual invocation.

### Gate 1 — Visibility (curation) — `chat_service.py:1476-1484`

```python
# chat_service.py:1476
exposed: list = []
for tool in registry.list_all():
    vis = getattr(tool.metadata, "visibility", "hidden") or "hidden"   # :1478
    if vis == "hidden":
        continue                                                      # :1479-1480
    # Gate 1b: sandboxd tools require feature flag
    if tool.tool_id in _SANDBOXD_IDS and not settings.SANDBOXD_ENABLED:
        continue                                                      # :1482-1483
    exposed.append(tool)
```

- `registry` = `get_tool_registry()` — the in-memory `ToolRegistry`, a hydrated projection of the `tools_catalog` Postgres table (`tool_catalog_models.py:Tool`).
- Untagged → `getattr(..., "hidden")` returns the field default `"hidden"` (see §2). `or "hidden"` also converts empty/None to hidden.
- **Feature-flag sub-gate (1b):** 7 sandboxd tools (`sandboxd_preview/exec/file_write/file_read/file_list/serve` + `browser_sandbox`) are additionally gated behind `settings.SANDBOXD_ENABLED`. They can be tagged `default_on` but never surface unless the flag is on. This makes the `default_on` tag *necessary but not sufficient* for those tools — a subtlety worth noting in the roadmap.

### Gate 2 — Workspace allowlist — `chat_service.py:1486-1492`

```python
# chat_service.py:1486
if db is not None and workspace_id:
    from app.models.workspace_models import get_workspace_tool_allowlist

    workspace_allowed = await get_workspace_tool_allowlist(db, workspace_id)   # :1490
    if workspace_allowed is not None:
        exposed = [t for t in exposed if t.tool_id in workspace_allowed]       # :1492
```

- `get_workspace_tool_allowlist` (`workspace_models.py:271`) returns `None` when **no allowlist rows exist → all tools permitted** (the default state). Returns a `set[str]` of tool names only when the workspace has explicit, *active* (`is_active=True`) entries.
- Redis-cached: `_ALLOWLIST_CACHE_TTL = 300` (5 min), key `ws_allowlist:{workspace_id}`; cache invalidated on PUT `/tools` via `invalidate_workspace_tool_allowlist_cache` (`workspace_models.py:258`).
- This is an **intersection** (not a union): a tool passing Gate 1 is dropped if absent from the workspace set. NULL allowlist = passthrough.

### Gate 3 — Scope (security boundary) — `chat_service.py:1535-1565` (`_execute_tool_call`)

```python
# chat_service.py:1535
if tool.metadata.required_scopes and user_id is not None:
    from app.core.auth_constants import ADMIN_ROLES
    if _user_role and _user_role in ADMIN_ROLES:
        pass  # full access (admin/owner bypass)                  # :1539-1540
    elif _user_scopes is not None:
        missing = [s for s in tool.metadata.required_scopes if s not in _user_scopes]  # :1542
        if missing:
            return json.dumps({"error": f"capability denied: ... (missing: {missing})"})  # :1550-1555
    else:
        # No cached scopes available — deny as defense-in-depth    # :1556-1565
        return json.dumps({"error": f"capability denied: tool '{tool_name}' requires scopes ..."})
```

**Intersection summary:** A tool reaches the LLM **only if** (a) `visibility != "hidden"` AND (b) passes the sandboxd flag AND (c) is in the workspace allowlist (or allowlist is NULL). It then **executes only if** (d) either it declares no `required_scopes`, or the caller holds every required scope (admin/owner bypass), or — critically — `_user_scopes` is populated; if a tool needs scopes but no scopes were resolved, it is **denied** (fail-closed).

### ⚠️ Findings on the boundaries (not in the brief)

1. **`ToolMetadata.visibility` default is `"hidden"`** (`base.py:79-82`), *not* `"opt_in"`. The inline code comment at `chat_service.py:1473-1475` is **wrong** ("Default for untagged tools is `opt_in` (the `ToolMetadata` field default)…"). The *behavior* is correct (fall back to hidden), but the comment misstates the source of truth. Minor doc bug, but it's exactly the kind of misleading comment that could cause a future maintainer to "fix" the default to `opt_in` — which is the rejected change (see §2).
2. **`Tool.visibility` DB column default is `"public"`** (`tool_catalog_models.py:44`) — inconsistent with the in-memory `ToolMetadata` default (`"hidden"`) and with the code's hangup on `"hidden"`. The DB `enabled` default is `True`. So a freshly-seeded DB row says `"public"` while the registry treats absence as `"hidden"`. The registry is what actually gates chat; the DB column is currently inert for chat exposure. Worth reconciling in the roadmap (single source of truth).
3. **Gate-3 asymmetry:** "Tools with no `required_scopes` are unrestricted" (per `_execute_tool_call` docstring + the `if tool.metadata.required_scopes and ...` guard). This means **any newly-tagged `opt_in` tool with empty scopes is callable by any non-admin user.** For read-only tools this is acceptable, but it must be paired with a deliberate scope-decision, not left blank by accident. The roadmap's "tag 10–20 read tools" batch should assign explicit (even permissive) scopes or consciously accept the unrestricted state.

---

## 2. Why 93 untagged tools → `hidden` is FAIL-CLOSED BY DESIGN (not a bug)

The fallback is explicit and intentional:

```python
vis = getattr(tool.metadata, "visibility", "hidden") or "hidden"   # chat_service.py:1478
if vis == "hidden":
    continue
```

Three independent signals confirm this is a deliberate fail-safe, **not** an oversight:

1. **The field default in `base.py:80` is `"hidden"`** — the schema author chose the conservative default at the model level, before any per-tool override.
2. **The brief itself states it** (§1): *"93 tools are untagged → fall back to `hidden` … It is intentional fail-safe, not a bug. … Do NOT flip default to opt_in (Opus's call — agreed)."*
3. **The danger of the alternative is concrete.** Flipping the default to `opt_in` would expose, on the very next deploy, **every untagged tool whose author simply never got to it** — including write/mutating tools among the 93: `aws_s3_uploader`, `shell_cmd_executor`, `gmail_sender` (already correctly hidden), `stripe_operations`, `salesforce_lead_creator`, `twilio_sms_sender`, `telegram_bot`, `slack_communicator`, `git_repo_manager` (commit/push), `vercel_deployer`, `shopify_inventory_sync`, `sendgrid_campaign`, `github_actions_trigger`, `instagram_media_publisher`, `ghost_medium_publisher`, `x_twitter_scheduler`, `nodejs_sandbox`, `python_sandbox`, `terminal`/`terminal.py`. A forgotten write-tool becoming silently reachable in chat = a **security incident**, not a UX nit. Fail-closed protects exactly the case where someone adds a powerful handler and forgets to think about exposure.

> **EXPLICIT STATEMENT (per task requirement):** Flipping the untagged default from `hidden` to `opt_in` is **REJECTED**. A forgotten write-tool would become silently reachable in the chat surface = security incident. The correct path is *explicit per-tool curation* (tag the ones we want), which is what Gate 1 is designed for.

---

## 3. Proposed next batch: 10–20 high-value READ-ONLY tools to tag `opt_in`

Selection criteria: (a) read-only / fetch / search / list / analyze semantics, (b) demonstrably increases chat capability (web data, structured extraction, analysis), (c) **excludes** any tool with write/mutating side-effects (those stay `hidden` pending a scope + intent review). Each candidate below is currently **untagged** (in the 93) and would gain `visibility="opt_in"`.

| # | File | tool_id | Why it earns `opt_in` |
|---|------|---------|----------------------|
| 1 | `graphql_fetcher.py` | `graphql_fetcher` | Query any GraphQL endpoint — broad read access to APIs. |
| 2 | `smart_web_scraper.py` | `smart_web_scraper` | General-purpose page fetch/extract — directly makes chat "browse the web." |
| 3 | `sitemap_crawler.py` | `sitemap_crawler` | Discover + read site structure/URLs. |
| 4 | `xpath_node_extractor.py` | `xpath_node_extractor` | Extract text/attrs from HTML/XML by XPath — structured read. |
| 5 | `css_selector_query.py` | `css_selector_query` | Extract structured data via CSS selectors. |
| 6 | `infiniscroll_extractor.py` | `infiniscroll_extractor` | Read infinite-scroll pages (dynamic content). |
| 7 | `table_to_csv_extractor.py` | `table_to_csv_extractor` | Pull HTML tables → CSV (read + structure). |
| 8 | `chart_data_extractor.py` | `chart_data_extractor` | Reverse-engineer data from chart images (read/analyze). |
| 9 | `image_exif_extractor.py` | `image_exif_extractor` | Read EXIF/metadata from images (read-only). |
| 10 | `stock_price_tracker.py` | `stock_price_tracker` | Alpha Vantage quote/history lookup (read). |
| 11 | `keyword_density_analyzer.py` | `keyword_density_analyzer` | TF-IDF / keyword analysis (read/analyze). |
| 12 | `seo_content_scorer.py` | `seo_content_scorer` | Score HTML against focus keywords (read/analyze). |
| 13 | `visual_diff_checker.py` | `visual_diff_checker` | Compare two images for changes (read-only). |
| 14 | `google_analytics_reporter.py` | `google_analytics_reporter` | Read GA reports (read, with auth). |
| 15 | `integration.py` | `list_integrations` | List-type: surfaces connected integrations to chat. |
| 16 | `browser_snapshot.py` | `browser_snapshot` | Read DOM/accessibility snapshot — complements `default_on` `browser_navigate`/`browser_sandbox`. |
| 17 | `browser_screenshot.py` | `browser_screenshot` | Read visual state of a page (read-only browser op). |
| 18 | `memory_summarization.py` | `memory_summarization` | Summarize stored memory (read/analyze). |
| 19 | `viral_trend_analyzer.py` | `viral_trend_analyzer` | Analyze trend data (read/analyze). |
| 20 | `schema_inference_engine.py` | `schema_inference_engine` | Infer schema from sample data (read/analyze). |

**Explicitly NOT proposed (stay `hidden`):** `aws_s3_uploader`, `shell_cmd_executor`, `stripe_operations`, `salesforce_lead_creator`, `twilio_sms_sender`, `telegram_bot`, `slack_communicator`, `git_repo_manager`, `vercel_deployer`, `shopify_inventory_sync`, `sendgrid_campaign`, `github_actions_trigger`, `instagram_media_publisher`, `ghost_medium_publisher`, `x_twitter_scheduler`, `nodejs_sandbox`, `python_sandbox`, `terminal`/`terminal.py`, `postgresql_client`, `mongodb_connector`, `pinecone_manager` (upsert), `notion_sync`, `github_manager` (mixed write ops). These need a separate write-tool exposure track with explicit `required_scopes` + HITL before any `opt_in`/visible tag.

**Caveat to carry into the roadmap:** per Finding 3 (§1), each of these 20 should be tagged `opt_in` *and* receive a conscious scope decision. Read-only web/analysis tools can reasonably ship with empty/permissive scopes, but that choice must be made explicitly, not inherited.

---

## 4. `docs/DUAL-WRITE-DECISION.md` — BLOCKER STATUS: RESOLVED (premise is stale)

**The task assumed this file should NOT exist ("the one BLOCKED architectural decision"). It DOES exist, and the decision is EXECUTED.**

- **Path:** `/opt/flowmanner/docs/DUAL-WRITE-DECISION.md` (real: `/opt/flowmanner/docs/DUAL-WRITE-DECISION.md`).
- **Content:** "Dual-Write Decision — Executed", dated 2026-07-04, **Status: ✅ EXECUTED — 2026-07-07**. Documents that the dual-write layer was fully removed; Mission is canonical, Blueprint+Run retained as a read model. Lists completed work: `dual_write` calls removed from `_mission_cqrs/commands.py`, `DualWriteService` deleted, backfill/prove/renumber scripts deleted (2026-07-07).
- **Contradiction with the foundation brief:** Brief §13 lists *"Dual-write: BLOCKED on `docs/DUAL-WRITE-DECISION.md` (still the only genuinely open item)."* The brief is **stale on this point** — the decision was made and executed on 2026-07-07, the same day the brief was written. The file the brief pointed to as the "blocker" is precisely the artifact that records the decision being done.

**Reported blocker:** There is **no longer a blocker**. The one open architectural decision the brief flagged has been resolved and documented. The roadmap should treat dual-write as CLOSED, not pending. If anything, the only residual item is the deferred *lazy population path for Blueprint+Run* (marked ⏳ in the decision file), which is a non-blocking v2 concern.

---

## 5. One-paragraph summary

The Flowmanner tool system gates chat-exposed tools through three intersecting checks: **(1) visibility** (curation) in `_get_chat_openai_tools` (`chat_service.py:1478`), where any tool with `visibility="hidden"` — including all 93 untagged handlers, whose field default is `"hidden"` at `base.py:80` — is dropped from the schema; **(2) the workspace allowlist** (`chat_service.py:1490-1492`, Redis-cached 5 min, NULL = passthrough); and **(3) `required_scopes`** (the real security boundary) enforced at execution in `_execute_tool_call` (`chat_service.py:1535-1565`), where missing scopes or unresolvable scopes → capability denied (fail-closed). The 93-untagged→hidden fallback is **fail-closed by design**, not a bug, and flipping the default to `opt_in` is **explicitly REJECTED** because it would silently expose forgotten write-tools (e.g. `shell_cmd_executor`, `stripe_operations`) as a security incident. I propose tagging **20 high-value READ-ONLY tools** `opt_in` (web fetch/extract: `graphql_fetcher`, `smart_web_scraper`, `sitemap_crawler`, `xpath_node_extractor`, `css_selector_query`, `infiniscroll_extractor`, `table_to_csv_extractor`, `chart_data_extractor`; analysis: `image_exif_extractor`, `stock_price_tracker`, `keyword_density_analyzer`, `seo_content_scorer`, `visual_diff_checker`, `viral_trend_analyzer`, `schema_inference_engine`, `memory_summarization`; list/read: `google_analytics_reporter`, `list_integrations`, `browser_snapshot`, `browser_screenshot`) — explicitly excluding all mutating tools. Finally, the expected blocker `docs/DUAL-WRITE-DECISION.md` **does exist and records an EXECUTED decision (2026-07-07)**, so the brief's "blocked" claim is stale; dual-write is **CLOSED**, not open. Three minor consistency findings were also surfaced (misleading code comment at `chat_service.py:1473-1475`; DB `Tool.visibility` default `"public"` vs in-memory `"hidden"`; Gate-3 "no scopes = unrestricted" requiring conscious scope assignment for the new batch).
