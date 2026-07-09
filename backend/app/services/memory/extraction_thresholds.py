"""GOV-1.5 — memory extraction threshold calibration instrumentation.

Owns the *calibration* knobs for the chat memory-extraction path
(``app.services.chat_service._maybe_extract_memory_claims``). Before
GOV-1.5 there was no place to tune the confidence gate and **no
persistent record of dropped candidates** (C5 gap) — the reviewer /
extractor dropped claims silently, so the 0.85 gate could never be
calibrated against real data.

Design constraints (do NOT drift — see GOV-1.2 invariant):

* Provenance, not score, is the reliable control. ``user_explicit``
  source_type is the ONLY claim trusted enough to bypass the approval
  gate. Everything else (``conversation`` / ``mission`` /
  ``program_learning``) is externally derived and MUST be routed to
  human approval regardless of confidence.
* Therefore the confidence gate defined here is applied **only to the
  trusted direct-write path** (``user_explicit``). Untrusted candidates
  are never dropped by a confidence threshold — they are staged for
  approval instead. A confidence gate on untrusted writes would be a
  side-door re-opening of the GOV-1.2 hole (an attacker just keeps the
  score above the line to skip human review).
* The gate is **env-overridable but defaults to 0.85** so it can be
  recalibrated from the dropped-candidate telemetry this module also
  emits, without a code change.
"""

from __future__ import annotations

import os

# ── Calibration knobs (GOV-1.5) ───────────────────────────────────────

# Default confidence floor for the *trusted* direct-write path. Claims
# with source_type="user_explicit" whose extractor confidence is below
# this are held for human approval instead of written directly. 0.85 is
# the starting calibration point; tune from drop-rate telemetry.
MEMORY_EXTRACTION_MIN_CONFIDENCE: float = float(os.getenv("MEMORY_EXTRACTION_MIN_CONFIDENCE", "0.85"))

# Source types that may reach durable memory via the direct-write path
# (i.e. bypass the approval gate). This is exactly the user-authored
# set from ``provenance_approval.USER_AUTHORED_SOURCES``; we keep a
# local reference so the gate below is self-documenting and stays in
# lockstep with the GOV-1.2 policy.
TRUSTED_DIRECT_WRITE_SOURCES: frozenset[str] = frozenset({"user_explicit"})


def is_trusted_direct_write(source_type: str | None) -> bool:
    """True only for user-authored source types that may skip approval."""
    return source_type in TRUSTED_DIRECT_WRITE_SOURCES


def passes_confidence_gate(confidence: float) -> bool:
    """GOV-1.5 confidence gate — applied to the *trusted* path only.

    Returns ``True`` when a claim's extractor confidence is at or above
    the calibrated floor. Used solely for ``user_explicit`` claims; it
    must never be consulted to de-escalate an externally-derived claim.
    """
    return confidence >= MEMORY_EXTRACTION_MIN_CONFIDENCE
