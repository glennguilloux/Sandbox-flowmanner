# SELF-AUDIT-MED-06 — Encryption legacy hardcoded salt

## Finding
`app/utils/encryption.py:16` defines `_LEGACY_SALT = b"flowmanner-salt-"`, a
static salt used only by the **v1 backward-compat decrypt path**
(`decrypt_api_key`, line 65). A static salt weakens PBKDF2 for any data still
in v1 format (identical plaintexts → identical ciphertext; salt not
per-record). Severity: medium.

## What is still encrypted with the v1 path?
Encryption (`encrypt_api_key`) has used the **v2 per-key random-salt** format
since the change that introduced migration `byok_per_key_salt_001`
(2026-07-04). The v1 path is now **read-only legacy-decrypt only**.

Three stores consume this module:
1. `user_api_keys.encrypted_key` (BYOK) — **already migrated** to v2 by
   `alembic/versions/20260704_byok_per_key_salt.py`.
2. `integrations.auth_config_encrypted` — written via `encrypt_api_key` in
   `app/api/v1/integrations.py` + `app/api/v2/integrations.py`, decrypted in
   `app/services/http_integration_executor.py`. **NOT covered by any
   migration** — rows written before the v2 switch may still be v1.
3. `api_keys` table — `app/api/v1/api_keys.py:567` uses `encrypt_api_key`.
   Same gap as #2.

So `_LEGACY_SALT` cannot be removed until #2 and #3 are also migrated, or
those old rows are already v2.

## What this task changed (safe, non-breaking hardening behind a flag)
- Added `ENCRYPTION_ALLOW_LEGACY_DECRYPT: bool = True` to `app/config.py`
  (default `True` = current behavior, fully backward-compatible).
- Gated the v1 branch in `decrypt_api_key` on the flag. When `False`, the
  weakened static-salt path raises a clear `ValueError` instead of silently
  decrypting v1 data. The salt and derivation are **unchanged** (no break to
  existing v1 decrypt).
- Added `test_legacy_v1_decrypt_disabled_by_flag` in `app/tests/test_byok.py`
  locking the contract: default still decrypts v1; flag-off rejects v1.

**No production data path was altered. v1 decryption is preserved by default.**

## Proposed migration plan (DO NOT apply without review)
The hardened flag is the lever; the full remediation is a one-time data
migration + a config flip:

1. **Add a second data migration** (`alembic/versions`) that re-encrypts
   `integrations.auth_config_encrypted` and the `api_keys` encrypted column
   from v1→v2, mirroring `byok_per_key_salt_001` (per-row random salt, commit
   individually, skip already-`v2:` rows). Provide a downgrade that reverts
   to v1.
2. **Run both migrations** in every environment (prod + dev). After this,
   no rows remain in v1 format.
3. **Flip the flag**: set `ENCRYPTION_ALLOW_LEGACY_DECRYPT=False` once
   dashboards/audit confirm zero v1 rows remain (a one-off SQL
   `WHERE encrypted_key NOT LIKE 'v2:%' AND encrypted_key IS NOT NULL` across
   the three tables returns 0).
4. **Delete `_LEGACY_SALT` + the v1 branch** only in a later task, after the
   flag has been `False` in prod for a soak window and the existing
   `test_decrypt_legacy_v1_key` / `test_re_encrypt_api_key` tests are retired.

This keeps the system decryptable at every step and never changes v1
derivation before v1 data is gone.

## Files touched
- `backend/app/config.py` (+`ENCRYPTION_ALLOW_LEGACY_DECRYPT` setting)
- `backend/app/utils/encryption.py` (flag gate on v1 decrypt branch)
- `backend/app/tests/test_byok.py` (+flag test)

## Verify gate (canonical venv)
```
cd /opt/flowmanner/.worktrees/t_7535d4f3/backend
export PYTHONPATH=/opt/flowmanner/.worktrees/t_7535d4f3/backend
PY=/opt/flowmanner/backend/.venv/bin/python
$PY -m ruff check app/config.py app/utils/encryption.py app/tests/test_byok.py   # All checks passed!
$PY -m pytest app/tests/test_byok.py -k "encrypt or decrypt or re_encrypt or legacy"  # 4 passed
```
Note: 3 unrelated `test_byok` router tests (`test_create_api_key`,
`test_list_api_keys`, `test_delete_api_key`) fail with
`RuntimeError: Router imp...` — confirmed pre-existing (fail identically on a
clean stashed tree) and unrelated to this change.
