# TASK-BE-STUB-07 — Audit 30+ Integration Tools for Real API Implementation

## Current State
30+ tool files in `/opt/flowmanner/backend/app/tools/` check `is_placeholder()` for API keys but have no visible HTTP API call code:
- `salesforce_lead_creator.py`, `shopify_inventory_sync.py`, `stripe_operations.py`, `aws_s3_uploader.py`, `stock_price_tracker.py`, `telegram_bot.py`, `sendgrid_campaign.py`, `twilio_sms_sender.py`, `gmail_sender.py`, `hubspot_crm_link.py`, `linkedin_publisher.py`, `instagram_media_publisher.py`, `x_twitter_scheduler.py`, `global_news_aggregator.py`, `expense_receipt_parser.py`, `fact_check_validator.py`, `google_search_api.py`

Pattern in all of these:
```python
from app.tools.base import BaseTool, ..., register_tool, is_placeholder
if is_placeholder(SOME_API_KEY):
    return ToolResult.error_result(error="Replace placeholder value...")
# No actual HTTP request / API call follows
```

## Problem
- **HIGH**: All external integration tools are only placeholder-key validators. Even with valid credentials, they make no API calls.
- Agents discover these tools, call them, and get either "replace placeholder" errors or silent no-ops.

## Exact Files
- **Audit (read only):** All files listed above in `/opt/flowmanner/backend/app/tools/`
- **Reference:** `/opt/flowmanner/backend/app/tools/base.py` (`is_placeholder`, `BaseTool`)

## Exact Implementation Steps
1. **Phase 1: Audit** — For each tool file:
   - Open the file and search for any HTTP client usage (`httpx`, `aiohttp`, `requests`, `urllib`).
   - If an HTTP call exists: mark as IMPLEMENTED, document the API endpoint.
   - If no HTTP call exists: mark as STUB.
2. **Phase 2: Categorize** — Group results:
   - **REAL**: Tool has real API call code (keep).
   - **STUB-HIGH**: Tool is critical for platform value (implement next).
   - **STUB-LOW**: Tool is nice-to-have (defer).
   - **DEAD**: Tool has no clear use case (remove from registry).
3. **Phase 3: Implement** — For STUB-HIGH tools:
   - Add real HTTP API calls using `httpx.AsyncClient`.
   - Use `aiohttp` timeout handling (30s max per call).
   - Add proper error handling: network errors, auth errors, rate limits.
4. **Phase 4: Cleanup** — For STUB-LOW/DEAD:
   - Remove `register_tool()` call at module bottom (or comment out).
   - Add a docstring comment explaining deferred status.

## Constraints
- Must not break any existing tool that actually works.
- Must use `httpx.AsyncClient` for consistency with the rest of the codebase.
- Must handle API rate limiting gracefully (429 responses).

## Verification
```bash
cd /opt/flowmanner/backend
# List all tool files that import is_placeholder
grep -l "is_placeholder" app/tools/*.py | wc -l
# For each, check if it has an HTTP call
for f in $(grep -l "is_placeholder" app/tools/*.py); do
  if grep -q "httpx\|aiohttp\|requests\.\|urllib" "$f"; then
    echo "IMPLEMENTED: $f"
  else
    echo "STUB: $f"
  fi
done
```
