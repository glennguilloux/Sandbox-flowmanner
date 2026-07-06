"""Tests for app.database.fresh_session — Task 2.8.

Verifies the async context manager commits on success, rolls back on
exception, and yields a usable session.  Uses mocked AsyncSession since
the test environment has no live PostgreSQL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession with async methods."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Patch AsyncSessionLocal to return our mock session."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


class TestFreshSessionContextManager:
    """Unit tests for the fresh_session() async context manager."""

    @pytest.mark.asyncio
    async def test_import_ok(self):
        """fresh_session is importable from app.database."""
        from app.database import fresh_session

        assert callable(fresh_session)

    @pytest.mark.asyncio
    async def test_yields_session_and_commits_on_success(self, mock_session, mock_session_factory):
        """fresh_session() yields a session and commits when no exception occurs."""
        from app.database import fresh_session

        with patch("app.database.AsyncSessionLocal", mock_session_factory):
            async with fresh_session() as db:
                # Session should be the mock
                assert db is mock_session
                # Simulate some work
                db.add(MagicMock())

        # Commit should have been called on successful exit
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self, mock_session, mock_session_factory):
        """fresh_session() rolls back when an exception occurs."""
        from app.database import fresh_session

        with (
            patch("app.database.AsyncSessionLocal", mock_session_factory),
            pytest.raises(ValueError, match="intentional"),
        ):
            async with fresh_session() as db:
                raise ValueError("intentional test error")

        # Rollback should have been called, commit should NOT
        mock_session.rollback.assert_awaited_once()
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_commit_not_called_on_error(self, mock_session, mock_session_factory):
        """Verify commit is skipped when an exception occurs mid-work."""
        from app.database import fresh_session

        with patch("app.database.AsyncSessionLocal", mock_session_factory), pytest.raises(RuntimeError):  # noqa: PT012
            async with fresh_session() as db:
                await db.flush()
                raise RuntimeError("db error mid-operation")

        mock_session.rollback.assert_awaited_once()
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_commit_called_after_successful_work(self, mock_session, mock_session_factory):
        """Verify the commit happens AFTER the body completes (not before)."""
        from app.database import fresh_session

        call_order = []

        mock_session.commit.side_effect = lambda: call_order.append("commit")
        mock_session.flush = AsyncMock(side_effect=lambda: call_order.append("flush"))

        with patch("app.database.AsyncSessionLocal", mock_session_factory):
            async with fresh_session() as db:
                await db.flush()
                call_order.append("body_end")

        # flush → body_end → commit
        assert call_order == ["flush", "body_end", "commit"]
