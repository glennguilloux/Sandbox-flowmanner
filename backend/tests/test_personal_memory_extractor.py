"""TDD tests for PersonalMemoryExtractor (D0-30, T20).

Covers the LLM-based candidate-claim extractor + the deterministic
regex fallback. This is a pure-logic service — no DB access.

Test clusters:

(A) Pure-Python — no DB, no LLM
    * ``CandidateClaim`` frozen dataclass + value validation
    * ``ExtractionSource`` enum (LLM / FALLBACK / EMPTY)
    * ``RegexPersonalMemoryExtractor`` patterns:
        - "I prefer X"  → preference / personal
        - "My name is X" → fact / personal / high confidence
        - "We use X" → fact / workspace
        - Non-personal text → empty
        - PII patterns → sensitive / private
    * ``PersonalMemoryExtractor.extract_with_fallback`` path selection:
        - LLM success → LLM source
        - LLM raises → FALLBACK source
        - LLM returns [] → EMPTY source
    * LLM-response JSON parser:
        - Fenced ````json...```` block
        - Raw JSON array
        - Garbage → returns ``[]``, does not raise
    * System prompt mentions ``max_claims``, JSON fence, and the four
      scope names by name.

(B) Mocked-LLM (AsyncMock for the model router)
    * ``extract()`` invokes the model router with the right messages
    * ``extract()`` uses the cheap default model name
    * ``extract()`` returns parsed ``CandidateClaim`` instances on a
      valid LLM response
    * ``extract()`` returns ``[]`` on an empty LLM response
    * ``extract_with_fallback`` returns FALLBACK results when the LLM
      raises

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_personal_memory_extractor.py -v
"""

from __future__ import annotations

import os
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Set DATABASE_URL BEFORE importing app modules that need it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)


# ═══════════════════════════════════════════════════════════════════════════
# (A.1) CandidateClaim dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestCandidateClaimImmutability:
    """The CandidateClaim dataclass MUST be frozen (immutable)."""

    def test_is_frozen_dataclass(self) -> None:
        # frozen=True is the safest signal — assigning to a field must raise.
        import dataclasses

        from app.services.personal_memory_extractor import CandidateClaim

        assert dataclasses.is_dataclass(CandidateClaim)
        assert CandidateClaim.__dataclass_params__.frozen is True

    def test_assignment_raises_frozen_error(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        c = CandidateClaim(
            subject="user",
            predicate="prefers",
            object={"value": "dark_mode"},
            claim_type="preference",
            scope="personal",
            confidence=0.8,
        )
        with pytest.raises((AttributeError, Exception)):
            # Frozen dataclass: __setattr__ raises FrozenInstanceError.
            c.subject = "other"  # type: ignore[misc]

    def test_field_values_round_trip(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        c = CandidateClaim(
            subject="user",
            predicate="name",
            object={"value": "Alice"},
            claim_type="fact",
            scope="personal",
            confidence=0.9,
            rationale="user said so",
        )
        assert c.subject == "user"
        assert c.predicate == "name"
        assert c.object == {"value": "Alice"}
        assert c.claim_type == "fact"
        assert c.scope == "personal"
        assert c.confidence == 0.9
        assert c.rationale == "user said so"


class TestCandidateClaimValidation:
    """``__post_init__`` MUST reject invalid claim_type / scope / confidence."""

    def test_rejects_invalid_claim_type(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        with pytest.raises(ValueError, match="claim_type"):
            CandidateClaim(
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="made_up_value",
                scope="personal",
                confidence=0.5,
            )

    def test_rejects_invalid_scope(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        with pytest.raises(ValueError, match="scope"):
            CandidateClaim(
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="preference",
                scope="made_up_value",
                confidence=0.5,
            )

    def test_rejects_confidence_above_one(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        with pytest.raises(ValueError, match="confidence"):
            CandidateClaim(
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="preference",
                scope="personal",
                confidence=1.5,
            )

    def test_rejects_confidence_below_zero(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        with pytest.raises(ValueError, match="confidence"):
            CandidateClaim(
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="preference",
                scope="personal",
                confidence=-0.1,
            )

    def test_accepts_all_four_claim_types(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        for ct in ("fact", "preference", "observation", "sensitive"):
            c = CandidateClaim(
                subject="user",
                predicate="p",
                object={"v": 1},
                claim_type=ct,
                scope="personal",
                confidence=0.5,
            )
            assert c.claim_type == ct

    def test_accepts_all_four_scopes(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        for sc in ("personal", "workspace", "program", "private"):
            c = CandidateClaim(
                subject="user",
                predicate="p",
                object={"v": 1},
                claim_type="fact",
                scope=sc,
                confidence=0.5,
            )
            assert c.scope == sc

    def test_rationale_is_optional(self) -> None:
        from app.services.personal_memory_extractor import CandidateClaim

        c = CandidateClaim(
            subject="user",
            predicate="p",
            object={"v": 1},
            claim_type="fact",
            scope="personal",
            confidence=0.5,
        )
        assert c.rationale is None


# ═══════════════════════════════════════════════════════════════════════════
# (A.2) ExtractionSource enum
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractionSourceEnum:
    """ExtractionSource must expose LLM / FALLBACK / EMPTY with the right
    string values, and be a ``str, Enum``."""

    def test_has_three_values(self) -> None:
        from app.services.personal_memory_extractor import ExtractionSource

        values = {member.value for member in ExtractionSource}
        assert values == {"llm", "fallback", "empty"}

    def test_member_string_values(self) -> None:
        from app.services.personal_memory_extractor import ExtractionSource

        assert ExtractionSource.LLM.value == "llm"
        assert ExtractionSource.FALLBACK.value == "fallback"
        assert ExtractionSource.EMPTY.value == "empty"

    def test_is_str_enum(self) -> None:
        from app.services.personal_memory_extractor import ExtractionSource

        # str, Enum: member is a str instance.
        assert isinstance(ExtractionSource.LLM, str)
        assert ExtractionSource.LLM == "llm"

    def test_no_transitions_leak(self) -> None:
        """str, Enum must not leak class-level dicts (per project pattern)."""
        from app.services.personal_memory_extractor import ExtractionSource

        # Iterate via __members__; only the 3 documented values.
        assert set(ExtractionSource.__members__) == {"LLM", "FALLBACK", "EMPTY"}


# ═══════════════════════════════════════════════════════════════════════════
# (A.3) RegexPersonalMemoryExtractor
# ═══════════════════════════════════════════════════════════════════════════


class TestRegexExtractorPreference:
    """I prefer / I like / I don't like / I avoid → preference / personal."""

    def test_i_prefer_x(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        r = RegexPersonalMemoryExtractor()
        claims = r.extract("I prefer terse updates")
        assert len(claims) == 1
        c = claims[0]
        assert c.claim_type == "preference"
        assert c.scope == "personal"
        assert c.confidence >= 0.7
        assert "terse updates" in (c.object.get("value") or "")

    def test_i_like_x(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("I like dark mode")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "preference"
        assert c.scope == "personal"

    def test_i_dont_like_x(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("I don't like popups")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "preference"
        assert c.scope == "personal"

    def test_i_avoid_x(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("I avoid meetings on Fridays")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "preference"
        assert c.scope == "personal"


class TestRegexExtractorIdentity:
    """My name is / I am / I'm → fact / personal / high confidence."""

    def test_my_name_is(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("My name is Alice")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "fact"
        assert c.scope == "personal"
        assert c.confidence >= 0.85
        # Predicate should be name-related
        assert "name" in c.predicate.lower()

    def test_i_am(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("I am a senior engineer")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "fact"
        assert c.scope == "personal"
        assert c.confidence >= 0.8

    def test_im_contraction(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("I'm a product manager")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "fact"
        assert c.scope == "personal"


class TestRegexExtractorProjectFacts:
    """We use / We're using / Our project → fact / workspace."""

    def test_we_use(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("We use Qdrant for vectors")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "fact"
        assert c.scope == "workspace"
        assert c.confidence >= 0.7

    def test_were_using(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("We're using FastAPI and Postgres")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "fact"
        assert c.scope == "workspace"

    def test_our_project(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("Our project is a coding assistant")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "fact"
        assert c.scope == "workspace"


class TestRegexExtractorImperatives:
    """Don't / Never / Always → preference / personal / medium confidence."""

    def test_dont_x(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("Don't use tabs, use spaces")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "preference"
        assert c.scope == "personal"

    def test_never_x(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("Never commit without tests")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "preference"
        assert c.scope == "personal"

    def test_always_x(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("Always run linters before pushing")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "preference"
        assert c.scope == "personal"


class TestRegexExtractorPII:
    """Email / phone / credit-card → sensitive / private / low confidence."""

    def test_email_flagged_sensitive_private(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("Reach me at alice@example.com please")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "sensitive"
        assert c.scope == "private"
        assert c.confidence <= 0.6

    def test_phone_flagged_sensitive_private(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("Call me at 555-123-4567 if urgent")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "sensitive"
        assert c.scope == "private"

    def test_credit_card_flagged_sensitive_private(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        # 16 digits, grouped as 4-4-4-4 (Luhn is NOT enforced — it's just a regex).
        claims = RegexPersonalMemoryExtractor().extract("My card is 4242 4242 4242 4242 btw")
        assert len(claims) >= 1
        c = claims[0]
        assert c.claim_type == "sensitive"
        assert c.scope == "private"


class TestRegexExtractorEmptyForNonPersonalText:
    """Non-personal text yields no claims."""

    def test_weather_phrase_yields_nothing(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("The weather is nice today")
        assert claims == []

    def test_pure_factual_text_yields_nothing(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        # No first-person, no PII, no imperative.
        claims = RegexPersonalMemoryExtractor().extract("Postgres 15.2 was released in February 2023.")
        assert claims == []

    def test_empty_string_yields_nothing(self) -> None:
        from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

        claims = RegexPersonalMemoryExtractor().extract("")
        assert claims == []


# ═══════════════════════════════════════════════════════════════════════════
# (A.4) JSON response parser
# ═══════════════════════════════════════════════════════════════════════════


class TestLLMResponseParser:
    """The internal ``_parse_llm_response`` must:

    * extract a JSON array from a ```` ```json ... ``` ```` fence
    * extract a JSON array from raw content (regex fallback)
    * return ``[]`` for non-parseable content (NEVER raise)
    """

    def _parser(self):
        from app.services.personal_memory_extractor import (
            PersonalMemoryExtractor,
        )

        # The parser is a method on the extractor; call it via a real
        # instance with a no-op router.
        return PersonalMemoryExtractor(get_model_router=lambda: None)._parse_llm_response

    def test_parses_fenced_json(self) -> None:
        parse = self._parser()
        body = (
            "```json\n"
            '[{"subject": "user", "predicate": "prefers", '
            '"object": {"value": "dark mode"}, '
            '"claim_type": "preference", "scope": "personal", '
            '"confidence": 0.8}]\n'
            "```"
        )
        result = parse(body)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["subject"] == "user"
        assert result[0]["claim_type"] == "preference"

    def test_parses_raw_json_array(self) -> None:
        parse = self._parser()
        body = (
            'Some preamble.\n[{"subject": "user", "predicate": "name", '
            '"object": {"value": "Alice"}, "claim_type": "fact", '
            '"scope": "personal", "confidence": 0.9}]'
        )
        result = parse(body)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["subject"] == "user"

    def test_garbage_returns_empty_list(self) -> None:
        parse = self._parser()
        # Garbage that contains no JSON array.
        assert parse("I am the LLM and here is my text response") == []
        assert parse("") == []
        assert parse("```\nnot json\n```") == []

    def test_invalid_json_returns_empty_list(self) -> None:
        parse = self._parser()
        # Looks like a JSON array but malformed.
        assert parse("[not valid json at all]") == []
        # Incomplete JSON.
        assert parse('[{"subject":') == []


# ═══════════════════════════════════════════════════════════════════════════
# (A.5) System prompt contract
# ═══════════════════════════════════════════════════════════════════════════


class TestSystemPrompt:
    """The system prompt sent to the LLM MUST mention:

    * the ```` ```json ```` fence
    * ``max_claims`` (or the literal token)
    * the four scope names: personal, workspace, program, private
    """

    def _extractor(self):
        from app.services.personal_memory_extractor import PersonalMemoryExtractor

        return PersonalMemoryExtractor(get_model_router=lambda: None)

    def test_prompt_mentions_json_fence(self) -> None:
        prompt = self._extractor()._build_system_prompt(max_claims=5)
        # The fence opener: ```json (with or without a space).
        assert "```json" in prompt

    def test_prompt_mentions_max_claims(self) -> None:
        prompt = self._extractor()._build_system_prompt(max_claims=5)
        assert "max_claims" in prompt

    def test_prompt_mentions_all_four_scopes(self) -> None:
        prompt = self._extractor()._build_system_prompt(max_claims=5)
        for scope in ("personal", "workspace", "program", "private"):
            assert scope in prompt, f"prompt must mention scope '{scope}'"

    def test_prompt_max_claims_value_rendered(self) -> None:
        """The literal ``max_claims=5`` should appear in the prompt (as a
        formatted directive, not just the token name)."""
        prompt = self._extractor()._build_system_prompt(max_claims=5)
        # The number 5 should be embedded in the prompt.
        assert "5" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# (A.6) extract_with_fallback path selection (pure-Python, mocked LLM)
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractWithFallbackPathSelection:
    """``extract_with_fallback`` must return the right ``ExtractionSource``
    for the three documented paths: LLM success / LLM failure / LLM []."""

    @pytest.mark.asyncio
    async def test_llm_success_returns_llm_source(self) -> None:
        from app.services.personal_memory_extractor import (
            ExtractionSource,
            PersonalMemoryExtractor,
        )

        # Mock router returning one valid claim.
        valid_response = (
            "```json\n"
            '[{"subject": "user", "predicate": "prefers", '
            '"object": {"value": "dark mode"}, '
            '"claim_type": "preference", "scope": "personal", '
            '"confidence": 0.8}]\n'
            "```"
        )
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": valid_response,
                "model": "deepseek-chat",
            }
        )

        extractor = PersonalMemoryExtractor(
            get_model_router=lambda: mock_router,
        )
        claims, source = await extractor.extract_with_fallback(
            user_id=1,
            workspace_id="ws-1",
            text="I prefer dark mode.",
        )
        assert source is ExtractionSource.LLM
        assert len(claims) == 1
        assert claims[0].claim_type == "preference"

    @pytest.mark.asyncio
    async def test_llm_raises_returns_fallback_source(self) -> None:
        from app.services.personal_memory_extractor import (
            ExtractionSource,
            PersonalMemoryExtractor,
            RegexPersonalMemoryExtractor,
        )

        # LLM raises an exception. The fallback regex extractor should
        # still find "I prefer dark mode" in the input text.
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(side_effect=RuntimeError("LLM provider is down"))

        extractor = PersonalMemoryExtractor(
            get_model_router=lambda: mock_router,
            fallback_extractor=RegexPersonalMemoryExtractor(),
        )
        claims, source = await extractor.extract_with_fallback(
            user_id=1,
            workspace_id="ws-1",
            text="I prefer dark mode",
        )
        assert source is ExtractionSource.FALLBACK
        assert len(claims) >= 1
        # The fallback regex would classify "I prefer X" as a preference.
        assert any(c.claim_type == "preference" for c in claims)

    @pytest.mark.asyncio
    async def test_llm_returns_empty_returns_empty_source(self) -> None:
        from app.services.personal_memory_extractor import (
            ExtractionSource,
            PersonalMemoryExtractor,
        )

        # LLM responds successfully but with an empty JSON array.
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "```json\n[]\n```",
                "model": "deepseek-chat",
            }
        )

        extractor = PersonalMemoryExtractor(
            get_model_router=lambda: mock_router,
        )
        claims, source = await extractor.extract_with_fallback(
            user_id=1,
            workspace_id="ws-1",
            text="The sky is blue today.",
        )
        assert source is ExtractionSource.EMPTY
        assert claims == []


# ═══════════════════════════════════════════════════════════════════════════
# (B) Mocked-LLM tests for extract()
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_router(response: dict[str, Any] | None = None, side_effect: Exception | None = None):
    """Helper: build a mock router with route_request as an AsyncMock."""
    router = MagicMock()
    if side_effect is not None:
        router.route_request = AsyncMock(side_effect=side_effect)
    else:
        router.route_request = AsyncMock(return_value=response or {})
    return router


class TestExtractCallsModelRouter:
    """``extract()`` MUST invoke the model router with messages + the cheap
    default model name."""

    @pytest.mark.asyncio
    async def test_extract_invokes_model_router(self) -> None:
        from app.services.personal_memory_extractor import PersonalMemoryExtractor

        mock_router = _make_mock_router(
            response={"success": True, "response": "```json\n[]\n```", "model": "deepseek-chat"}
        )
        extractor = PersonalMemoryExtractor(get_model_router=lambda: mock_router)

        await extractor.extract(user_id=1, workspace_id="ws-1", text="Hello")

        mock_router.route_request.assert_awaited_once()
        call = mock_router.route_request.await_args
        # Messages must include a system + user message.
        assert "messages" in call.kwargs
        msgs = call.kwargs["messages"]
        roles = [m["role"] for m in msgs]
        assert "system" in roles
        assert "user" in roles

    @pytest.mark.asyncio
    async def test_extract_uses_default_model_name(self) -> None:
        from app.services.personal_memory_extractor import PersonalMemoryExtractor

        mock_router = _make_mock_router(response={"success": True, "response": "[]", "model": "deepseek-chat"})
        extractor = PersonalMemoryExtractor(get_model_router=lambda: mock_router)
        await extractor.extract(user_id=1, workspace_id="ws-1", text="Hello")

        call = mock_router.route_request.await_args
        # Either model_preference kwarg or model_name kwarg, depending on
        # how the router exposes it. We pass it via model_preference.
        kw = call.kwargs
        # Accept either "model_preference" or "model_name" — at least one
        # of them should be the cheap default.
        candidate = kw.get("model_preference") or kw.get("model_name")
        assert candidate is not None
        # The default model name should not be empty.
        assert isinstance(candidate, str) and len(candidate) > 0

    @pytest.mark.asyncio
    async def test_extract_uses_custom_model_name(self) -> None:
        from app.services.personal_memory_extractor import PersonalMemoryExtractor

        mock_router = _make_mock_router(response={"success": True, "response": "[]", "model": "qwen-0.5b"})
        extractor = PersonalMemoryExtractor(
            get_model_router=lambda: mock_router,
            model_name="qwen-0.5b",
        )
        await extractor.extract(user_id=1, workspace_id="ws-1", text="Hello")

        call = mock_router.route_request.await_args
        candidate = call.kwargs.get("model_preference") or call.kwargs.get("model_name")
        assert candidate == "qwen-0.5b"


class TestExtractReturnsParsedCandidates:
    """``extract()`` returns parsed ``CandidateClaim`` instances on a valid
    LLM response; ``[]`` on an empty response."""

    @pytest.mark.asyncio
    async def test_returns_parsed_candidate_claims(self) -> None:
        from app.services.personal_memory_extractor import (
            CandidateClaim,
            PersonalMemoryExtractor,
        )

        valid_response = (
            "```json\n"
            '[{"subject": "user", "predicate": "prefers", '
            '"object": {"value": "terse updates"}, '
            '"claim_type": "preference", "scope": "personal", '
            '"confidence": 0.85, "rationale": "explicit user statement"}]\n'
            "```"
        )
        mock_router = _make_mock_router(
            response={"success": True, "response": valid_response, "model": "deepseek-chat"}
        )
        extractor = PersonalMemoryExtractor(get_model_router=lambda: mock_router)
        claims = await extractor.extract(user_id=1, workspace_id="ws-1", text="hi")

        assert len(claims) == 1
        c = claims[0]
        assert isinstance(c, CandidateClaim)
        assert c.subject == "user"
        assert c.predicate == "prefers"
        assert c.claim_type == "preference"
        assert c.scope == "personal"
        assert c.confidence == 0.85
        assert c.rationale == "explicit user statement"

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_llm_response(self) -> None:
        from app.services.personal_memory_extractor import PersonalMemoryExtractor

        mock_router = _make_mock_router(
            response={"success": True, "response": "```json\n[]\n```", "model": "deepseek-chat"}
        )
        extractor = PersonalMemoryExtractor(get_model_router=lambda: mock_router)
        claims = await extractor.extract(user_id=1, workspace_id="ws-1", text="nothing")

        assert claims == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_unfenced_empty(self) -> None:
        """Even without a fence, an empty JSON array must yield []."""
        from app.services.personal_memory_extractor import PersonalMemoryExtractor

        mock_router = _make_mock_router(response={"success": True, "response": "[]", "model": "deepseek-chat"})
        extractor = PersonalMemoryExtractor(get_model_router=lambda: mock_router)
        claims = await extractor.extract(user_id=1, workspace_id="ws-1", text="nothing")

        assert claims == []


class TestExtractWithFallbackWhenLLMRaises:
    """``extract_with_fallback`` returns the regex fallback's results when
    the LLM raises."""

    @pytest.mark.asyncio
    async def test_returns_fallback_results_on_llm_exception(self) -> None:
        from app.services.personal_memory_extractor import (
            ExtractionSource,
            PersonalMemoryExtractor,
            RegexPersonalMemoryExtractor,
        )

        mock_router = _make_mock_router(side_effect=RuntimeError("boom"))
        extractor = PersonalMemoryExtractor(
            get_model_router=lambda: mock_router,
            fallback_extractor=RegexPersonalMemoryExtractor(),
        )
        claims, source = await extractor.extract_with_fallback(user_id=1, workspace_id="ws-1", text="My name is Alice")
        assert source is ExtractionSource.FALLBACK
        assert len(claims) >= 1
        # The regex extractor should pick up "My name is Alice" as a fact.
        assert any(c.predicate == "name" or "name" in c.predicate for c in claims)
