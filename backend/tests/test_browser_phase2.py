"""Phase 2 tests: idle-timeout fix + session cleanup after blueprint runs.

2.1 — verify screenshot/snapshot/scroll reset the idle watchdog (call
      ``touch_user_interaction``, not just ``touch``).
2.2 — verify ``UnifiedExecutor._cleanup_browser_session`` closes the
      ``blueprint:<run_id>`` session on all terminal paths (success, failure,
      budget exhausted, lease lost, unhandled exception) and is NOT called
      on the HITL-pause path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 2.1: Idle-timeout watchdog reset ──────────────────────────────────


class TestTouchUserInteraction:
    """Methods that keep the page alive should reset the *idle* clock
    (``touch_user_interaction``), not just the activity clock (``touch``).

    The session watchdog checks ``last_user_interaction`` exclusively —
    ``touch()`` alone does not prevent a 300 s timeout mid-blueprint.
    """

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.is_active.return_value = True
        session.page = MagicMock()
        session.page.url = "https://example.com"
        session.page.title = AsyncMock(return_value="Example")
        session.page.screenshot = AsyncMock(return_value=b"png")
        session.page.evaluate = AsyncMock(return_value=None)
        session.page.query_selector = AsyncMock(return_value=None)
        session.touch_user_interaction = MagicMock()
        session.touch = MagicMock()
        session.clear_elements = MagicMock()
        session.register_element = MagicMock(return_value="e1")
        session.snapshot_fingerprint = ""
        return session

    @pytest.mark.asyncio
    async def test_screenshot_calls_touch_user_interaction(self, mock_session):
        from app.services.browser_service import BrowserService

        with patch(
            "app.services.browser_service.get_browser_manager"
        ) as mock_mgr:
            mock_mgr.return_value.get_user_session.return_value = mock_session
            svc = BrowserService()
            await svc.screenshot("user-1")

        mock_session.touch_user_interaction.assert_called_once()
        mock_session.touch.assert_not_called()

    @pytest.mark.asyncio
    async def test_snapshot_calls_touch_user_interaction(self, mock_session):
        from app.services.browser_service import BrowserService

        mock_session.page.evaluate = AsyncMock(
            return_value={"elements": [], "fingerprint": "abc"}
        )

        with patch(
            "app.services.browser_service.get_browser_manager"
        ) as mock_mgr:
            mock_mgr.return_value.get_user_session.return_value = mock_session
            svc = BrowserService()
            await svc.snapshot("user-1")

        mock_session.touch_user_interaction.assert_called_once()
        mock_session.touch.assert_not_called()

    @pytest.mark.asyncio
    async def test_scroll_calls_touch_user_interaction(self, mock_session):
        from app.services.browser_service import BrowserService

        with patch(
            "app.services.browser_service.get_browser_manager"
        ) as mock_mgr:
            mock_mgr.return_value.get_user_session.return_value = mock_session
            svc = BrowserService()
            await svc.scroll("user-1")

        mock_session.touch_user_interaction.assert_called_once()
        mock_session.touch.assert_not_called()


# ── 2.2: Browser session cleanup on run termination ───────────────────


class TestBrowserSessionCleanup:
    """``_cleanup_browser_session`` must close the blueprint-scoped browser
    session on every terminal path so headless Chromium processes don't
    leak and exhaust the 2-session capacity.
    """

    @pytest.mark.asyncio
    async def test_cleanup_closes_blueprint_session(self):
        """The helper derives ``blueprint:<run_id>`` and asks the manager
        to close that user session."""
        from app.services.substrate.executor import UnifiedExecutor

        executor = UnifiedExecutor.__new__(UnifiedExecutor)

        mock_manager = MagicMock()
        mock_manager.close_user_session = AsyncMock()

        with patch(
            "app.services.browser_manager.get_browser_manager",
            return_value=mock_manager,
        ):
            await executor._cleanup_browser_session("run-abc")

        mock_manager.close_user_session.assert_awaited_once_with(
            "blueprint:run-abc"
        )

    @pytest.mark.asyncio
    async def test_cleanup_no_session_is_silent(self):
        """If no browser session exists for this run, cleanup must not raise."""
        from app.services.substrate.executor import UnifiedExecutor

        executor = UnifiedExecutor.__new__(UnifiedExecutor)

        mock_manager = MagicMock()
        mock_manager.close_user_session = AsyncMock(
            side_effect=RuntimeError("no session")
        )

        with patch(
            "app.services.browser_manager.get_browser_manager",
            return_value=mock_manager,
        ):
            # Must not raise
            await executor._cleanup_browser_session("run-no-browser")

    @pytest.mark.asyncio
    async def test_cleanup_not_called_on_hitl_pause_path(self):
        """The HITL-pause except-block in _execute_inner must NOT call
        _cleanup_browser_session — the session must survive for the
        resumed run.

        We verify by reading the executor source: the HITLPaused handler
        has no cleanup call, while every other terminal path does.
        """
        import inspect

        from app.services.substrate.executor import UnifiedExecutor

        source = inspect.getsource(UnifiedExecutor._execute_inner_run)

        # Find the HITLPaused except-block — it must not reference cleanup.
        # Split on "except HITLPaused" and check the block up to the next
        # "except" doesn't contain "_cleanup_browser_session".
        hitl_block_start = source.index("except HITLPaused")
        # Find the next except clause after the HITL block
        rest = source[hitl_block_start:]
        lines = rest.split("\n")

        # Collect lines until the next "except " at the same indent
        hitl_lines = []
        for i, line in enumerate(lines):
            if i == 0:
                hitl_lines.append(line)
                continue
            if line.strip().startswith("except ") and not line.strip().startswith(
                "except:"
            ):
                break
            hitl_lines.append(line)

        hitl_block = "\n".join(hitl_lines)
        assert "_cleanup_browser_session" not in hitl_block, (
            "HITL-pause path must NOT close the browser session — the "
            "resumed run needs it."
        )

    @pytest.mark.asyncio
    async def test_cleanup_called_on_all_terminal_paths(self):
        """Every terminal path except HITL pause must call _cleanup_browser_session.

        Verify via source inspection that the string appears in the
        BudgetExhausted, LeaseLostError, generic Exception, and
        post-strategy-success paths.
        """
        import inspect

        from app.services.substrate.executor import UnifiedExecutor

        source = inspect.getsource(UnifiedExecutor._execute_inner_run)

        # Should appear exactly 4 times: budget, lease_lost, generic
        # exception, and success path.
        count = source.count("_cleanup_browser_session")
        assert count == 4, (
            f"Expected _cleanup_browser_session on 4 terminal paths "
            f"(budget, lease_lost, exception, success), found {count}"
        )
