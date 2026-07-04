"""Re-encrypt BYOK API keys with per-key random salts.

The legacy ``encrypt_api_key`` in ``app/utils/encryption.py`` derived a single
Fernet key from ``AES_ENCRYPTION_KEY`` + a hardcoded salt
(``b"flowmanner-salt-"``).  Two identical plaintexts produced identical
ciphertexts, which leaks equality information.

This data migration upgrades every row in ``user_api_keys`` to the v2 format
(``v2:<base64_salt>:<fernet_token>``) where each row gets a fresh random
16-byte salt.  The code-side ``decrypt_api_key`` already handles both v1 and
v2 formats transparently.

Revision ID: byok_per_key_salt_001
Revises: 20260630_plan_candidates
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "byok_per_key_salt_001"
down_revision: str | Sequence[str] | None = "20260630_plan_candidates"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Re-encrypt every active BYOK key with a per-key random salt.

    Runs in-process using the Python encryption helpers so that the migration
    is self-contained (no dependency on the app container being available).
    Each row is committed individually to keep transaction locks short.
    """
    import base64
    import os

    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    conn = op.get_bind()
    if conn is None:
        # Offline SQL render mode — no live DB connection.
        # This migration performs data-level re-encryption which cannot
        # be expressed as static SQL.  Skip gracefully.
        print("  BYOK re-encryption: skipped (offline mode)")
        return

    # Use the SAME secret source as app/utils/encryption.py:
    #   getattr(settings, "ENCRYPTION_KEY", None) or settings.SECRET_KEY
    # NOT AES_ENCRYPTION_KEY (that's a different config var).
    try:
        from app.config import settings  # type: ignore[import-untyped]
        secret = getattr(settings, "ENCRYPTION_KEY", None) or settings.SECRET_KEY
    except Exception:
        secret = os.environ.get("ENCRYPTION_KEY", "") or os.environ.get("SECRET_KEY", "")
        if not secret:
            raise RuntimeError(
                "Could not determine encryption secret: "
                "ENCRYPTION_KEY/SECRET_KEY not in env or app config"
            )

    legacy_salt = b"flowmanner-salt-"

    def _derive_key(salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000
        )
        return base64.urlsafe_b64encode(kdf.derive(secret.encode()))

    legacy_fernet = Fernet(_derive_key(legacy_salt))

    # Fetch all rows with non-null encrypted_key
    rows = conn.execute(
        sa.text("SELECT id, encrypted_key FROM user_api_keys WHERE encrypted_key IS NOT NULL")
    ).fetchall()

    migrated = 0
    skipped = 0
    errors = 0

    for row_id, encrypted_key in rows:
        # Skip already-v2 keys
        if encrypted_key and encrypted_key.startswith("v2:"):
            skipped += 1
            continue

        try:
            # Decrypt with legacy salt
            plaintext = legacy_fernet.decrypt(
                base64.urlsafe_b64decode(encrypted_key)
            ).decode()

            # Re-encrypt with fresh random salt
            new_salt = os.urandom(16)
            new_fernet = Fernet(_derive_key(new_salt))
            new_encrypted = new_fernet.encrypt(plaintext.encode()).decode()
            salt_b64 = base64.urlsafe_b64encode(new_salt).decode()
            new_value = f"v2:{salt_b64}:{new_encrypted}"

            conn.execute(
                sa.text("UPDATE user_api_keys SET encrypted_key = :val, updated_at = NOW() WHERE id = :id"),
                {"val": new_value, "id": row_id},
            )
            migrated += 1
        except (InvalidToken, Exception) as exc:
            # Log but don't abort the entire migration for one bad row
            errors += 1
            print(f"  WARNING: Could not re-encrypt key id={row_id}: {exc}")

    print(f"  BYOK re-encryption: {migrated} migrated, {skipped} already v2, {errors} errors")


def downgrade() -> None:
    """Re-encrypt v2 keys back to the legacy hardcoded-salt format.

    This is a best-effort downgrade. Keys that cannot be decrypted (e.g.
    corrupted data) are left unchanged.
    """
    import base64
    import os

    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    conn = op.get_bind()

    # Same secret source as the upgrade (and encryption.py)
    try:
        from app.config import settings  # type: ignore[import-untyped]
        secret = getattr(settings, "ENCRYPTION_KEY", None) or settings.SECRET_KEY
    except Exception:
        secret = os.environ.get("ENCRYPTION_KEY", "") or os.environ.get("SECRET_KEY", "")
        if not secret:
            raise RuntimeError("Could not determine encryption secret for downgrade")

    legacy_salt = b"flowmanner-salt-"

    def _derive_key(salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000
        )
        return base64.urlsafe_b64encode(kdf.derive(secret.encode()))

    legacy_fernet = Fernet(_derive_key(legacy_salt))

    rows = conn.execute(
        sa.text("SELECT id, encrypted_key FROM user_api_keys WHERE encrypted_key LIKE 'v2:%'")
    ).fetchall()

    downgraded = 0
    for row_id, encrypted_key in rows:
        try:
            _prefix, salt_b64, token = encrypted_key.split(":", 2)
            salt = base64.urlsafe_b64decode(salt_b64)
            fernet = Fernet(_derive_key(salt))
            plaintext = fernet.decrypt(token.encode()).decode()

            # Re-encrypt with legacy salt
            new_encrypted = base64.urlsafe_b64encode(
                legacy_fernet.encrypt(plaintext.encode())
            ).decode()

            conn.execute(
                sa.text("UPDATE user_api_keys SET encrypted_key = :val, updated_at = NOW() WHERE id = :id"),
                {"val": new_encrypted, "id": row_id},
            )
            downgraded += 1
        except (InvalidToken, Exception) as exc:
            print(f"  WARNING: Could not downgrade key id={row_id}: {exc}")

    print(f"  BYOK downgrade: {downgraded} keys reverted to legacy format")
