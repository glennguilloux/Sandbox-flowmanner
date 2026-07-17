# R5 — Upload path-traversal fix + close SSRF bypass (HIGH)

**Context:** Swarm audit REPORT.md §3 H1 + M1 (Security Engineer).
- `backend/app/api/v1/file.py:56` concatenates `file.filename` unmodified into
  `UPLOAD_DIR / f"{file_id}_{file.filename}"` — `Path` does not strip `..`, so a
  crafted filename writes outside `UPLOAD_DIR`. No content-type/size validation.
- `backend/app/api/v1/api_keys.py:441-456` `discover_models` skips the secure
  `_is_safe_outbound_url` + `_PinnedNetworkBackend` guard that `fetch_provider_models`
  (`:219`) uses — SSRF/credential-exfil risk on BYOK model discovery.

**Your task:**
1. `file.py:56`: replace raw `file.filename` with `os.path.basename(file.filename)`
   (UUID-only storage is already there via `file_id`), and add magic-byte / size
   validation before `write_bytes`.
2. `api_keys.py`: route `discover_models` (`:441-456`) through the existing
   `_is_safe_outbound_url` + `_PinnedNetworkBackend` helper so the SSRF guard can't
   be bypassed by a sibling endpoint.
3. Add a test: a `filename="../../etc/cron.d/x"` upload must NOT escape `UPLOAD_DIR`.

**Constraints:** Security hardening, surgical. No other refactors. Commit to this
branch. Do NOT push, deploy, or merge. Stop and await review when done.
