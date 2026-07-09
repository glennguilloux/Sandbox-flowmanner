"""PersonalMemoryExtractor — LLM candidate-claim extraction (D0-30, T20).

The extractor is a *thin LLM wrapper* that turns a chunk of text (a chat
turn, a mission transcript, a feedback note) into a list of candidate
``PersonalMemoryClaim`` records. It does NOT persist anything — the caller
(T21/T22 mission planner, conversation hook, etc.) decides which
candidates to dedupe and persist via ``PersonalMemoryService.create()``.

Design notes (see plan §D0-30):

* **LLM is the real path.** The system prompt instructs the model to
  return up to ``max_claims`` facts/preferences/observations about the
  user, each wrapped in a ```` ```json ... ``` ```` fence. A cheap
  model (default: ``"deepseek-chat"``) is used so each extraction
  costs ≈ $0.001.
* **Regex fallback is intentional simple coverage.** When the LLM is
  unavailable, rate-limited, times out, or returns garbage, the
  :class:`RegexPersonalMemoryExtractor` runs a small set of pattern
  matchers. The fallback is deliberately limited — the LLM is the
  real extractor, the regex is a graceful-degradation path.
* **Three source paths** are exposed by ``extract_with_fallback``:
  ``ExtractionSource.LLM`` (LLM returned ≥1 claim),
  ``ExtractionSource.EMPTY`` (LLM succeeded but returned nothing worth
  extracting), ``ExtractionSource.FALLBACK`` (LLM raised; the regex
  extractor produced the candidates).
* **No DB access.** This is a pure-logic service.
* **Late-binding router.** ``get_model_router`` is a callable (not an
  instance) so the extractor can be constructed before the
  ``ModelRouter`` singleton is initialised — matching the pattern
  used in ``MissionPlanner``, ``BrandVoice``, ``BudgetEnforcer``, etc.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


# ── Value sets (mirrored from the model layer; kept in lockstep) ────────
# These are the ONLY valid claim_type / scope values. Anything else is
# rejected at CandidateClaim construction time (defence in depth: the
# DB CHECK constraints are the second line of defence).

_VALID_CLAIM_TYPES: frozenset[str] = frozenset({"fact", "preference", "observation", "sensitive"})
_VALID_SCOPES: frozenset[str] = frozenset({"personal", "workspace", "program", "private"})


# ═══════════════════════════════════════════════════════════════════════════
# DTOs / enum
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CandidateClaim:
    """A single candidate claim produced by the extractor.

    This is a *data-transfer object*, NOT a SQLAlchemy model. It is
    passed to the caller's persistence layer (``PersonalMemoryService``)
    which copies the fields onto a ``PersonalMemoryClaim`` row.

    Frozen: the extractor never mutates a candidate in place.

    Fields:
        subject:   The "who/what" the claim is about. Usually ``"user"``
                   for personal facts; the team / project name for
                   workspace-scoped claims.
        predicate: A short verb-like label (e.g. ``"prefers"``,
                   ``"name"``, ``"uses"``).
        object:    A JSONB-shaped dict describing the value. Always a
                   dict (not a bare string) to leave room for
                   ``{value, context, tags, ...}`` enrichment later.
        claim_type: One of ``"fact"`` / ``"preference"`` /
                    ``"observation"`` / ``"sensitive"``.
        scope:     One of ``"personal"`` / ``"workspace"`` /
                   ``"program"`` / ``"private"``.
        confidence: A float in ``[0.0, 1.0]`` indicating the
                    extractor's self-reported confidence.
        rationale: Optional one-sentence explanation of why the
                   extractor produced this claim. Helpful for the
                   Memory Inspector UI and audit log.
        source_type: Provenance of the claim. Defaults to
                     ``"conversation"`` (inferred by the chat extractor).
                     ``"user_explicit"`` marks claims the user authored
                     directly (e.g. an explicit "remember this" command)
                     and is the only source trusted enough to bypass the
                     human-approval gate (GOV-1.2). Externally-derived
                     sources (``mission`` / ``program_learning``) are
                     routed to approval regardless of confidence.
                     Carried through to ``_maybe_extract_memory_claims``
                     so the GOV-1.5 confidence gate can scope itself to
                     the trusted direct-write path.
    """

    subject: str
    predicate: str
    object: dict[str, Any]
    claim_type: str
    scope: str
    confidence: float
    rationale: str | None = None
    source_type: str = "conversation"

    def __post_init__(self) -> None:
        if self.claim_type not in _VALID_CLAIM_TYPES:
            raise ValueError(f"invalid claim_type={self.claim_type!r}; must be one of {sorted(_VALID_CLAIM_TYPES)}")
        if self.scope not in _VALID_SCOPES:
            raise ValueError(f"invalid scope={self.scope!r}; must be one of {sorted(_VALID_SCOPES)}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0]; got {self.confidence!r}")
        if not isinstance(self.object, dict):
            raise ValueError(f"object must be a dict (JSONB-shaped); got {type(self.object).__name__}")


class ExtractionSource(str, Enum):
    """Provenance tag returned by ``extract_with_fallback``.

    * ``LLM``      — the LLM returned at least one valid claim.
    * ``EMPTY``    — the LLM succeeded but reported "nothing worth
                     extracting" (or the parser found an empty array).
    * ``FALLBACK`` — the LLM raised; the regex extractor produced
                     whatever was salvageable.
    """

    LLM = "llm"
    FALLBACK = "fallback"
    EMPTY = "empty"


# ═══════════════════════════════════════════════════════════════════════════
# Regex fallback
# ═══════════════════════════════════════════════════════════════════════════


# PII patterns (intentionally broad — false positives are preferable to
# missed PII for the personal-memory MVP).
_PII_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_PII_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?)?\d{3}[ .-]?\d{3,4}[ .-]?\d{0,4}\b")
_PII_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

# Preference patterns.
_PREF_PREFER_RE = re.compile(r"\bI\s+prefer\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)", re.IGNORECASE)
_PREF_LIKE_RE = re.compile(r"\bI\s+(?:like|love)\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)", re.IGNORECASE)
_PREF_DISLIKE_RE = re.compile(
    r"\bI\s+(?:don['']t\s+(?:like|love)|dislike|hate)\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)",
    re.IGNORECASE,
)
_PREF_AVOID_RE = re.compile(r"\bI\s+avoid\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)", re.IGNORECASE)

# Identity patterns.
_ID_NAME_RE = re.compile(r"\bMy\s+name\s+is\s+(?P<value>[A-Z][\w'-]+)", re.IGNORECASE)
_ID_AM_RE = re.compile(
    r"\b(?:I['']m|I\s+am)\s+(?:a\s+)?(?P<value>[A-Za-z][\w\s/-]{1,40}?)(?:\s*[.;,]|$)",
    re.IGNORECASE,
)

# Project / workspace facts.
_PROJ_WEUSE_RE = re.compile(r"\bWe\s+use\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)", re.IGNORECASE)
_PROJ_WEREUSING_RE = re.compile(r"\bWe['']re\s+using\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)", re.IGNORECASE)
_PROJ_OURPROJECT_RE = re.compile(
    r"\bOur\s+project(?:\s+is)?\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)",
    re.IGNORECASE,
)

# Imperative preference statements.
_IMP_DONT_RE = re.compile(r"\bDon['']t\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)", re.IGNORECASE)
_IMP_NEVER_RE = re.compile(r"\bNever\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)", re.IGNORECASE)
_IMP_ALWAYS_RE = re.compile(r"\bAlways\s+(?P<value>[^.;,]+?)(?:\s*[.;,]|$)", re.IGNORECASE)


def _claim(
    *,
    subject: str,
    predicate: str,
    value: str,
    claim_type: str,
    scope: str,
    confidence: float,
    rationale: str | None = None,
    extra: dict[str, Any] | None = None,
) -> CandidateClaim:
    """Build a ``CandidateClaim`` from a captured string value."""
    obj: dict[str, Any] = {"value": value.strip()}
    if extra:
        obj.update(extra)
    return CandidateClaim(
        subject=subject,
        predicate=predicate,
        object=obj,
        claim_type=claim_type,
        scope=scope,
        confidence=confidence,
        rationale=rationale,
    )


class RegexPersonalMemoryExtractor:
    """Deterministic, no-LLM claim extractor.

    Pattern coverage (each pattern contributes at most one claim per
    input; the order is the priority when the same value would match
    multiple patterns — first match wins):

    1. PII (email / phone / credit-card)        → sensitive, private
    2. Identity facts (``My name is`` / ``I am`` / ``I'm``) → fact, personal
    3. Project facts (``We use`` / ``We're using`` / ``Our project``) → fact, workspace
    4. Preference patterns (``I prefer/like/love/dislike/avoid``) → preference, personal
    5. Imperative patterns (``Don't`` / ``Never`` / ``Always``) → preference, personal

    The regex coverage is intentionally limited: the LLM is the real
    extractor. The fallback is for outage / rate-limit / garbage cases.
    """

    # Each entry: (compiled regex, predicate, claim_type, scope, confidence)
    _PREF_PATTERNS = (
        (_PREF_PREFER_RE, "prefers", "preference", "personal", 0.85, "user said 'I prefer X'"),
        (_PREF_LIKE_RE, "likes", "preference", "personal", 0.8, "user said 'I like X'"),
        (_PREF_DISLIKE_RE, "dislikes", "preference", "personal", 0.8, "user said 'I don't like X'"),
        (_PREF_AVOID_RE, "avoids", "preference", "personal", 0.75, "user said 'I avoid X'"),
    )

    _IMPERATIVE_PATTERNS = (
        (_IMP_DONT_RE, "do_not", "preference", "personal", 0.65, "imperative 'Don't X'"),
        (_IMP_NEVER_RE, "never", "preference", "personal", 0.6, "imperative 'Never X'"),
        (_IMP_ALWAYS_RE, "always", "preference", "personal", 0.6, "imperative 'Always X'"),
    )

    def extract(self, text: str) -> list[CandidateClaim]:
        """Return the list of candidate claims detected in *text*.

        Order: PII first (highest sensitivity), then identity, then
        project facts, then preferences, then imperatives. The
        ``CandidateClaim`` instances are frozen, so the caller can
        safely share or sort them.
        """
        if not text or not text.strip():
            return []

        claims: list[CandidateClaim] = []

        # 1) PII — sensitive / private, low confidence.
        for regex, kind in (
            (_PII_EMAIL_RE, "email"),
            (_PII_PHONE_RE, "phone"),
            (_PII_CARD_RE, "credit_card"),
        ):
            m = regex.search(text)
            if m:
                claims.append(
                    _claim(
                        subject="user",
                        predicate=f"has_{kind}",
                        value=m.group(0),
                        claim_type="sensitive",
                        scope="private",
                        confidence=0.5,
                        rationale=f"PII pattern matched: {kind}",
                        extra={"pii_kind": kind},
                    )
                )

        # 2) Identity — fact / personal, high confidence.
        m = _ID_NAME_RE.search(text)
        if m:
            claims.append(
                _claim(
                    subject="user",
                    predicate="name",
                    value=m.group("value"),
                    claim_type="fact",
                    scope="personal",
                    confidence=0.9,
                    rationale="user stated 'My name is X'",
                )
            )

        m = _ID_AM_RE.search(text)
        if m:
            claims.append(
                _claim(
                    subject="user",
                    predicate="is",
                    value=m.group("value"),
                    claim_type="fact",
                    scope="personal",
                    confidence=0.85,
                    rationale="user stated 'I am X' / 'I'm X'",
                )
            )

        # 3) Project facts — fact / workspace.
        m = _PROJ_WEUSE_RE.search(text)
        if m:
            claims.append(
                _claim(
                    subject="team",
                    predicate="uses",
                    value=m.group("value"),
                    claim_type="fact",
                    scope="workspace",
                    confidence=0.8,
                    rationale="user stated 'We use X'",
                )
            )
        else:
            m = _PROJ_WEREUSING_RE.search(text)
            if m:
                claims.append(
                    _claim(
                        subject="team",
                        predicate="using",
                        value=m.group("value"),
                        claim_type="fact",
                        scope="workspace",
                        confidence=0.8,
                        rationale="user stated 'We're using X'",
                    )
                )
            else:
                m = _PROJ_OURPROJECT_RE.search(text)
                if m:
                    claims.append(
                        _claim(
                            subject="team",
                            predicate="project",
                            value=m.group("value"),
                            claim_type="fact",
                            scope="workspace",
                            confidence=0.75,
                            rationale="user stated 'Our project X'",
                        )
                    )

        # 4) Preferences — preference / personal.
        for regex, predicate, ct, scope, conf, rationale in self._PREF_PATTERNS:
            m = regex.search(text)
            if m:
                claims.append(
                    _claim(
                        subject="user",
                        predicate=predicate,
                        value=m.group("value"),
                        claim_type=ct,
                        scope=scope,
                        confidence=conf,
                        rationale=rationale,
                    )
                )
                break  # one preference claim per input

        # 5) Imperatives — preference / personal, medium confidence.
        for regex, predicate, ct, scope, conf, rationale in self._IMPERATIVE_PATTERNS:
            m = regex.search(text)
            if m:
                claims.append(
                    _claim(
                        subject="user",
                        predicate=predicate,
                        value=m.group("value"),
                        claim_type=ct,
                        scope=scope,
                        confidence=conf,
                        rationale=rationale,
                    )
                )
                break  # one imperative claim per input

        return claims


# ═══════════════════════════════════════════════════════════════════════════
# LLM extractor
# ═══════════════════════════════════════════════════════════════════════════


_DEFAULT_MODEL_NAME = "deepseek-v4-flash"


# Matches a JSON array inside a ```json ... ``` fence.
_FENCED_JSON_RE = re.compile(r"```json\s*(\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)
# Matches a JSON array anywhere in raw text (greedy; the JSON must be
# syntactically valid for json.loads to succeed).
_RAW_JSON_RE = re.compile(r"\[.*\]", re.DOTALL)


class PersonalMemoryExtractor:
    """Async LLM candidate-claim extractor with a regex fallback.

    The extractor is the *feed* of the personal-memory MVP. The
    *caller* (mission planner, conversation hook, etc.) decides which
    candidates to dedupe against existing claims and persist via
    ``PersonalMemoryService.create()``.

    Args:
        get_model_router: A late-binding callable returning a
            ``ModelRouter`` instance (or ``None``). Called lazily on
            each ``extract()`` so the singleton can be initialised
            after the extractor is constructed.
        model_name: The cheap model to use for extraction. Defaults to
            ``"deepseek-chat"`` (a placeholder for the cheap option —
            the project's actual setting lives in
            ``settings.LLM_EXTRACTION_MODEL`` once T21 wires it up).
        fallback_extractor: The regex extractor used when the LLM
            raises. Defaults to a fresh
            :class:`RegexPersonalMemoryExtractor`.
    """

    def __init__(
        self,
        *,
        get_model_router: Callable[[], Any] | None = None,
        model_name: str | None = None,
        fallback_extractor: RegexPersonalMemoryExtractor | None = None,
    ) -> None:
        self._get_model_router = get_model_router or (lambda: None)
        self.model_name = model_name or _DEFAULT_MODEL_NAME
        self.fallback_extractor = (
            fallback_extractor if fallback_extractor is not None else RegexPersonalMemoryExtractor()
        )

    # ── Public API ─────────────────────────────────────────────────────

    async def extract(
        self,
        *,
        user_id: int,
        workspace_id: str,
        text: str,
        context: str | None = None,
        max_claims: int = 5,
    ) -> list[CandidateClaim]:
        """Run LLM extraction only.

        Returns ``[]`` on any failure (LLM raises, router is ``None``,
        response is empty/unparseable). The caller is expected to use
        ``extract_with_fallback`` if it needs the regex fallback.
        """
        router = self._get_model_router()
        if router is None:
            logger.debug("personal_memory.extract: no model_router available; returning []")
            return []

        messages = self._build_messages(text=text, context=context, max_claims=max_claims)
        try:
            response = await router.route_request(
                messages=messages,
                model_preference=self.model_name,
                user_id=str(user_id),
                temperature=0.1,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.warning(
                "personal_memory.extract: LLM call failed user_id=%s workspace_id=%s error=%s",
                user_id,
                workspace_id,
                exc,
            )
            return []

        # The ModelRouter's dict shape varies across code paths
        # (sometimes ``response``, sometimes ``content``); accept both.
        content = response.get("response") or response.get("content") or ""
        if not content:
            return []

        raw_items = self._parse_llm_response(content)
        return self._items_to_claims(raw_items, max_claims=max_claims)

    async def extract_with_fallback(
        self,
        *,
        user_id: int,
        workspace_id: str,
        text: str,
        context: str | None = None,
        max_claims: int = 5,
    ) -> tuple[list[CandidateClaim], ExtractionSource]:
        """Run LLM extraction; on LLM failure, fall back to regex.

        Returns ``(claims, source)`` where ``source`` is one of:

        * :attr:`ExtractionSource.LLM` — the LLM returned ≥1 valid
          claim.
        * :attr:`ExtractionSource.EMPTY` — the LLM succeeded but
          produced no claims (empty list, or "nothing to extract"
          response).
        * :attr:`ExtractionSource.FALLBACK` — the LLM raised; the
          regex extractor produced whatever was salvageable.
        """
        router = self._get_model_router()
        if router is None:
            # No router at all: just use the fallback.
            claims = self.fallback_extractor.extract(text)
            return claims, (ExtractionSource.FALLBACK if claims else ExtractionSource.EMPTY)

        messages = self._build_messages(text=text, context=context, max_claims=max_claims)
        try:
            response = await router.route_request(
                messages=messages,
                model_preference=self.model_name,
                user_id=str(user_id),
                temperature=0.1,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.warning(
                "personal_memory.extract_with_fallback: LLM call failed "
                "user_id=%s workspace_id=%s error=%s; using regex fallback",
                user_id,
                workspace_id,
                exc,
            )
            claims = self.fallback_extractor.extract(text)
            return claims, (ExtractionSource.FALLBACK if claims else ExtractionSource.EMPTY)

        content = response.get("response") or response.get("content") or ""
        if not content:
            return [], ExtractionSource.EMPTY

        raw_items = self._parse_llm_response(content)
        if not raw_items:
            return [], ExtractionSource.EMPTY

        claims = self._items_to_claims(raw_items, max_claims=max_claims)
        if not claims:
            return [], ExtractionSource.EMPTY
        return claims, ExtractionSource.LLM

    # ── Internal: prompt construction ──────────────────────────────────

    def _build_system_prompt(self, *, max_claims: int) -> str:
        """Build the system prompt sent to the LLM.

        Contract (also asserted by the test suite):

        * Mentions `````json`` (the JSON fence the LLM must wrap its
          output in).
        * Mentions the literal token ``max_claims`` (so the LLM knows
          to limit its output).
        * Mentions the four scope names: ``personal``, ``workspace``,
          ``program``, ``private``.
        * Renders the ``max_claims`` value as a digit.
        """
        # The prompt is a STRING LITERAL — logger rules don't apply.
        # We assemble it via .format() to keep the magic numbers in
        # one place. (No f-strings here per the project convention.)
        return _SYSTEM_PROMPT_TEMPLATE.format(max_claims=max_claims)

    def _build_user_prompt(self, *, text: str, context: str | None, max_claims: int) -> str:
        """Build the user-role prompt (the chunk of text to extract from)."""
        if context:
            return (
                f"Context: {context}\n\n"
                f"Extract up to {max_claims} personal-memory claims from "
                f"the following text:\n\n{text}"
            )
        return f"Extract up to {max_claims} personal-memory claims from the following text:\n\n{text}"

    def _build_messages(self, *, text: str, context: str | None, max_claims: int) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": self._build_system_prompt(max_claims=max_claims),
            },
            {
                "role": "user",
                "content": self._build_user_prompt(text=text, context=context, max_claims=max_claims),
            },
        ]

    # ── Internal: response parsing ─────────────────────────────────────

    def _parse_llm_response(self, content: str) -> list[dict[str, Any]]:
        """Parse the LLM response into a list of raw claim dicts.

        Tries, in order:

        1. ```` ```json ... ``` ```` fenced content.
        2. The first ``[...]`` JSON array anywhere in the content.
        3. ``[]`` (silent — never raises).
        """
        if not content or not content.strip():
            return []

        # 1) Fenced JSON.
        m = _FENCED_JSON_RE.search(content)
        if m:
            payload = m.group(1)
            try:
                parsed = json.loads(payload)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
            if isinstance(parsed, dict):
                return [parsed]

        # 2) Raw JSON array anywhere in the content.
        m = _RAW_JSON_RE.search(content)
        if m:
            payload = m.group(0)
            try:
                parsed = json.loads(payload)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
            if isinstance(parsed, dict):
                return [parsed]

        # 3) Garbage / unparseable → return [], do NOT raise.
        return []

    # ── Internal: DTO conversion ───────────────────────────────────────

    def _items_to_claims(self, raw_items: list[dict[str, Any]], *, max_claims: int) -> list[CandidateClaim]:
        """Convert raw LLM-output dicts into validated ``CandidateClaim``s.

        Truncates to ``max_claims`` (in case the LLM returns more).
        Skips items that fail ``CandidateClaim`` validation (rather
        than blowing up the whole extraction).
        """
        claims: list[CandidateClaim] = []
        for item in raw_items[:max_claims]:
            try:
                claims.append(self._item_to_claim(item))
            except (ValueError, TypeError) as exc:
                logger.debug(
                    "personal_memory.extract: skipping invalid LLM item error=%s item=%s",
                    exc,
                    item,
                )
                continue
        return claims

    @staticmethod
    def _item_to_claim(item: dict[str, Any]) -> CandidateClaim:
        """Map a raw LLM-output dict onto the dataclass shape.

        The LLM is told to return a dict with these keys:
            subject, predicate, object, claim_type, scope, confidence,
            [rationale]

        We tolerate minor shape variation (object as a string, missing
        rationale) by normalising into the JSONB-dict shape the model
        requires.
        """
        subject = str(item.get("subject") or "user")
        predicate = str(item.get("predicate") or "observed")

        raw_object = item.get("object")
        if isinstance(raw_object, dict):
            obj: dict[str, Any] = dict(raw_object)
        elif raw_object is None:
            obj = {}
        else:
            obj = {"value": str(raw_object)}

        claim_type = str(item.get("claim_type") or "observation")
        scope = str(item.get("scope") or "personal")

        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        # Clamp to [0.0, 1.0].
        confidence = max(0.0, min(1.0, confidence))

        rationale_raw = item.get("rationale")
        rationale = str(rationale_raw) if rationale_raw is not None else None

        return CandidateClaim(
            subject=subject,
            predicate=predicate,
            object=obj,
            claim_type=claim_type,
            scope=scope,
            confidence=confidence,
            rationale=rationale,
        )


# ═══════════════════════════════════════════════════════════════════════════
# System prompt template (module-level so tests can introspect it)
# ═══════════════════════════════════════════════════════════════════════════


_SYSTEM_PROMPT_TEMPLATE = """\
You are a personal-memory extractor for an AI assistant.

Your job: read the user's text and extract discrete, durable facts, \
preferences, observations, and sensitive items that would help the \
assistant serve the user better in future conversations.

Constraints:
- Extract AT MOST {max_claims} claims. (The caller has set the parameter
  `max_claims = {max_claims}` — respect that limit strictly.)
- For each claim, output a JSON object with these exact fields:
    - "subject"   (string) — the entity the claim is about
                         (usually "user" for personal facts).
    - "predicate" (string) — a short verb-like label (e.g. "prefers",
                         "name", "uses").
    - "object"    (string OR small dict) — the value of the claim. \
Prefer a dict of the form {{"value": "<the value>", "context": "..."}} \
so it can be enriched later.
    - "claim_type" (one of "fact", "preference", "observation", \
"sensitive").
    - "scope"      (one of "personal", "workspace", "program", \
"private") — where this claim is visible.
        - "personal"  = user-only
        - "workspace" = shared with workspace members
        - "program"   = shared with a mission program's participants
        - "private"   = encrypted, only readable by the owner (use \
for PII)
    - "confidence" (float in [0.0, 1.0]) — your self-reported \
confidence in the claim.
    - "rationale"  (optional string) — one-sentence reason you \
extracted it.

Output format:
- Wrap the JSON array in a ```json ... ``` fence.
- If nothing in the text is worth extracting, return [] inside the \
fence.
- Do NOT add commentary outside the fence.

Examples:

User: "I prefer terse updates and my name is Alice."
Output:
```json
[
  {{"subject": "user", "predicate": "prefers", "object": {{"value": "terse updates"}}, "claim_type": "preference", "scope": "personal", "confidence": 0.9, "rationale": "explicit user preference"}},
  {{"subject": "user", "predicate": "name", "object": {{"value": "Alice"}}, "claim_type": "fact", "scope": "personal", "confidence": 0.95, "rationale": "user stated their name"}}
]
```

User: "We use Qdrant. Reach me at alice@example.com."
Output:
```json
[
  {{"subject": "team", "predicate": "uses", "object": {{"value": "Qdrant"}}, "claim_type": "fact", "scope": "workspace", "confidence": 0.85, "rationale": "user stated team's tool"}},
  {{"subject": "user", "predicate": "has_email", "object": {{"value": "alice@example.com"}}, "claim_type": "sensitive", "scope": "private", "confidence": 0.7, "rationale": "PII detected"}}
]
```
"""
