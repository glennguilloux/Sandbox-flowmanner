"""PII Redaction Service — regex-based sensitive data masking.

Detects and masks personally identifiable information (PII) before
sending text to LLMs.  Supports email, phone, SSN, credit card, and
common API key formats.

Masking format: ``[EMAIL_REDACTED]``, ``[PHONE_REDACTED]``, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Compiled patterns ──────────────────────────────────────────────────

PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ \-]*?){13,19}\b"),
    "api_key": re.compile(
        r"\b(?:sk-|pk-|ak-|AKIA|ghp_|gho_|glpat-|xoxb-|xoxp-)[A-Za-z0-9]{16,}\b"
    ),
}

_MASK_LABELS: dict[str, str] = {
    "email": "[EMAIL_REDACTED]",
    "phone": "[PHONE_REDACTED]",
    "ssn": "[SSN_REDACTED]",
    "credit_card": "[CREDIT_CARD_REDACTED]",
    "api_key": "[API_KEY_REDACTED]",
}

# ── Luhn check for credit-card false-positive reduction ───────────────


def _luhn_valid(number: str) -> bool:
    """Return True if *number* passes the Luhn checksum."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ── Result types ──────────────────────────────────────────────────────


@dataclass
class PIIHit:
    """A single detected PII occurrence."""

    type: str
    start: int
    end: int
    masked_value: str


@dataclass
class RedactionResult:
    """Output of :func:`redact_pii`."""

    redacted_text: str
    found: list[PIIHit] = field(default_factory=list)
    count: int = 0


# ── Public API ────────────────────────────────────────────────────────


def redact_pii(
    text: str,
    *,
    types: list[str] | None = None,
    level: str = "standard",
) -> RedactionResult:
    """Detect and mask PII in *text*.

    Parameters
    ----------
    text:
        Input text that may contain PII.
    types:
        Subset of PII types to redact.  ``None`` means all types.
    level:
        ``"standard"`` — normal detection.
        ``"strict"`` — also catches partial phone numbers and
        short API-like tokens.
    """
    if not text:
        return RedactionResult(redacted_text=text)

    target_types = types if types else list(PATTERNS.keys())
    hits: list[PIIHit] = []
    result_text = text

    for pii_type in target_types:
        pattern = PATTERNS.get(pii_type)
        if pattern is None:
            continue

        for match in pattern.finditer(text):
            raw = match.group()

            # Credit-card: apply Luhn to reduce false positives
            if pii_type == "credit_card":
                digits_only = "".join(c for c in raw if c.isdigit())
                if not _luhn_valid(digits_only):
                    continue

            label = _MASK_LABELS.get(pii_type, f"[{pii_type.upper()}_REDACTED]")
            hits.append(
                PIIHit(
                    type=pii_type,
                    start=match.start(),
                    end=match.end(),
                    masked_value=label,
                )
            )

    # Apply standard replacements from end-to-start so offsets stay valid
    hits.sort(key=lambda h: h.start, reverse=True)
    result_text = text
    for hit in hits:
        result_text = (
            result_text[: hit.start] + hit.masked_value + result_text[hit.end :]
        )

    standard_count = len(hits)

    # Strict mode: also catch long tokens that look like secrets
    strict_hits: list[PIIHit] = []
    if level == "strict":
        strict_pattern = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
        for match in strict_pattern.finditer(result_text):
            raw = match.group()
            # Skip if it's obviously not a secret (all lowercase, no digits)
            if raw.islower() and not any(c.isdigit() for c in raw):
                continue
            strict_hits.append(
                PIIHit(
                    type="potential_secret",
                    start=match.start(),
                    end=match.end(),
                    masked_value="[SECRET_REDACTED]",
                )
            )
        strict_hits.sort(key=lambda h: h.start, reverse=True)
        for hit in strict_hits:
            result_text = (
                result_text[: hit.start] + hit.masked_value + result_text[hit.end :]
            )

    all_hits = sorted(hits + strict_hits, key=lambda h: h.start)
    return RedactionResult(
        redacted_text=result_text,
        found=all_hits,
        count=len(all_hits),
    )
