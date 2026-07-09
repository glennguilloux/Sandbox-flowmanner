"""Extraction-time poison scan — GOV-1.3a (triage aid, escalate-only).

This module scans a memory write *at staging time* (``stage_pending_write``)
for prompt-injection / poison patterns before the claim reaches durable
review. It is a HEURISTIC TRIAGE AID, NOT the reliable control:

  - The reliable control is the provenance gate (GOV-1.2): externally-
    derived claims are routed to human approval regardless of score.
  - This scan may ONLY *escalate* (flag, annotate, prioritize for review).
    It must NEVER *de-escalate* — i.e. it must never downgrade a
    provenance-mandated approval or skip staging. A "scan passed" result
    is a signal an attacker optimizes against, exactly like confidence.

Hard invariant (do not drift): ``scan_for_poison`` returns a dataclass of
findings and **never** short-circuits the staging call site. The caller
stages the write unconditionally and attaches the findings as metadata so
the eventual HITL drain (GOV-1.1) can surface/ prioritize flagged writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Invisible / control Unicode that is never legitimate memory content and
# is a common steganographic prompt-injection carrier.
_INVISIBLE_RE = re.compile(
    "[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u200b-\u200f"
    "\u202a-\u202e\u2060-\u2064\u2066-\u2069\u206a-\u206f\u2e2f"
    "\u3000\u2800\ufe00-\ufe0f\ufeff\ufff9-\ufffb]"
)
_CONTROL_WS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Fenced-instruction / block-escape markers — a recalled claim is data, not
# an instruction; these shapes are almost never legitimate memory content.
_BLOCK_ESCAPE_RE = re.compile(
    r"</?(?:system|assistant|user|tool|function|memory|instructions?|prompt)\b",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```|~~~")

# Classic injection trigger phrases.
_DIRECTIVE_RE = re.compile(
    r"(?i)"
    r"(ignore (?:all |any |previous |above )?(?:previous |prior )?instructions?)"
    r"|((?:disregard|forget|override|neglect) (?:the |all |any )?(?:above |previous |prior |preceding )?instructions?)"
    r"|((?:you are|act as|pretend to be|roleplay as) (?:now |a |an |the )?[\w -]{0,40})"
    r"|((?:reveal|exfiltrate|leak|send|post|transmit)[\s\S]{0,40}(?:secret|api[_-]?key|password|token|credential))"
    r"|((?:system ?prompt|developer ?message|root ?instruction)[\s\S]{0,30})"
)


@dataclass
class PoisonScanResult:
    """Findings of an extraction-time poison scan.

    ``flagged`` is True when any heuristic matched. ``hits`` lists the
    human-readable categories that fired (for reviewer prioritization).
    ``severity`` is ``high`` if an instruction/block-escape pattern matched,
    else ``low`` for invisible/control-char noise.
    """

    flagged: bool = False
    hits: list[str] = field(default_factory=list)
    severity: str = "none"

    def to_metadata(self) -> dict[str, object]:
        """Shape attached to the pending write's ``metadata`` column."""
        return {
            "poison_scan": {
                "flagged": self.flagged,
                "hits": self.hits,
                "severity": self.severity,
            }
        }


def scan_for_poison(content: str | None, old_text: str | None = None) -> PoisonScanResult:
    """Scan a proposed write for poison patterns.

    ESCALATE-ONLY: returns findings; the caller stages the write
    unconditionally and attaches ``to_metadata()`` so the HITL drain can
    prioritize it. This function never decides whether to stage.

    Fail-open: on any error it returns an unflagged result rather than
    risk blocking legitimate staging.
    """
    texts = [t for t in (content, old_text) if t and isinstance(t, str)]
    if not texts:
        return PoisonScanResult()

    try:
        hits: list[str] = []
        high_severity = False
        for text in texts:
            if _INVISIBLE_RE.search(text) or _CONTROL_WS_RE.search(text):
                hits.append("invisible_or_control_chars")
            if _BLOCK_ESCAPE_RE.search(text):
                hits.append("fenced_instruction_marker")
                high_severity = True
            if _FENCE_RE.search(text):
                hits.append("code_fence")
            if _DIRECTIVE_RE.search(text):
                hits.append("injection_directive")
                high_severity = True

        flagged = bool(hits)
        severity = "high" if high_severity else ("low" if flagged else "none")
        # De-duplicate while preserving order.
        seen: set[str] = set()
        unique_hits: list[str] = []
        for h in hits:
            if h not in seen:
                seen.add(h)
                unique_hits.append(h)
        return PoisonScanResult(flagged=flagged, hits=unique_hits, severity=severity)
    except Exception:  # pragma: no cover - defensive
        return PoisonScanResult()
