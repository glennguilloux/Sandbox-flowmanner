"""MemoryCitationService — chat-side recall + filtering for T33 (Inline
Memory Citations in Chat).

T19 ships substring-based recall via ``PersonalMemoryService.recall()``.
T33 wraps that with the chat-specific safety filters and prompt-injection
format. This service is intentionally a thin layer:

* ``recall_for_chat`` — substring recall + defensive exclusion of
  ``sensitivity in {"sensitive", "restricted"}`` and ``scope == "private"``.
  The defensive filter is the stop-rule mitigation for "sensitive memory
  shown in chat" (see plan §14 risk register).

* ``format_memory_block`` — build a system-message-ready text block
  describing the recalled claims for the LLM prompt. Each (subject,
  predicate, object) fragment is passed through ``scrub_recalled_claim_text``
  (GOV-1.3b read-side defense) to strip invisible Unicode, control
  whitespace, fenced-instruction markers, and neutralize injection trigger
  phrases. The block is **deliberately decoupled** from the short-UUID
  citation label the frontend renders — the LLM never sees the citation
  label, only the (subject, predicate, object, confidence) tuple. The chip
  label is derived from the claim UUID in ``build_recall_used_event``.

* ``build_recall_used_event`` — build one ``memory_recall_used`` SSE
  event payload per cited claim. Emitted AFTER the assistant message is
  persisted so ``message_id`` is known.

Hard guardrails (per the T33 plan §3 Backend Constraints):

* No ``db.commit()`` — the service only ``flush()``es via the underlying
  ``PersonalMemoryService.recall`` call. The route / streaming function
  owns the transaction.
* No new tables, no new routes.
* Defensive filter MUST be applied to every claim before it reaches
  either the prompt or the SSE event. The stop rule says: "The model
  needs access to sensitive/restricted claims" halts implementation.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from app.services.personal_memory_service import PersonalMemoryService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.personal_memory_models import PersonalMemoryClaim

logger = logging.getLogger(__name__)


# Top-K cap for the prompt-injection block. The plan §7 limits recall to
# top-5 to avoid prompt pollution.
CHAT_RECALL_TOP_K: int = 5

# Confidence floor for substring matches (decision M = "semantic ≥ 0.7
# intent, implemented in T33 as substring presence + confidence ≥ 0.7
# floor"). Real semantic similarity is deferred to T33.1/T20.
CHAT_RECALL_MIN_CONFIDENCE: float = 0.7

# Defensive exclusion list. Per plan §13 M3 and §14 stop rule. If this
# set ever changes, update §13/§14 in the plan doc and the test suite.
_EXCLUDED_SENSITIVITIES: frozenset[str] = frozenset({"sensitive", "restricted"})
_EXCLUDED_SCOPES: frozenset[str] = frozenset({"private"})

# ---------------------------------------------------------------------------
# Recall-side scrubber (GOV-1.3b harm reduction).
#
# A recalled PersonalMemoryClaim is attacker-controlled text (it was written by
# the background reviewer or an earlier agent run, which can be poisoned). When
# it is injected into the live chat LLM prompt via ``format_memory_block`` it
# must not be able to smuggle prompt-injection directives, control characters,
# or fenced-instruction blocks past the model. This is MITIGATION, not
# neutralization: a scrubbed instruction is still *visible* to the model, so
# the surrounding ``<memory-context>`` framing (see ``chat_context.py``) and
# provenance gating (GOV-1.2) remain the real controls. Status must never read
# "poisoning is handled."
#
# Design constraints (kept minimal + additive per GOV-1.3b):
#   * Never raises on recall — a scrubber bug must not break chat.
#   * Never alters the *semantic* content of a claim, only strips control /
#     injection syntax. Falls back to the original string on any error.
#   * Does NOT drop claims — only the read-side fence + gate decide that.
# ---------------------------------------------------------------------------

# Invisible / control Unicode ranges often abused for steganographic prompts
# and homograph attacks. We strip them; they carry no legitimate memory value.
_INVISIBLE_RE = re.compile(
    "["
    "\u00ad"  # soft hyphen
    "\u034f"  # combining grapheme joiner
    "\u061c"  # arabic letter mark
    "\u115f\u1160"  # hangul filler / choseong filler
    "\u17b4\u17b5"  # khmer vowel signs
    "\u200b-\u200f"  # zero-width (space, nbsp, joiner, non-joiner)
    "\u202a-\u202e"  # directional formatting
    "\u2060-\u2064"  # word joiner / invisible operators
    "\u2066-\u2069"  # directional isolate
    "\u206a-\u206f"  # deprecated directional overrides
    "\u2e2f"
    "\u3000"  # ideographic space
    "\u2800"  # braille blank
    "\ufe00-\ufe0f"  # variation selectors
    "\ufeff"  # byte order mark
    "\ufff9-\ufffb"  # interlinear annotation marks
    "]"
)

# Whitespace-control chars that can be used to obfuscate directives.
_CONTROL_WS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Blatant fenced-instruction / block-escape markers. A recalled claim is data,
# not an instruction; these shapes are almost never legitimate memory content.
_BLOCK_ESCAPE_RE = re.compile(
    r"</?(?:system|assistant|user|tool|function|memory|instructions?|prompt)\b",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```|~~~")

# Classic injection trigger phrases. We neutralize by prefixing rather than
# deleting, so the *presence* of the claim is preserved for reviewer audit
# while the directive is defused.
_DIRECTIVE_PREFIX_RE = re.compile(
    r"(?i)"
    r"(ignore (?:all |any |previous |above )?(?:previous |prior )?instructions?)"
    r"|((?:disregard|forget|override|neglect) (?:the |all |any )?(?:above |previous |prior |preceding )?instructions?)"
    r"|((?:you are|act as|pretend to be|roleplay as) (?:now |a |an |the )?[\w -]{0,40})"
    r"|((?:reveal|exfiltrate|leak|send|post|transmit)[\s\S]{0,40}(?:secret|api[_-]?key|password|token|credential))"
    r"|((?:system ?prompt|developer ?message|root ?instruction)[\s\S]{0,30})"
)

# Allow-list of benign, common adjectival/contextual uses that should NOT be
# defused (avoids false positives on legit preferences like "ignore whitespace").
_DIRECTIVE_ALLOWLIST_RE = re.compile(
    r"(?i)(ignore (?:the |a )?(?:tab|space|whitespace|case|formatting|trailing|leading))"
    r"|(when (?:you |the model |it )?ignore)"
)

_MAX_SCRUBBED_CHARS = 4000  # safety clamp; a single claim line should never exceed this


def scrub_recalled_claim_text(text: str) -> str:
    """Neutralize prompt-injection syntax in a recalled-claim fragment.

    Returns the scrubbed string. On any error, returns the *original* text
    unchanged (fail open — never break recall, never silently mangle memory).
    """
    if not text or not isinstance(text, str):
        return text
    if len(text) > _MAX_SCRUBBED_CHARS:
        # Truncate before regex work to bound CPU; truncation here only caps
        # pathological inputs — the framing layer still marks it as recalled.
        text = text[:_MAX_SCRUBBED_CHARS]
    try:
        # 1) strip invisible / control whitespace (no semantic content).
        cleaned = _INVISIBLE_RE.sub("", text)
        cleaned = _CONTROL_WS_RE.sub(" ", cleaned)
        # 2) defuse fenced-instruction / block-escape markers.
        cleaned = _BLOCK_ESCAPE_RE.sub("[BLOCKED-TAG]", cleaned)
        cleaned = _FENCE_RE.sub("[FENCE]", cleaned)
        # 3) neutralize directive phrases (prefix, never delete).
        if _DIRECTIVE_ALLOWLIST_RE.search(cleaned):
            return cleaned  # benign usage — leave untouched
        cleaned = _DIRECTIVE_PREFIX_RE.sub("[RECALLED-CLAIM-SUSPECTED] \\1\\2\\3\\4\\5", cleaned)
        return cleaned
    except Exception:  # pragma: no cover - defensive
        logger.exception("scrub_recalled_claim_text: unexpected failure; passing through")
        return text


async def recall_for_chat(
    db: AsyncSession,
    *,
    user_id: int,
    workspace_id: str,
    query: str,
    top_k: int = CHAT_RECALL_TOP_K,
    min_confidence: float = CHAT_RECALL_MIN_CONFIDENCE,
) -> list[PersonalMemoryClaim]:
    """Recall relevant personal-memory claims for a chat message and
    apply the T33 defensive filter.

    The underlying ``PersonalMemoryService.recall`` already filters by
    ``(user_id, workspace_id, NOT deleted, NOT expired, confidence ≥
    min_confidence, scope ∈ scopes)`` and updates ``last_used_at``.
    This wrapper:

    1. Restricts scopes to ``["personal", "workspace", "program"]``
       (the ``"private"`` scope is filtered out post-recall; restricting
       at the SQL layer is also fine but the post-filter is a defensive
       belt-and-suspenders).
    2. Drops any row whose ``sensitivity`` is in ``_EXCLUDED_SENSITIVITIES``.
    3. Drops any row whose ``scope`` is in ``_EXCLUDED_SCOPES``.

    Returns the filtered, top-``top_k`` list. Empty list is normal
    (no claims matched, or all were filtered out).

    No exceptions are raised on recall failure — the caller (the
    streaming function) wraps this in try/except so a recall outage
    never breaks the chat.
    """
    service = PersonalMemoryService(db)
    raw_claims, _total = await service.recall(
        user_id=user_id,
        workspace_id=workspace_id,
        query=query,
        scopes=["personal", "workspace", "program"],
        top_k=top_k,
        min_confidence=min_confidence,
    )
    safe_claims: list[PersonalMemoryClaim] = []
    for claim in raw_claims:
        if claim.sensitivity in _EXCLUDED_SENSITIVITIES:
            logger.info(
                "memory_citation: filtered sensitive claim id=%s sensitivity=%s",
                claim.id,
                claim.sensitivity,
            )
            continue
        if claim.scope in _EXCLUDED_SCOPES:
            logger.info(
                "memory_citation: filtered private-scope claim id=%s scope=%s",
                claim.id,
                claim.scope,
            )
            continue
        safe_claims.append(claim)
    if len(safe_claims) < len(raw_claims):
        logger.info(
            "memory_citation: defensive filter dropped %d of %d recalled claims",
            len(raw_claims) - len(safe_claims),
            len(raw_claims),
        )
    return safe_claims


def format_memory_block(claims: list[PersonalMemoryClaim]) -> str:
    """Build the prompt-injection text block for the LLM.

    The block is a single string. The caller inserts it as a ``"system"``
    message after the existing system prompt. The block is intentionally
    terse and stable-format so the LLM can pattern-match it cheaply.

    Format::

        PERSONAL MEMORY CONTEXT
        The following facts have been recalled for this user. Use them
        only if they are directly relevant to the user's question. Do not
        reference them by id in the answer; the chat UI renders the
        citation chip separately based on the metadata emitted over SSE.

        - Flowmanner uses → App Router → {"framework": "Next.js"} (confidence: 0.85)
        - User prefers → dark mode → {"value": "true"} (confidence: 0.78)

    Empty claim list → empty string (caller should skip injection).
    """
    if not claims:
        return ""
    lines: list[str] = [
        "PERSONAL MEMORY CONTEXT",
        "The following facts have been recalled for this user. Use them",
        "only if they are directly relevant to the user's question. Do not",
        "reference them by id in the answer; the chat UI renders the",
        "citation chip separately based on the metadata emitted over SSE.",
        "",
    ]
    for claim in claims:
        # GOV-1.3b read-side scrubber: recalled claims are attacker-
        # influenced data (written by the reviewer / earlier runs). Strip
        # invisible Unicode, control whitespace, fenced-instruction markers,
        # and neutralize injection trigger phrases before the block reaches
        # the live LLM. This is harm reduction, NOT neutralization; the
        # <memory-context> framing + provenance gate remain the real controls.
        subject = scrub_recalled_claim_text(getattr(claim, "subject", "") or "")
        predicate = scrub_recalled_claim_text(getattr(claim, "predicate", "") or "")
        try:
            object_str = json.dumps(claim.object, sort_keys=True, default=str)
        except (TypeError, ValueError):
            object_str = str(claim.object)
        object_str = scrub_recalled_claim_text(object_str)
        lines.append(f"- {subject} → {predicate} → {object_str} (confidence: {claim.confidence:.2f})")
    return "\n".join(lines)


def short_claim_id(claim: PersonalMemoryClaim) -> str:
    """Format the short-UUID citation label per plan §13 M2.

    Locked format: ``c-<first-8-hex-chars>`` (lowercase, no dashes).
    Example: claim UUID ``550e8400-e29b-41d4-a716-446655440000`` →
    ``c-550e8400``.
    """
    raw = str(claim.id).replace("-", "")
    return f"c-{raw[:8]}"


def _safe_object_str(obj: object) -> str:
    """Render a claim's ``object`` (JSON-shaped) as a compact string for
    the LLM-injected memory block and the SSE citation event.

    Uses ``sort_keys=True`` for stable ordering and ``default=str`` so
    non-JSON values (e.g. datetimes) degrade to a printable string
    rather than raising ``TypeError``.
    """
    try:
        return json.dumps(obj, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(obj)


def format_citation_label(claim: PersonalMemoryClaim) -> str:
    """Build the locked bracket-wrapped citation label for a claim.

    Per plan §7 the format is::

        [memory: c-14, mission #482, conf 0.85]

    Degrades gracefully when ``mission_number`` is unavailable (the
    claim is not sourced from a mission)::

        [memory: c-14, conf 0.85]

    The short-UUID prefix (``c-<8hex>``) always comes from
    :func:`short_claim_id` so the label is a drop-in for the chat chip.
    """
    short = short_claim_id(claim)
    mission_number = getattr(claim, "mission_number", None)
    confidence = float(claim.confidence)
    if mission_number is not None:
        return f"[memory: {short}, mission #{int(mission_number)}, conf {confidence:.2f}]"
    return f"[memory: {short}, conf {confidence:.2f}]"


def build_citation_event(
    claim: PersonalMemoryClaim,
    *,
    message_id: str,
) -> dict[str, Any]:
    """Build one ``memory_citation`` SSE event payload (plan §4).

    Emitted AFTER the assistant message is persisted so ``message_id`` is
    known. The frontend renders a :class:`MemoryCitationChip` per event
    using the ``label`` field as the chip's primary text and the
    individual ``subject`` / ``predicate`` / ``object`` fields for the
    rich tooltip / WhyDrawer.

    Stage 2 of T33. Stage 1 emits only ``memory_recall_used`` (which
    carries the same short-UUID label so the frontend can pre-stage
    metadata before the richer ``memory_citation`` arrives).

    ``mission_id`` and ``mission_number`` are passed through if present
    on the claim. Today the model has no denormalized ``mission_number``
    column, so the label degrades to ``[memory: c-14, conf 0.85]``;
    T33.1 will wire the mission join to add the ``#482`` suffix.
    """
    label = format_citation_label(claim)
    mission_id = getattr(claim, "mission_id", None) or (
        str(claim.source_id) if claim.source_type == "mission" and claim.source_id is not None else None
    )
    payload: dict[str, Any] = {
        "type": "memory_citation",
        "message_id": str(message_id),
        "citation_id": str(claim.id),
        "claim_id": str(claim.id),
        "label": label,
        "short_id": short_claim_id(claim),
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object": _safe_object_str(claim.object),
        "scope": claim.scope,
        "confidence": float(claim.confidence),
        "source": "pre_llm_context",
        # Honest recall-quality signal for the frontend (Phase 2c.4).
        # T19 ships substring recall; flips to "semantic" once embedding
        # recall lands (C3.3). Lets the UI show recall confidence truthfully.
        "recall_method": "substring",
    }
    if mission_id is not None:
        payload["mission_id"] = str(mission_id)
    mission_number = getattr(claim, "mission_number", None)
    if mission_number is not None:
        payload["mission_number"] = int(mission_number)
    if claim.expires_at is not None:
        payload["expires_at"] = cast(datetime, claim.expires_at).isoformat()
    return payload


def build_recall_used_event(
    claim: PersonalMemoryClaim,
    *,
    message_id: str,
) -> dict[str, Any]:
    """Build one ``memory_recall_used`` SSE event payload (plan §4).

    Emitted AFTER the assistant message is persisted so ``message_id`` is
    known. The frontend uses this to attach recall metadata to the
    assistant message; Stage 2 adds ``memory_citation`` events that
    carry the full bracket label and confidence for chip rendering.
    """
    return {
        "type": "memory_recall_used",
        "message_id": str(message_id),
        "claim_id": str(claim.id),
        "label": short_claim_id(claim),
        "subject": claim.subject,
        "predicate": claim.predicate,
        "scope": claim.scope,
        "confidence": float(claim.confidence),
        "source": "pre_llm_context",
        # Honest recall-quality signal for the frontend (Phase 2c.4).
        # T19 ships substring recall; flips to "semantic" once embedding
        # recall lands (C3.3). Lets the UI show recall confidence truthfully.
        "recall_method": "substring",
    }
