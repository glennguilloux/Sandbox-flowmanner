"""Security regression tests for the file-upload endpoint (R5).

R5 covers two findings from the swarm audit:

  H1 — Path traversal: ``file.py`` concatenated ``file.filename`` unmodified
       into ``UPLOAD_DIR / f"{file_id}_{file.filename}"``. ``Path`` does not
       strip ``..``, so a crafted filename such as ``../../etc/cron.d/x`` writes
       outside ``UPLOAD_DIR``.

  M1 — Missing content validation: no size or content-type / magic-byte
       validation before ``write_bytes``.

These tests assert that a hostile filename is confined to ``UPLOAD_DIR`` and
that executable/script content is rejected. No real filesystem escape is
possible; we verify the resolved ``storage_path`` stays under ``UPLOAD_DIR``.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.api.v1.file as file_module
from app.api.deps import get_current_user
from app.api.v1.file import _safe_storage_name, _validate_upload_content
from app.database import get_db
from app.main_fastapi import app

client = TestClient(app)

UPLOAD_URL = "/api/file/upload"

# A temp UPLOAD_DIR that is unique per test session so we don't touch the real
# /opt/flowmanner/uploads. Set before the app reads UPLOAD_DIR at import time is
# not possible (module-level), so we patch the live value instead.
_TEST_UPLOAD_DIR = file_module.UPLOAD_DIR


# ── Unit tests: filename sanitisation (no network, no DB) ───────────────────


@pytest.mark.parametrize(
    "raw,expected_basename",
    [
        ("../../etc/cron.d/x", "x"),  # traversal collapses to basename
        ("../secrets.txt", "secrets.txt"),
        ("/abs/path/evil.sh", "evil.sh"),  # absolute path -> basename only
        ("a/../../b/c.txt", "c.txt"),  # mid-path traversal
    ],
)
def test_safe_storage_name_confines_to_basename(raw, expected_basename):
    file_id = "00000000-0000-0000-0000-000000000000"
    name = _safe_storage_name(file_id, raw)
    assert name == f"{file_id}_{expected_basename}"
    # The resolved path must live strictly under UPLOAD_DIR and never contain
    # a parent reference.
    resolved = file_module.UPLOAD_DIR / name
    assert resolved.parent == file_module.UPLOAD_DIR
    assert ".." not in resolved.as_posix().split("/")


def test_safe_storage_name_strips_windows_separators():
    """Backslashes (Windows paths) must not survive into the stored name on any
    platform — they are flattened to underscores so the resolved path can never
    reference a parent directory segment."""
    file_id = "00000000-0000-0000-0000-000000000000"
    name = _safe_storage_name(file_id, "..\\..\\windows\\system32\\x.dll")
    assert "\\" not in name
    assert "/" not in name
    resolved = file_module.UPLOAD_DIR / name
    # The resolved path is a direct child of UPLOAD_DIR — separators are gone,
    # so no segment can navigate to a parent directory.
    assert resolved.parent == file_module.UPLOAD_DIR


# ── Unit tests: content validation (no network, no DB) ─────────────────────


def test_validate_rejects_elf():
    with pytest.raises(HTTPException) as exc_info:
        _validate_upload_content(b"\x7fELF\x02\x01\x01\x00")
    assert exc_info.value.status_code == 400


def test_validate_rejects_windows_pe():
    with pytest.raises(HTTPException) as exc_info:
        _validate_upload_content(b"MZ\x90\x00\x03\x00")
    assert exc_info.value.status_code == 400


def test_validate_rejects_shebang_script():
    with pytest.raises(HTTPException) as exc_info:
        _validate_upload_content(b"#!/bin/sh\necho pwned\n")
    assert exc_info.value.status_code == 400


def test_validate_rejects_oversized():
    with pytest.raises(HTTPException) as exc_info:
        _validate_upload_content(b"A" * (file_module.MAX_UPLOAD_BYTES + 1))
    assert exc_info.value.status_code == 400


def test_validate_accepts_png():
    # PNG magic bytes must pass.
    _validate_upload_content(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def test_validate_accepts_plain_text():
    # Unrecognised, non-executable text is permitted (default-allow for text).
    _validate_upload_content(b"just some plain text content\n")


# ── Integration: a traversal filename must NOT escape UPLOAD_DIR ────────────


@pytest.fixture
def authed_client(monkeypatch):
    """TestClient with get_db/get_current_user overridden; yields the mock db."""
    user = MagicMock()
    user.id = 1

    db = AsyncMock()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    yield db

    app.dependency_overrides.clear()


def test_upload_traversal_filename_stays_in_upload_dir(authed_client, tmp_path, monkeypatch):
    """A filename like ../../etc/cron.d/x must never write outside UPLOAD_DIR.

    We redirect UPLOAD_DIR to a temp dir and assert the resolved storage path
    is a child of it — proving the traversal cannot escape.
    """
    monkeypatch.setattr(file_module, "UPLOAD_DIR", tmp_path)

    # Capture the DB flush/refresh so the handler returns cleanly.
    db_file = MagicMock()
    db_file.id = "file-123"
    db_file.filename = "../../etc/cron.d/x"
    db_file.content_type = "application/octet-stream"
    db_file.size = 4
    db_file.user_id = 1
    db_file.created_at = None  # handler uses "" when created_at is None

    async def _flush(*args):
        return None

    async def _refresh(*args):
        return None

    authed_client.flush = AsyncMock(side_effect=_flush)
    authed_client.refresh = AsyncMock(side_effect=_refresh)
    # The handler awaits db.add, db.flush, db.refresh in sequence.
    call_order = {"add": False}

    def _add(obj):
        call_order["add"] = True

    authed_client.add = MagicMock(side_effect=_add)

    evil_filename = "../../etc/cron.d/x"
    content = b"pwn"

    with patch.object(file_module, "UserFile", return_value=db_file):
        resp = client.post(
            UPLOAD_URL,
            files={"file": (evil_filename, content, "application/octet-stream")},
        )

    assert resp.status_code == 200, resp.text

    # The file MUST have been written inside tmp_path, never into /etc/cron.d.
    written = list(tmp_path.iterdir())
    assert len(written) == 1, f"expected exactly one file under upload dir, got {written}"
    assert written[0].parent == tmp_path
    # The basename must be just 'x' (traversal stripped), prefixed by the uuid.
    assert written[0].name.endswith("_x")
    assert ".." not in written[0].as_posix()


def test_upload_executable_content_rejected(authed_client, tmp_path, monkeypatch):
    """Uploading executable content must be refused with 400 before any write."""
    monkeypatch.setattr(file_module, "UPLOAD_DIR", tmp_path)

    db_file = MagicMock()
    authed_client.add = MagicMock()
    authed_client.flush = AsyncMock()
    authed_client.refresh = AsyncMock()

    with patch.object(file_module, "UserFile", return_value=db_file):
        resp = client.post(
            UPLOAD_URL,
            files={"file": ("payload.bin", b"\x7fELF\x02\x01\x01\x00", "application/octet-stream")},
        )

    assert resp.status_code == 400, resp.text
    # Nothing should have been written to disk.
    assert list(tmp_path.iterdir()) == []
