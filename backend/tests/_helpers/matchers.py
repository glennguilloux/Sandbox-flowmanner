"""Assertion helpers for mission tests."""

from typing import Any


def assert_mission_complete(mission: Any) -> None:
    """Assert that a mission finished successfully with real generated output.

    Use this matcher in regression and sanity tests after a mission executor call.
    It enforces the success criteria documented in
    ``docs/test-automation-strategy.md`` §11.4: the mission must be completed,
    must contain non-empty ``output_data``, and must have consumed tokens.
    """
    assert mission.status == "completed"
    assert mission.output_data not in (None, {}, [], "")
    assert mission.tokens_used is not None
    assert mission.tokens_used > 0
