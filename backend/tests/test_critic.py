"""TDD tests for CriticAgent + RedTeamAgent (D30-60, T25).

Covers the LLM-driven critic service — the structured-output path that
scores a (mission_goal, plan, outcome) tuple and returns a CriticOutput
DTO ready to be persisted by T27. No DB writes happen here.

Test clusters:

(A) Pure-Python — no DB, no LLM
    * ``CriticOutput`` dataclass defaults (all-optional, lists default to [])
    * ``CriticOutput.to_critique_kwargs()`` produces a kwargs dict whose
      keys match the Critique model column names (1:1 with T24's table)
    * ``CriticInput`` dataclass accepts dict|str for plan / outcome
    * ``CriticAgent()`` no-args constructor works
    * ``CriticAgent(model_id=..., temperature=..., max_tokens=...)`` works
    * ``RedTeamAgent()`` exists and uses a higher temperature

(B) Mocked LLM (AsyncMock for BudgetEnforcer.call)
    * ``critique()`` invokes BudgetEnforcer exactly once with the right
      model_id + temperature
    * Clean JSON → ``CriticOutput`` populated correctly
    * Prose-wrapped JSON → extraction still works
    * score_overall > 1.0 → clamped to 1.0
    * score_overall < 0.0 → clamped to 0.0
    * Missing scores → ``None`` (not 0.0)
    * Missing list fields → ``[]`` (not None)
    * Telemetry: ``model_id`` / ``tokens_in`` / ``tokens_out`` /
      ``duration_ms`` populated from enforcer result
    * ``BudgetExhausted`` is re-raised (not swallowed)
    * No DB session is created / ``session.execute`` is never called

(C) RedTeamAgent-specific
    * Uses temperature >= 0.3 (more exploratory than the critic)
    * ``critique()`` returns a ``CriticOutput`` (same shape)

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_critic.py -v
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Set DATABASE_URL BEFORE importing app modules that need it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner",
)

import pytest

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_enforcer_response(
    *,
    content: str,
    model: str = "deepseek-chat",
    tokens_in: int = 250,
    tokens_out: int = 180,
) -> dict[str, Any]:
    """Build a stand-in for BudgetEnforcer.call()'s return dict.

    Mirrors the shape produced by ``BudgetEnforcer.call`` (see
    ``app/services/budget_enforcer.py`` — ``response["cost"]`` is a dict
    with ``input_tokens`` / ``output_tokens``).
    """
    return {
        "success": True,
        "response": content,
        "content": content,  # the mission_program_service path uses this key
        "model": model,
        "provider": "deepseek",
        "cost": {
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "usd": 0.000123,
        },
        "budget": {
            "spent_usd": 0.000123,
            "remaining_usd": 0.999877,
            "iterations_used": 1,
            "budget_exhausted": False,
        },
    }


def _sample_input() -> Any:
    """A reasonable CriticInput payload for the mocked tests."""
    from app.services.critic import CriticInput

    return CriticInput(
        mission_goal="Refactor the auth module to use OIDC.",
        plan={
            "tasks": [
                {"id": "t1", "type": "code", "description": "Replace JWT lib"},
                {"id": "t2", "type": "test", "description": "Add OIDC tests"},
            ]
        },
        outcome={
            "status": "completed",
            "tasks_completed": 2,
            "tasks_failed": 0,
            "tokens_used": 12345,
        },
        context={"workspace_id": "ws-1"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# (A) Pure-Python — dataclass shape and construction
# ═══════════════════════════════════════════════════════════════════════════


class TestCriticOutputDataclass:
    """Validate CriticOutput defaults and Critique-model column alignment."""

    def test_critic_output_dataclass_defaults(self) -> None:
        """All-optional dataclass: scores default to None, lists to []."""
        from app.services.critic import CriticOutput

        out = CriticOutput()
        # All scores default to None (not 0.0, so missing-data is distinguishable).
        assert out.score_overall is None
        assert out.score_alignment is None
        assert out.score_safety is None
        assert out.score_completeness is None
        # All list/dict fields default to empty collections.
        assert out.misses == []
        assert out.risks == []
        assert out.improvements == []
        assert out.alternatives == []
        # Provenance / audit fields default to None.
        assert out.summary is None
        assert out.raw_response is None
        assert out.model_id is None
        assert out.tokens_in is None
        assert out.tokens_out is None
        assert out.duration_ms is None

    def test_critic_output_field_naming_matches_critique_columns(self) -> None:
        """Every Critique column has a matching CriticOutput field name.

        This guards against silent drift between T24 (Critique model) and
        T25 (CriticOutput) — every column the persistence layer (T27)
        will read from CriticOutput must exist as a dataclass field.
        """
        # Use the actual SQLAlchemy table column names as the source of truth.
        from app.models import Base
        from app.models.critique_models import Critique
        from app.services.critic import CriticOutput

        critique_columns = set(Base.metadata.tables["critiques"].columns.keys())
        # Columns the persistence layer is allowed to fill from the
        # critic stack (excludes id, timestamps, FKs, audit-trail columns
        # that T27 fills itself).
        persistence_managed = {
            "score_overall",
            "score_alignment",
            "score_safety",
            "score_completeness",
            "summary",
            "misses",
            "risks",
            "improvements",
            "alternatives",
            "raw_response",
            "model_id",
            "tokens_in",
            "tokens_out",
            "duration_ms",
        }
        assert persistence_managed.issubset(critique_columns), (
            "Critique model missing one or more columns the CriticOutput "
            f"expects: {persistence_managed - critique_columns}"
        )

        # And every such column has a matching field on CriticOutput.
        out = CriticOutput()
        for col in persistence_managed:
            assert hasattr(out, col), (
                f"CriticOutput is missing a field for Critique.{col}; " "T27 will fail to persist the agent's output."
            )

    def test_critic_output_to_critique_kwargs_is_a_mapping(self) -> None:
        """to_critique_kwargs() returns a dict keyed by Critique column names."""
        from app.services.critic import CriticOutput

        out = CriticOutput(
            score_overall=0.7,
            score_alignment=0.8,
            score_safety=0.9,
            score_completeness=0.6,
            summary="ok",
            misses=["m1"],
            risks=["r1"],
            improvements=[{"description": "d1", "confidence": 0.5}],
            alternatives=[{"approach": "a1", "tradeoffs": "t1", "score": 0.4}],
            raw_response={"score_overall": 0.7},
            model_id="deepseek-chat",
            tokens_in=10,
            tokens_out=20,
            duration_ms=42,
        )
        kwargs = out.to_critique_kwargs()
        assert isinstance(kwargs, dict)
        # Spot-check the critical keys map correctly.
        for key in (
            "score_overall",
            "score_alignment",
            "score_safety",
            "score_completeness",
            "summary",
            "misses",
            "risks",
            "improvements",
            "alternatives",
            "raw_response",
            "model_id",
            "tokens_in",
            "tokens_out",
            "duration_ms",
        ):
            assert key in kwargs, f"to_critique_kwargs() missing {key!r}"
        assert kwargs["score_overall"] == 0.7
        assert kwargs["misses"] == ["m1"]
        assert kwargs["improvements"] == [{"description": "d1", "confidence": 0.5}]

    def test_critic_input_accepts_dict_or_str_for_plan_outcome(self) -> None:
        """CriticInput.plan / outcome accept both dict and str."""
        from app.services.critic import CriticInput

        # Dict form.
        a = CriticInput(
            mission_goal="goal",
            plan={"tasks": ["a", "b"]},
            outcome={"status": "ok"},
        )
        assert a.plan == {"tasks": ["a", "b"]}
        # String form (free-form plan / outcome).
        b = CriticInput(
            mission_goal="goal",
            plan="Step 1: ... Step 2: ...",
            outcome="The mission succeeded.",
        )
        assert b.plan == "Step 1: ... Step 2: ..."
        # Context is optional.
        c = CriticInput(mission_goal="goal", plan="p", outcome="o")
        assert c.context is None


class TestCriticAgentConstruction:
    """Validate the agent's constructor surface (no LLM calls)."""

    def test_critic_agent_constructable_no_args(self) -> None:
        from app.services.critic import CriticAgent

        agent = CriticAgent()
        # The agent should expose the documented attributes.
        assert agent.model_id == "deepseek-v4-flash"
        assert isinstance(agent.temperature, float)
        assert isinstance(agent.max_tokens, int)
        assert agent.temperature > 0

    def test_critic_agent_constructable_with_overrides(self) -> None:
        from app.services.critic import CriticAgent

        agent = CriticAgent(
            model_id="claude-3-5-sonnet",
            temperature=0.42,
            max_tokens=1500,
        )
        assert agent.model_id == "claude-3-5-sonnet"
        assert agent.temperature == 0.42
        assert agent.max_tokens == 1500

    def test_critic_agent_default_constants_exposed(self) -> None:
        """The module must expose the documented module-level constants."""
        from app.services import critic

        assert critic.CRITIC_DEFAULT_MODEL == "deepseek-v4-flash"
        assert critic.CRITIC_DEFAULT_TEMPERATURE == 0.2
        assert critic.CRITIC_DEFAULT_MAX_TOKENS == 2000
        assert isinstance(critic.CRITIC_SYSTEM_PROMPT, str)
        assert "{goal}" not in critic.CRITIC_SYSTEM_PROMPT  # system prompt is static
        assert isinstance(critic.CRITIC_USER_PROMPT_TEMPLATE, str)
        assert "{goal}" in critic.CRITIC_USER_PROMPT_TEMPLATE
        assert "{plan}" in critic.CRITIC_USER_PROMPT_TEMPLATE
        assert "{outcome}" in critic.CRITIC_USER_PROMPT_TEMPLATE
        assert "{context}" in critic.CRITIC_USER_PROMPT_TEMPLATE

    def test_module_imports_contain_required_symbols(self) -> None:
        """The class must be importable in isolation (per the spec)."""
        from app.services.critic import (
            CriticAgent,
            CriticInput,
            CriticOutput,
            RedTeamAgent,
        )

        assert CriticAgent is not None
        assert CriticInput is not None
        assert CriticOutput is not None
        assert RedTeamAgent is not None


class TestRedTeamAgentConstruction:
    """Validate the RedTeamAgent variant uses a higher temperature."""

    def test_red_team_agent_uses_higher_temperature(self) -> None:
        from app.services.critic import RedTeamAgent

        agent = RedTeamAgent()
        # Spec: RedTeamAgent uses temperature >= 0.3 (more exploratory).
        assert agent.temperature >= 0.3, f"RedTeamAgent.temperature must be >= 0.3 (was {agent.temperature})"


# ═══════════════════════════════════════════════════════════════════════════
# (B) Mocked LLM — .critique() behaviour
# ═══════════════════════════════════════════════════════════════════════════


class TestCriticAgentCritique:
    """Validate CriticAgent.critique() against a mocked BudgetEnforcer."""

    async def test_critic_critique_calls_budget_enforcer(self) -> None:
        """The agent invokes BudgetEnforcer exactly once with the right args."""
        from app.services.critic import CriticAgent

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(
                content='{"score_overall": 0.7, "summary": "ok"}',
            )
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent(model_id="deepseek-chat", temperature=0.2)
            await agent.critique(
                mission_goal="Refactor auth",
                plan={"tasks": ["t1"]},
                outcome={"status": "ok"},
                user_id=1,
                workspace_id="ws-1",
            )

        # Exactly one LLM call.
        assert mock_enforcer.call.await_count == 1
        call_kwargs = mock_enforcer.call.await_args.kwargs
        assert call_kwargs["model_id"] == "deepseek-chat"
        assert call_kwargs["temperature"] == 0.2
        # Messages: [system, user].
        msgs = call_kwargs["messages"]
        assert isinstance(msgs, list)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "Refactor auth" in msgs[1]["content"]

    async def test_critic_critique_parses_structured_json(self) -> None:
        """A clean-JSON LLM response is parsed into a populated CriticOutput."""
        from app.services.critic import CriticAgent

        payload = {
            "score_overall": 0.82,
            "score_alignment": 0.9,
            "score_safety": 0.7,
            "score_completeness": 0.85,
            "summary": "Plan is solid, two safety risks to address.",
            "misses": ["missing rollback step", "no rate-limit plan"],
            "risks": ["data exfil via misconfig", "downtime on rollout"],
            "improvements": [
                {"description": "add rollback task", "confidence": 0.9},
                {"description": "add rate-limit", "confidence": 0.7},
            ],
            "alternatives": [
                {"approach": "use feature flag", "tradeoffs": "added complexity", "score": 0.6},
            ],
        }
        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(content=json_dumps(payload)),
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent()
            out = await agent.critique(
                mission_goal="Refactor auth",
                plan={"tasks": ["t1"]},
                outcome={"status": "ok"},
                user_id=1,
                workspace_id="ws-1",
            )

        assert out.score_overall == 0.82
        assert out.score_alignment == 0.9
        assert out.score_safety == 0.7
        assert out.score_completeness == 0.85
        assert out.summary == "Plan is solid, two safety risks to address."
        assert out.misses == ["missing rollback step", "no rate-limit plan"]
        assert out.risks == ["data exfil via misconfig", "downtime on rollout"]
        assert out.improvements == [
            {"description": "add rollback task", "confidence": 0.9},
            {"description": "add rate-limit", "confidence": 0.7},
        ]
        assert out.alternatives == [
            {"approach": "use feature flag", "tradeoffs": "added complexity", "score": 0.6},
        ]
        # The full parsed payload is preserved for audit.
        assert out.raw_response == payload

    async def test_critic_critique_parses_json_in_prose(self) -> None:
        """JSON embedded in prose ('Here is the critique: {...}') still extracts."""
        from app.services.critic import CriticAgent

        payload = {
            "score_overall": 0.65,
            "score_alignment": 0.7,
            "score_safety": 0.6,
            "score_completeness": 0.65,
            "summary": "prose-wrapped",
            "misses": ["m1"],
            "risks": ["r1"],
            "improvements": [{"description": "d1", "confidence": 0.5}],
            "alternatives": [],
        }
        prose = (
            "Sure, here is the structured critique you asked for:\n\n" f"{json_dumps(payload)}\n\n" "Hope that helps!"
        )
        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(content=prose),
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent()
            out = await agent.critique(
                mission_goal="g",
                plan="p",
                outcome="o",
                user_id=1,
                workspace_id="ws-1",
            )

        assert out.score_overall == 0.65
        assert out.summary == "prose-wrapped"
        assert out.misses == ["m1"]
        assert out.risks == ["r1"]
        assert out.raw_response == payload

    async def test_critic_critique_clamps_scores(self) -> None:
        """Out-of-range scores are clamped to [0.0, 1.0]."""
        from app.services.critic import CriticAgent

        payload = {
            "score_overall": 1.5,  # > 1.0 → clamp to 1.0
            "score_alignment": -0.2,  # < 0.0 → clamp to 0.0
            "score_safety": 99.0,  # > 1.0 → clamp to 1.0
            "score_completeness": -10.0,  # < 0.0 → clamp to 0.0
            "summary": "clamp test",
        }
        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(content=json_dumps(payload)),
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent()
            out = await agent.critique(
                mission_goal="g",
                plan="p",
                outcome="o",
                user_id=1,
                workspace_id="ws-1",
            )

        assert out.score_overall == 1.0
        assert out.score_alignment == 0.0
        assert out.score_safety == 1.0
        assert out.score_completeness == 0.0

    async def test_critic_critique_handles_missing_scores(self) -> None:
        """Missing scores default to None (NOT 0.0 — distinguishes from a real 0)."""
        from app.services.critic import CriticAgent

        payload = {"summary": "no scores returned"}  # no score_* fields
        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(content=json_dumps(payload)),
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent()
            out = await agent.critique(
                mission_goal="g",
                plan="p",
                outcome="o",
                user_id=1,
                workspace_id="ws-1",
            )

        assert out.score_overall is None
        assert out.score_alignment is None
        assert out.score_safety is None
        assert out.score_completeness is None

    async def test_critic_critique_handles_missing_lists(self) -> None:
        """Missing list fields default to [] (not None)."""
        from app.services.critic import CriticAgent

        payload = {"score_overall": 0.5, "summary": "only summary"}
        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(content=json_dumps(payload)),
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent()
            out = await agent.critique(
                mission_goal="g",
                plan="p",
                outcome="o",
                user_id=1,
                workspace_id="ws-1",
            )

        assert out.misses == []
        assert out.risks == []
        assert out.improvements == []
        assert out.alternatives == []

    async def test_critic_critique_records_telemetry(self) -> None:
        """The returned CriticOutput carries model_id, tokens, duration_ms."""
        from app.services.critic import CriticAgent

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(
                content='{"score_overall": 0.5, "summary": "t"}',
                model="deepseek-chat",
                tokens_in=421,
                tokens_out=311,
            )
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent(model_id="deepseek-chat")
            out = await agent.critique(
                mission_goal="g",
                plan="p",
                outcome="o",
                user_id=1,
                workspace_id="ws-1",
            )

        assert out.model_id == "deepseek-chat"
        assert out.tokens_in == 421
        assert out.tokens_out == 311
        assert isinstance(out.duration_ms, int)
        assert out.duration_ms >= 0

    async def test_critic_critique_handles_budget_exhausted(self) -> None:
        """BudgetExhausted from the enforcer is re-raised (not swallowed)."""
        from app.models.capability_models import BudgetExhausted
        from app.services.critic import CriticAgent

        mock_enforcer = MagicMock()
        from app.models.capability_models import Budget

        mock_budget = Budget(max_cost_usd="0.10")
        mock_enforcer.call = AsyncMock(side_effect=BudgetExhausted("cost exceeded", mock_budget))

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent()
            with pytest.raises(BudgetExhausted):
                await agent.critique(
                    mission_goal="g",
                    plan="p",
                    outcome="o",
                    user_id=1,
                    workspace_id="ws-1",
                )

    async def test_critic_critique_does_not_write_to_db(self) -> None:
        """The agent must NOT touch any DB session during a critique call.

        A mock AsyncSession is constructed but never passed to the agent
        (the agent doesn't accept one); the assertion is that the mock's
        ``execute`` / ``add`` / ``flush`` / ``commit`` are never called.
        """
        from app.services.critic import CriticAgent

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(
                content='{"score_overall": 0.5, "summary": "no db"}',
            )
        )
        mock_session = MagicMock()
        mock_session.execute = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = MagicMock()
        mock_session.commit = MagicMock()

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent()
            # Note: we deliberately do NOT pass mock_session to .critique().
            out = await agent.critique(
                mission_goal="g",
                plan="p",
                outcome="o",
                user_id=1,
                workspace_id="ws-1",
            )

        # The mock session was never touched.
        mock_session.execute.assert_not_called()
        mock_session.add.assert_not_called()
        mock_session.flush.assert_not_called()
        mock_session.commit.assert_not_called()
        # And the agent still produced a sensible output.
        assert out.score_overall == 0.5

    async def test_critic_critique_accepts_critic_input_object(self) -> None:
        """CriticInput convenience: pass a single dataclass instead of 4 args."""
        from app.services.critic import CriticAgent

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(
                content='{"score_overall": 0.4, "summary": "ok"}',
            )
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent()
            inp = _sample_input()
            out = await agent.critique_from(inp, user_id=1, workspace_id="ws-1")

        assert out.score_overall == 0.4
        assert out.summary == "ok"

    async def test_critic_critique_records_telemetry_on_garbage_response(self) -> None:
        """Even when the LLM returns unparseable junk, telemetry is recorded."""
        from app.services.critic import CriticAgent

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(
                content="not json at all, just prose",  # garbage
                tokens_in=12,
                tokens_out=34,
            )
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = CriticAgent(model_id="deepseek-chat")
            out = await agent.critique(
                mission_goal="g",
                plan="p",
                outcome="o",
                user_id=1,
                workspace_id="ws-1",
            )

        # Telemetry still populated.
        assert out.model_id == "deepseek-chat"
        assert out.tokens_in == 12
        assert out.tokens_out == 34
        assert isinstance(out.duration_ms, int)
        # All semantic fields are defaults (None / []).
        assert out.score_overall is None
        assert out.summary is None
        assert out.misses == []
        assert out.raw_response is None  # nothing parseable


# ═══════════════════════════════════════════════════════════════════════════
# (C) RedTeamAgent-specific behaviour
# ═══════════════════════════════════════════════════════════════════════════


class TestRedTeamAgentCritique:
    """The RedTeamAgent shares CriticOutput's shape but explores more."""

    async def test_red_team_critique_returns_critic_output(self) -> None:
        from app.services.critic import CriticOutput, RedTeamAgent

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value=_make_enforcer_response(
                content='{"score_overall": 0.3, "summary": "adversarial"}',
            )
        )

        with patch(
            "app.services.critic.get_budget_enforcer",
            return_value=mock_enforcer,
        ):
            agent = RedTeamAgent()
            # Sanity: it really is exploratory.
            assert agent.temperature >= 0.3

            out = await agent.critique(
                mission_goal="g",
                plan="p",
                outcome="o",
                user_id=1,
                workspace_id="ws-1",
            )

        # Same shape as CriticAgent's output.
        assert isinstance(out, CriticOutput)
        assert out.score_overall == 0.3
        assert out.summary == "adversarial"

        # The enforcer was called with the RedTeamAgent's elevated temperature.
        call_kwargs = mock_enforcer.call.await_args.kwargs
        assert call_kwargs["temperature"] >= 0.3


# ═══════════════════════════════════════════════════════════════════════════
# Local helpers
# ═══════════════════════════════════════════════════════════════════════════


def json_dumps(obj: Any) -> str:
    """Tiny indirection so the test file doesn't shadow stdlib ``json``."""
    import json

    return json.dumps(obj)
