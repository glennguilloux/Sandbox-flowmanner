# Handoff — Phase 4: i18n + Polish

**Completed:** 2026-07-06
**Commits:** `ddefb734` (frontend), `33eddc7a` (backend), `6604b7d3` (frontend), `6ca815c3` (backend)
**Deployed:** ✅ Both deployed to VPS

---

## Summary

Phase 4 addressed three polish and security items:

1. **i18n services translations** — Added 63 `services.*` keys to de.json, es.json, ja.json. Covers hero text, service descriptions (Code Review, Competitive Intelligence, Document Q&A), pricing stats, CTA strings, and footer. All locales now have 0 missing keys.

2. **Unreachable routes triage** — Documented decisions for 7 dashboard routes with real content but no nav entry. Two candidates for nav (`/analytics`, `/files`), four for contextual links, one programmatic-only.

3. **Twilio HMAC-SHA1 verification** — Replaced header-presence check with full cryptographic verification in `_verify_twilio`. Computes HMAC-SHA1 of request URL + sorted form params using auth token, base64 encodes, timing-safe comparison via `hmac.compare_digest()`.

## Verification

- All locales: 0 missing keys vs en.json
- Frontend typechecks clean
- Backend lint passes
- Both deploys healthy

## Gotchas for Next Agent

- The `custom_verify` callable type is `Callable[..., bool]` — very loose. Only Twilio uses it currently.
- The unreachable routes need actual nav wiring — the triage only documented decisions.
- The Twilio HMAC fallback (no request_url) silently accepts any non-empty signature — same as before, but not truly secure in that path.
