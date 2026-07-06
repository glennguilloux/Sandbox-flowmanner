# Task: Phase 4 — i18n + Polish

**Status:** DRAFT
**Priority:** P2 — polish and security hardening
**Estimated effort:** 1 session
**Created:** 2026-07-06
**Audited:** 2026-07-06
**Source:** `docs/STUB-COMPLETION-PLAN-2026-07-06.md` §Phase 4
**Depends on:** Phase 1.2 (i18n keys baseline)

---

## Problem

Three polish items:

1. **Homepage `services.*` section untranslated** — 63 keys missing from DE, ES, JA locales. The homepage consulting section renders empty for non-EN/FR users.
2. **14 unreachable routes** — routes with real content but no nav entry need triage.
3. **Twilio HMAC verification** — security vulnerability: webhook verification checks header presence only, not validity.

---

## Ground Truth Verification

| Claim | Verified? | Notes |
|-------|-----------|-------|
| EN has 63 `services` keys | ✅ Yes | `len(en["services"]) = 63` |
| FR has 63 `services` keys | ✅ Yes | `len(fr["services"]) = 63` |
| DE/ES/JA have 0 | ✅ Yes | `"services" in de/es/ja = False` |
| Twilio checks header only | ✅ Yes | `_verify_twilio` returns `bool(sig)` — presence check only |
| 14 unreachable routes | ✅ Yes | See nav-config.ts verification below |

**Nav verification:** None of `analytics`, `circuit-breaker`, `critiques`, `feedback`, `files`, `triggers` appear in `nav-config.ts` (verified via grep). These routes exist in the `(dashboard)` route group but have no nav entries.

---

## Acceptance Criteria

- [ ] `services.*` section translated for DE, ES, JA (63 keys each)
- [ ] i18n verification script shows 0 missing keys
- [ ] Twilio HMAC-SHA1 verification implemented with `hmac.compare_digest()`
- [ ] Unreachable routes documented with decisions (add to nav / link from parent / leave as programmatic-only)

---

## Sub-tasks

### 4.1 — Translate `services.*` for DE / ES / JA

**Current:** The homepage (`src/app/[locale]/page-client.tsx:74`) uses `useTranslations("services")`. EN and FR have 63 keys. DE/ES/JA have 0.

**Keys structure** (from en.json):
```json
"services": {
  "metaTitle": "Services — FlowManner",
  "metaDescription": "...",
  "heroEyebrow": "...",
  "heroTitle1": "...",
  // ... 63 keys total covering:
  // - hero section (eyebrow, title, body, CTAs)
  // - howItWorks section (title, 3 steps with title/body)
  // - services grid (12 services with title/desc)
  // - useCases (3 use cases with title/desc/items)
  // - consulting section (title, points, CTA)
  // - integrations section
  // - pricing stats (3 stats with value/label/sub)
  // - footer CTA
  // - SEO metadata
}
```

**Steps:**

1. Read the `services` section from `src/i18n/locales/en.json` (and `fr.json` for reference translations)
2. For each of `de.json`, `es.json`, `ja.json`:
   - Add a `services` top-level key
   - Translate all 63 values into the target language
   - Preserve the key names exactly
   - Use machine translation with human review for quality
3. Run the i18n gate — all locales should show 0 missing

**Translation priority (per convention):** FR is primary locale. DE/ES/JA are secondary. When in doubt, match FR conventions.

**Commit:** `i18n: translate services.* section for DE, ES, JA (63 keys each)`

---

### 4.2 — Review unreachable routes

14 routes exist with real content but no nav entry. For each, decide:

| Route | `(dashboard)` path | Decision guidance |
|-------|-------------------|-------------------|
| `/analytics` | `(dashboard)/analytics/` | User-facing analytics dashboard — candidate for nav |
| `/circuit-breaker` | `(dashboard)/circuit-breaker/` | Internal reliability — programmatic only |
| `/critiques` | `(dashboard)/critiques/` | AI criticism/improvement — link from programs page |
| `/feedback` | `(dashboard)/feedback/` | User feedback — link from footer or settings |
| `/files` | `(dashboard)/files/` | File management — candidate for nav |
| `/triggers` | `(dashboard)/triggers/` | Event triggers — link from automations |
| `/developer` | `(dashboard)/developer/` | API docs — link from footer |
| `/mission-dashboard` | Does NOT exist as separate route | Check if this is just `/missions` or if there's a real route |
| `/topology` | Does NOT exist as `(dashboard)/topology/` | Check `/tools/topology` or if this is orphaned |

**Approach:**
1. Read each route's `page.tsx` to understand its purpose
2. Check git blame/commit messages for context
3. Document decision in a table in the commit message:
   ```
   /analytics          → add to nav (user-facing)
   /circuit-breaker    → programmatic-only (internal reliability)
   /critiques          → link from programs page
   /feedback           → link from footer
   /files              → add to nav
   /triggers           → link from automations
   /developer          → link from footer
   /mission-dashboard  → TBD (verify existence)
   /topology           → TBD (verify existence)
   ```

**Note:** Some of these (like `/mission-dashboard` and `/topology`) may reference routes from earlier iterations that no longer exist. Verify before documenting.

**Commit:** `docs: triage unreachable routes (decisions documented)`

---

### 4.3 — Twilio HMAC verification (SECURITY)

**Current:** `backend/app/api/v1/integration_webhooks.py:151-162` — `_verify_twilio` checks header presence only:
```python
def _verify_twilio(body: bytes, headers: dict[str, str], secret: str | None) -> bool:
    if not secret:
        return True
    sig = headers.get("x-twilio-signature", "")
    return bool(sig)  # ← SECURITY: presence check only, no cryptographic verification
```

**Twilio's signature scheme:**
1. Take the **full request URL** (including protocol, host, path, and query params)
2. Sort all **POST form parameters** alphabetically by key
3. Concatenate: `url + sorted_params_string`
4. HMAC-SHA1 with the auth token as key
5. Base64-encode the result
6. Compare with `X-Twilio-Signature` header using `hmac.compare_digest()`

**Steps:**

1. **Read the current call site** — find where `_verify_twilio` is called to understand what arguments are available (the request URL needs to be passed through):
   ```bash
   grep -n "_verify_twilio" backend/app/api/v1/integration_webhooks.py
   ```

2. **Update the function signature** to accept the request URL:
   ```python
   def _verify_twilio(
       body: bytes,
       headers: dict[str, str],
       secret: str | None,
       request_url: str,  # ← NEW: passed by caller
   ) -> bool:
   ```

3. **Implement full HMAC-SHA1:**
   ```python
   import base64
   import hashlib
   import hmac
   from urllib.parse import parse_qs

   def _verify_twilio(
       body: bytes,
       headers: dict[str, str],
       secret: str | None,
       request_url: str,
   ) -> bool:
       """Twilio: HMAC-SHA1 of the URL + sorted form params."""
       if not secret:
           return True  # Verification disabled (dev/test only)

       sig = headers.get("x-twilio-signature", "")
       if not sig:
           return False

       # Parse the form-encoded body and sort params alphabetically
       body_str = body.decode("utf-8")
       params = parse_qs(body_str)
       # Flatten: each key appears once with its first value
       flat_params = {k: v[0] for k, v in params.items()}
       sorted_params = "".join(
           f"{k}{v}" for k, v in sorted(flat_params.items())
       )

       # Build the signed string: URL + sorted params
       signed_string = request_url + sorted_params

       # HMAC-SHA1 with the Twilio auth token
       expected = base64.b64encode(
           hmac.new(
               secret.encode("utf-8"),
               signed_string.encode("utf-8"),
               hashlib.sha1,
           ).digest()
       ).decode("utf-8")

       # Timing-safe comparison
       return hmac.compare_digest(expected, sig)
   ```

4. **Update all call sites** to pass `request_url`. Find them with:
   ```bash
   grep -rn "_verify_twilio" backend/app/api/v1/integration_webhooks.py
   ```

5. **Add a unit test** (if one doesn't exist):
   ```python
   # Test with known Twilio signature payload
   # Expected: valid signature → True, wrong signature → False
   ```

**Verify:**
```bash
docker compose exec backend pytest app/tests/ -k "webhook" -v
# Test manually with a known Twilio webhook payload
```

**Commit:** `fix: implement full Twilio HMAC-SHA1 webhook verification (security)`

---

## Verification Gate

```bash
# Frontend
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit
npx vitest run

# i18n
python3 -c "
import json
en = json.load(open('/home/glenn/FlowmannerV2-frontend/src/i18n/locales/en.json'))
def keys(x,p=''):
    r=set()
    for k,v in x.items():
        f=f'{p}.{k}' if p else k
        r.update(keys(v,f) if isinstance(v,dict) else {f})
    return r
en_keys = keys(en)
for lang in ['fr','de','es','ja']:
    d = json.load(open(f'/home/glenn/FlowmannerV2-frontend/src/i18n/locales/{lang}.json'))
    miss = en_keys - keys(d)
    print(f'{lang}: {len(miss)} missing')
"

# Backend
cd /opt/flowmanner
docker compose exec backend pytest app/tests/ -q --tb=no 2>&1 | tail -5
```

---

## File Map

| File | Action |
|------|--------|
| `src/i18n/locales/de.json` | Add 63 `services.*` keys |
| `src/i18n/locales/es.json` | Add 63 `services.*` keys |
| `src/i18n/locales/ja.json` | Add 63 `services.*` keys |
| `backend/app/api/v1/integration_webhooks.py` | Implement Twilio HMAC verification (lines 151-162) |
| Various route `page.tsx` files under `(dashboard)/` | Review for nav inclusion |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Machine-translated services keys may read awkwardly | Review translations for naturalness; prefer FR as reference for Romance languages (ES) |
| Twilio HMAC may break existing webhook integrations if URL format differs | Test with a real Twilio webhook payload before deploying; Twilio's test console provides known-valid signatures |
| Unreachable routes may be intentional deep links | Check git blame and commit messages for context before adding to nav |
| `/mission-dashboard` and `/topology` may not exist | Verify before documenting; mark as "non-existent, remove route" if confirmed |
