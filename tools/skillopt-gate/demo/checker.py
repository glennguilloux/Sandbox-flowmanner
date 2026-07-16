"""Demo checker for skillopt-gate.

This is a stand-in for YOUR held-out test. A real checker might run a
pytest suite, a linter, or a task harness over the skill text. Here we
score how many of a set of *required phrases* the skill contains
(hard = fraction present; soft = fraction + length penalty handed).
"""

from __future__ import annotations

# Held-out "golden" requirements for the demo skill.
REQUIRED = [
    "always run the test before claiming done",
    "stage proposals for human review",
    "never mutate the live skill without explicit adopt",
    "log the per-edit gate decision",
]


def score(skill: str) -> tuple[float, float]:
    """Return (hard, soft) in 0..1 for the given skill text."""
    low = skill.lower()
    present = sum(1 for r in REQUIRED if r.lower() in low)
    hard = present / len(REQUIRED)
    # soft: hard plus a small reward for being concise (<=600 chars)
    length_ok = 1.0 if len(skill) <= 600 else max(0.0, 1.0 - (len(skill) - 600) / 2000)
    soft = 0.7 * hard + 0.3 * length_ok
    return hard, soft
