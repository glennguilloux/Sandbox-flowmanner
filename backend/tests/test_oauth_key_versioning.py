"""Tests for the OAuth token key-versioning / KEK-rotation scaffold.

Covers (audit B9, §9/§12):
  * legacy (no-prefix) tokens still decrypt under the new code path;
  * new versioned writes round-trip;
  * after a KEK rotation (active version bumps, old KEK retained in the
    key-ring) the OLD envelope still decrypts while NEW writes use the new KEK.

Run standalone (no app-wide conftest) so the heavy FastAPI/OTel import graph
is avoided — these are pure crypto functions.
"""

import base64
import os

# Set required config BEFORE importing app.config (settings is built at import).
# AES_ENCRYPTION_KEY must be a VALID Fernet key (32 url-safe base64 bytes) for
# the legacy decrypt path to actually run — the app's real secret is shaped
# this way; a short placeholder would make Fernet() raise at import time.
_VALID_FERNET_KEY = base64.urlsafe_b64encode(b"x" * 32).decode()
os.environ.setdefault("SECRET_KEY", "test-secret-key-123")
os.environ.setdefault("AES_ENCRYPTION_KEY", _VALID_FERNET_KEY)

import pytest
from cryptography.fernet import Fernet

import app.integrations.oauth as oauth_mod

# Make the legacy (pre-scaffold) path use a real Fernet key.
oauth_mod.settings.AES_ENCRYPTION_KEY = _VALID_FERNET_KEY
from app.integrations.oauth import decrypt_token, encrypt_token, re_encrypt_token

# Deterministic secrets for the key-ring so rotation is actually exercised
# with two DIFFERENT KEKs (not the same fallback secret).
_SECRET_A = "rotation-test-kek-secret-A-" + "A" * 16
_SECRET_B = "rotation-test-kek-secret-B-" + "B" * 16


@pytest.fixture
def key_ring():
    """Install a two-version key-ring and clear caches around the test."""
    original_versions = oauth_mod._OAUTH_KEK_VERSIONS
    original_current = oauth_mod._OAUTH_CURRENT_KEK_VERSION
    original_cache = getattr(oauth_mod._oauth_kek_cache, "_cache", None)

    oauth_mod._OAUTH_KEK_VERSIONS = {
        1: {"secret": lambda: _SECRET_A, "salt": b"k1", "iterations": 1000},
    }
    oauth_mod._OAUTH_CURRENT_KEK_VERSION = 1
    oauth_mod._clear_oauth_kek_cache()

    yield

    oauth_mod._OAUTH_KEK_VERSIONS = original_versions
    oauth_mod._OAUTH_CURRENT_KEK_VERSION = original_current
    if original_cache is not None:
        oauth_mod._oauth_kek_cache._cache = original_cache  # type: ignore[attr-defined]
    else:
        oauth_mod._clear_oauth_kek_cache()


def _legacy_encrypt(token: str) -> str:
    """Replicate the PRE-scaffold single-key encrypt (AES_ENCRYPTION_KEY path)."""
    f = Fernet(oauth_mod.settings.AES_ENCRYPTION_KEY.encode())
    return f.encrypt(token.encode()).decode()


def test_legacy_no_prefix_token_still_decrypts(key_ring):
    """Existing stored tokens (no envelope prefix) must remain readable."""
    token = "gho_legacyaccesssecretvalue123"
    legacy_blob = _legacy_encrypt(token)

    assert not legacy_blob.startswith("v1:")
    assert decrypt_token(legacy_blob) == token


def test_new_versioned_round_trip(key_ring):
    """encrypt_token -> decrypt_token round-trips and stamps the version."""
    token = "gho_newaccesssecretvalue456"
    blob = encrypt_token(token)

    assert blob.startswith("v1:1:")
    assert decrypt_token(blob) == token


def test_rotation_keeps_old_ciphertext_decryptable(key_ring):
    """After rotating the active KEK, an old envelope must still decrypt.

    This is the core B9 guarantee: KEK_v1 ciphertext stays decryptable once
    KEK_v2 becomes active, because the envelope records which KEK encrypted it.
    """
    token_v1 = "tok_encrypted_under_kek_v1"
    blob_v1 = encrypt_token(token_v1)
    assert blob_v1.startswith("v1:1:")

    # --- ROTATE: add KEK v2, make it the active version, drop nothing ---
    oauth_mod._OAUTH_KEK_VERSIONS = {
        1: {"secret": lambda: _SECRET_A, "salt": b"k1", "iterations": 1000},
        2: {"secret": lambda: _SECRET_B, "salt": b"k2", "iterations": 1000},
    }
    oauth_mod._OAUTH_CURRENT_KEK_VERSION = 2
    oauth_mod._clear_oauth_kek_cache()

    # Old v1 envelope still decrypts under the new active KEK.
    assert decrypt_token(blob_v1) == token_v1

    # New writes use KEK v2 and round-trip.
    token_v2 = "tok_encrypted_under_kek_v2"
    blob_v2 = encrypt_token(token_v2)
    assert blob_v2.startswith("v1:2:")
    assert decrypt_token(blob_v2) == token_v2

    # The two envelopes are NOT interchangeable (different KEKs): the v2
    # ciphertext must NOT validate under the v1 key.
    from cryptography.fernet import InvalidToken as _InvalidToken

    f1 = Fernet(oauth_mod._oauth_kek_cache()[1])
    with pytest.raises(_InvalidToken):
        f1.decrypt(base64.urlsafe_b64decode(blob_v2.split(":")[2]))


def test_re_encrypt_token_rewraps_under_current_kek(key_ring):
    """re_encrypt_token upgrades any form to the current KEK envelope."""
    token = "tok_to_be_rewrapped"
    legacy_blob = _legacy_encrypt(token)

    rewrapped = re_encrypt_token(legacy_blob)
    assert rewrapped.startswith("v1:1:")
    assert decrypt_token(rewrapped) == token


def test_malformed_envelope_raises(key_ring):
    with pytest.raises(ValueError, match="Invalid KEK version"):
        decrypt_token("v1:notanint:garbage")

    with pytest.raises(ValueError, match="Incorrect padding"):
        decrypt_token("v1:1:!!not-base64!!")
