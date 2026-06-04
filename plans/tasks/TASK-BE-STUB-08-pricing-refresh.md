# TASK-BE-STUB-08 — Implement Pricing Table Refresh (BudgetEnforcer)

## Current State
`/opt/flowmanner/backend/app/services/budget_enforcer.py:101`:
```python
def refresh(self) -> None:
    """Refresh pricing from upstream sources (placeholder).
    In production, this would fetch pricing from provider APIs.
    """
    self._last_refresh = time.monotonic()
    logger.debug("Pricing table refreshed")
```
Only updates the timestamp — never fetches real pricing data.

## Problem
- **CRITICAL**: If upstream LLM providers change their pricing, cost tracking becomes inaccurate.
- Budget enforcement (Invariant I.14) uses stale prices to reject/approve LLM calls.
- The `stale` property correctly identifies outdated pricing but there's no source to refresh from.

## Exact Files
- **Modify:** `/opt/flowmanner/backend/app/services/budget_enforcer.py` (lines 97-103)
- **Reference:** `/opt/flowmanner/backend/app/services/budget_enforcer.py` (DEFAULT_PRICING dict, lines 40-62)

## Exact Implementation Steps
1. Create a pricing configuration file at `/opt/flowmanner/backend/app/config/pricing.json`:
   ```json
   {
     "version": "1",
     "updated_at": "2026-06-01",
     "models": {
       "deepseek-chat": {"input": 0.14, "output": 0.28, "provider": "deepseek"},
       "claude-3-5-sonnet": {"input": 3.00, "output": 15.00, "provider": "anthropic"},
       "gpt-4o": {"input": 5.00, "output": 15.00, "provider": "openai"}
     }
   }
   ```
2. Implement `refresh()` to read from this config file:
   ```python
   def refresh(self) -> None:
       import json
       from pathlib import Path
       config_path = Path(__file__).parent.parent / "config" / "pricing.json"
       try:
           with open(config_path) as f:
               data = json.load(f)
           self._pricing = {**DEFAULT_PRICING, **data.get("models", {})}
           self._last_refresh = time.monotonic()
           logger.info("Pricing refreshed: %d models", len(self._pricing))
       except Exception as e:
           logger.warning("Failed to refresh pricing: %s", e)
   ```
3. Alternatively: implement HTTP fetch from provider pricing endpoints:
   - OpenAI: `GET https://api.openai.com/v1/models` (pricing not in API — use config)
   - Anthropic: No pricing API — use config file
   - DeepSeek: Config file only
4. Register a background task that calls `refresh()` daily (matches `PRICING_REFRESH_INTERVAL = 86400`).

## Constraints
- Must not make external network calls at startup (slows boot).
- Must fall back to DEFAULT_PRICING if config file is missing.
- Must not change the `estimate()` method signature.

## Verification
```bash
cd /opt/flowmanner/backend
# Test pricing refresh
python -c "
from app.services.budget_enforcer import PricingTable
pt = PricingTable()
print('Before refresh:', pt._pricing.get('deepseek-chat'))
pt.refresh()
print('After refresh:', pt._pricing.get('deepseek-chat'))
print('Stale:', pt.stale)
"
```
