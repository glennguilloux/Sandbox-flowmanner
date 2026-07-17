"""Tests for the v2 changelog read-only router.

Covers GET /api/v2/changelog (list, paginated envelope) and
GET /api/v2/changelog/{version} (single + 404). Uses the real app with
get_db overridden to a mock session so no live DB is required. Mirrors the
blog/roadmap v2 router test style.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main_fastapi import app
from app.models.changelog_models import ChangelogEntry

pytestmark = pytest.mark.integration

CHANGELOG_URL = "/api/v2/changelog"


def _make_entry(version: str, title: str = "T", released=None, sort_order: int = 0):
    return ChangelogEntry(
        id=uuid.uuid4(),
        version=version,
        title=title,
        summary="s",
        body="b",
        category="release",
        is_featured=False,
        released_at=released or datetime.now(UTC),
        sort_order=sort_order,
    )


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Mock session that serves a fixed entry list and a by-version lookup."""

    def __init__(self, entries):
        self._entries = entries

    async def scalars(self, stmt=None):
        # The list query: return all entries ordered (newest first by input order).
        return _FakeResult(self._entries)

    async def scalar(self, stmt=None):
        # count() -> len; version lookup -> first match.
        sql = str(stmt) if stmt is not None else ""
        if "count" in sql.lower():
            return len(self._entries)
        for e in self._entries:
            if f"'{e.version}'" in sql:
                return e
        return None

    async def execute(self, stmt=None):
        return _FakeResult(self._entries)


@pytest.fixture
def client(mock_db_session):
    entries = [
        _make_entry("R9", "R9 title", datetime(2026, 7, 17, tzinfo=UTC), sort_order=90),
        _make_entry("T1", "T1 title", datetime(2026, 7, 9, tzinfo=UTC), sort_order=80),
    ]
    fake = _FakeSession(entries)

    async def override_get_db():
        yield fake

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def test_list_changelog_returns_envelope(client: TestClient):
    resp = client.get(CHANGELOG_URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    assert "items" in body["data"]
    assert body["data"]["total"] == 2
    versions = [i["version"] for i in body["data"]["items"]]
    assert versions == ["R9", "T1"]  # newest first


def test_get_changelog_version_404(client: TestClient):
    resp = client.get(f"{CHANGELOG_URL}/NOPE")
    assert resp.status_code == 404
    assert "NOPE" in resp.text
