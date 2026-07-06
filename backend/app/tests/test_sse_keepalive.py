"""Tests for SSE keepalive ping (Task 1.2a).

Verifies the _sse_keepalive helper emits ``: ping`` comments when the
gap between yields exceeds the configured interval.
"""

from app.services.chat_service import _SSE_KEEPALIVE_INTERVAL, _sse_keepalive


class TestSseKeepalive:
    def test_returns_ping_when_gap_exceeds_interval(self):
        """A gap of 16s (> 15s interval) should emit a keepalive."""
        result = _sse_keepalive(0.0, 16.0)
        assert result == ": ping\n\n"

    def test_returns_none_when_gap_within_interval(self):
        """A gap of 5s (< 15s interval) should not emit a keepalive."""
        result = _sse_keepalive(0.0, 5.0)
        assert result is None

    def test_returns_none_at_exact_boundary(self):
        """At exactly the interval, no keepalive (strictly greater check)."""
        result = _sse_keepalive(0.0, float(_SSE_KEEPALIVE_INTERVAL))
        assert result is None

    def test_returns_ping_just_over_boundary(self):
        """Just over the interval should emit a keepalive."""
        result = _sse_keepalive(0.0, float(_SSE_KEEPALIVE_INTERVAL) + 0.01)
        assert result == ": ping\n\n"

    def test_interval_constant(self):
        """The interval should be 15 seconds as specified by Opus Round 2."""
        assert _SSE_KEEPALIVE_INTERVAL == 15
