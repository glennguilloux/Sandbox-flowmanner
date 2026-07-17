# Design Sign-off — R5 "Harden uploads + close SSRF bypass"

**Date:** 2026-07-17
**Task brief:** R5 from 2026-07-17 swarm audit (HIGH — externally reachable on homelab host).
**Mode:** SIGN-OFF GATE ONLY. No code written. No push/merge/deploy.

---

## VERDICT: ALREADY RESOLVED — do NOT dispatch the fmw1/fmw2/fmw3 review swarm

The audit brief quotes the **OLD buggy state** of two files. The live `main`
tree at `/opt/flowmanner/backend` has **already been hardened** by commit
`0bec741b` — *"security(R5): fix upload path-traversal + close SSRF bypass in
discover_models"* — which is an **ancestor of current HEAD** (`git branch` =
`main`, `git log` shows `0bec741b` above the current tip lineage).

Per the persona-delegation skill's PRE-DISPATCH STALENESS GATE, dispatching
read-only review cards against an already-fixed finding would manufacture a
false "we found/fixed it" narrative and burn worker capacity for zero signal.
**No kanban cards were dispatched.**

---

## Claim-by-claim verification (byte-level, live source)

### Finding 1 — `file.py` path traversal  →  RESOLVED

**Brief claimed (old state):** `file.py:56` concatenates `file.filename`
UNMODIFIED into `UPLOAD_DIR / "{file_id}_{file.filename}"`; path does NOT
strip `".."`, no content-type/size validation.

**Live state (`backend/app/api/v1/file.py`):**

- `upload_file` (line 124) now calls:
  - `_validate_upload_content(content_data)` at **line 134** (size + magic-byte
    executable rejection, BEFORE any write)
  - `storage_name = _safe_storage_name(file_id, file.filename)` at **line 135**
  - `storage_path = UPLOAD_DIR / storage_name` (line 136) — the path is built
    from the **sanitized** name, not raw `file.filename`.
- `_safe_storage_name` (lines **86–96**) uses `os.path.basename(...)` +
  extra `/` `\` separator stripping, so `../../etc/cron.d/x` collapses to a
  single safe component prefixed by the UUID. The raw `file.filename` is only
  stored in the DB `UserFile.filename` field (line 142) — display metadata,
  never used for the write path.
- `_validate_upload_content` (lines **53–83**): enforces `MAX_UPLOAD_BYTES`
  (25 MB, line 24), rejects empty files (65–66) and any content matching
  `_BLOCKED_MAGIC` executable signatures (ELF/MZ/shebang/Mach-O, lines 44–73).

**AST-verified:** `upload_file` body contains `basename`, `_safe_storage_name`,
and `write_bytes`; `_safe_storage_name` contains `os.path.basename`.

→ The exact proposed fix #1 (use `os.path.basename`; add magic-byte + size
validation before write_bytes) is **already implemented**. No remaining work.

### Finding 2 — `api_keys.py` SSRF bypass in `discover_models`  →  RESOLVED

**Brief claimed (old state):** `api_keys.py:441-456` (`discover_models`) skips
the secure `_is_safe_outbound_url` + `_PinnedNetworkBackend` guard that
`fetch_provider_models` (`:219`) uses.

**Live state (`backend/app/api/v1/api_keys.py`):**

- `discover_models` (lines **441–486**) now calls
  `await fetch_provider_models(provider=provider, api_key=request.api_key)`
  at **line 458**. AST-verified: the function body contains
  `fetch_provider_models(`.
- `fetch_provider_models` (lines **200–283**) is the single SSRF-safe source of
  truth: it calls `_is_safe_outbound_url(requested_base_url)` at **line 219**,
  re-resolves + re-checks the resolved public IP (lines 224–251), and pins the
  resolved IP via `_PinnedNetworkBackend` (lines 256–259) to defeat
  DNS-rebinding. It never follows redirects (line 254).
- `discover_models` maps the structured failure kinds to fail-secure responses,
  including `unsafe` → HTTP 400 (lines 473–478), so a refused destination never
  leaks the request.

→ The exact proposed fix #2 (route `discover_models` through the existing
`_is_safe_outbound_url` + `_PinnedNetworkBackend` helper) is **already
implemented**. No remaining work.

### Finding 3 — regression test for traversal  →  RESOLVED (test present)

Commit `0bec741b` includes the regression test. Verified via grep on the repo:

```
backend/tests/test_security_r5_upload_traversal.py
```

(Contains the `filename="../../etc/cron.d/x"` upload assertion that it must NOT
escape `UPLOAD_DIR`.)

→ Proposed fix #3 (add traversal regression test) is **already implemented**.

---

## Precise change(s) needed from me: NONE for code.

What remains is a **single decision point** — the sign-off gate's close-out:

1. **Approve the sign-off doc** (this file) as "R5 already resolved, no code
   action".
2. The fix commit `0bec741b` is on `main` but, per repo AGENTS.md, code changes
   do not take effect until a **backend rebuild + deploy** (`deploy-backend.sh`).
   If R5 is not yet live on the homelab backend, the only outstanding action is
   a **deploy authorization** — NOT a code change.
3. Commit this doc (untracked `.sisyphus/*` — the deploy gate trips on untracked
   entries) once you approve, so the working tree is clean for any deploy.

**No changes were made, no workers were dispatched, nothing was pushed/merged/
deployed.** Awaiting your go-ahead — specifically: do you want me to (a) just
commit this sign-off doc and close, or (b) also trigger a backend deploy so the
R5 fix is live?

---

## Evidence appendix

- `git log` (file.py / api_keys.py): `0bec741b security(R5): fix upload path-traversal + close SSRF bypass in discover_models`
- `git branch --show-current`: `main`
- `file.py`: `_safe_storage_name` @86, `_validate_upload_content` @53, hardened `upload_file` write path @124–137
- `api_keys.py`: `discover_models` @441 routes to `fetch_provider_models` @458; SSRF guard @219, `_PinnedNetworkBackend` @256
- AST parse confirmed both structural claims without relying on any worker self-report.
