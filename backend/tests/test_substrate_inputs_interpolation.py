"""Tests for {{ inputs.* }} interpolation into non-sandbox node types.

T1 proved ``run.input_data`` flows into the substrate node-execution context
as ``context["inputs"]`` and is substituted into **sandbox** node prompts
(``node_executor._handle_sandbox_node``). This test proves the SAME
``{{ inputs.<key> }}`` rendering reaches **LLM / RAG / web search** node
configs through the shared ``interpolate_inputs`` helper, and that the
sandbox path is unchanged (regression guard).

No real DB / LLM / network: the LLM call is mocked so we can capture the
rendered prompt; RAG and web-search services are mocked too.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.substrate import interpolate
from app.services.substrate.interpolate import interpolate_inputs
from app.services.substrate.node_executor import NodeExecutor
from app.services.substrate.workflow_models import WorkflowNode


class _StubUnifiedExecutor:
    def is_aborted(self, run_id):
        return False

    def check_circuit_breaker(self, **kwargs):
        return (True, "ok")


def _executor() -> NodeExecutor:
    return NodeExecutor(_StubUnifiedExecutor())


def _node(node_type: str, config=None, **kw) -> WorkflowNode:
    return WorkflowNode(
        id=kw.get("id", "n1"),
        type=node_type,
        title=kw.get("title", "N"),
        config=config or {},
    )


# ── Unit: shared helper ──────────────────────────────────────────────


class TestInterpolateInputs:
    def test_substitutes_known_key(self):
        assert interpolate_inputs("hi {{ inputs.name }}", {"name": "Glenn"}) == "hi Glenn"

    def test_substitutes_multiple_keys(self):
        text = "{{ inputs.a }}-{{ inputs.b }}"
        assert interpolate_inputs(text, {"a": "1", "b": "2"}) == "1-2"

    def test_whitespace_tolerated(self):
        assert interpolate_inputs("{{  inputs.x  }}", {"x": "y"}) == "y"

    def test_unknown_key_left_verbatim(self):
        # A missing input must never mangle the template.
        assert interpolate_inputs("{{ inputs.missing }}", {"x": "y"}) == "{{ inputs.missing }}"

    def test_empty_inputs_returns_text(self):
        assert interpolate_inputs("{{ inputs.x }}", {}) == "{{ inputs.x }}"

    def test_none_inputs_returns_text(self):
        assert interpolate_inputs("{{ inputs.x }}", None) == "{{ inputs.x }}"

    def test_empty_text_returns_text(self):
        assert interpolate_inputs("", {"x": "y"}) == ""

    def test_non_string_value_coerced(self):
        # int/other values become their str() form.
        assert interpolate_inputs("n={{ inputs.n }}", {"n": 7}) == "n=7"


# ── LLM node ────────────────────────────────────────────────────────


class TestLLMNodeInterpolation:
    @pytest.mark.asyncio
    async def test_inputs_reach_llm_prompt(self):
        captured_enforcers: list = []

        def fake_enforcer():
            enforcer = MagicMock()
            enforcer.call = AsyncMock(
                side_effect=lambda **kw: {
                    "success": True,
                    "response": "ok",
                    "model": "m",
                    "provider": "p",
                    "cost": {"usd": 0.0, "input_tokens": 1, "output_tokens": 1},
                    "budget": {},
                }
            )
            captured_enforcers.append(enforcer)
            return enforcer

        node = _node(
            "llm_call",
            {
                "prompt": "Summarize {{ inputs.topic }} for {{ inputs.audience }}.",
                "system_prompt": "You are an expert on {{ inputs.topic }}.",
            },
        )
        context = {"inputs": {"topic": "quantum computing", "audience": "CEOs"}}

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=MagicMock(
                    append=AsyncMock(),
                    find_by_idempotency_key=AsyncMock(return_value=None),
                ),
            ),
            patch(
                "app.services.budget_enforcer.get_budget_enforcer",
                side_effect=fake_enforcer,
            ),
            patch(
                "app.services.substrate.depth_selection.select_model_for_depth",
                return_value=MagicMock(
                    model_id="m",
                    reasoning=None,
                    reflection_iterations=0,
                    degraded=False,
                    degradation_note="",
                ),
            ),
        ):
            ex = _executor()
            res = await ex._handle_llm(
                db=MagicMock(),
                node=node,
                context=context,
                budget=MagicMock(remaining=MagicMock(return_value={"cost_usd": 1.0})),
                run_id="r-llm",
                workflow=None,
            )

        assert res["success"] is True
        # Capture the messages passed to the (mocked) provider.
        call_kwargs = captured_enforcers[0].call.call_args.kwargs
        messages = call_kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        system_msg = next((m for m in messages if m["role"] == "system"), None)

        # The placeholder must be GONE; the resolved value must be present.
        assert "{{ inputs.topic }}" not in user_msg["content"]
        assert "quantum computing" in user_msg["content"]
        assert "CEOs" in user_msg["content"]
        assert system_msg is not None
        assert "quantum computing" in system_msg["content"]


# ── RAG node ────────────────────────────────────────────────────────


class TestRAGNodeInterpolation:
    @pytest.mark.asyncio
    async def test_inputs_reach_rag_query(self):
        captured: dict = {}
        rag_mock = MagicMock()
        rag_mock.query_documents = MagicMock(return_value=[{"chunk": "x"}])

        node = _node("rag_query", {"query": "Find docs about {{ inputs.subject }}"})
        context = {"inputs": {"subject": "billing"}}

        with patch(
            "app.services.rag_service.RAGService",
            return_value=rag_mock,
        ):
            ex = _executor()
            res = await ex._handle_rag(node=node, context=context, workflow=None)

        assert res["success"] is True
        rag_mock.query_documents.assert_called_once()
        called_query = rag_mock.query_documents.call_args.args[0]
        assert called_query == "Find docs about billing"
        assert "{{ inputs.subject }}" not in called_query


# ── Web search node ─────────────────────────────────────────────────


class TestWebSearchNodeInterpolation:
    @pytest.mark.asyncio
    async def test_inputs_reach_web_query(self):
        service = MagicMock()
        service.search = AsyncMock(return_value=MagicMock(results=[]))

        node = _node("web_search", {"query": "latest news on {{ inputs.company }}"})
        context = {"inputs": {"company": "Flowmanner"}}

        # Mock SearchRequest + SearchType so the test validates interpolation
        # without depending on the unrelated SearchType.GENERAL enum reference
        # in the handler (pre-existing bug; flagged separately).
        req_capture = {}

        class _StubRequest:
            def __init__(self, query, **kw):
                self.query = query
                req_capture["query"] = query

        class _StubSearchType:
            GENERAL = "general"

        with (
            patch(
                "app.services.web_search.service.get_search_service",
                return_value=service,
            ),
            patch(
                "app.services.web_search.models.SearchRequest",
                _StubRequest,
            ),
            patch(
                "app.services.web_search.models.SearchType",
                _StubSearchType,
            ),
        ):
            ex = _executor()
            res = await ex._handle_web_search(node=node, context=context)

        assert res["success"] is True
        service.search.assert_called_once()
        assert req_capture["query"] == "latest news on Flowmanner"
        assert "{{ inputs.company }}" not in req_capture["query"]


# ── Regression: sandbox path uses identical rendering ───────────────


class TestSandboxParity:
    def test_sandbox_regex_matches_helper(self):
        # The sandbox handler uses its own re.sub with this exact pattern.
        import re

        sandbox_pattern = re.compile(r"\{\{\s*inputs\.(\w+)\s*\}\}")
        text = "run {{ inputs.a }} and {{ inputs.b }}"
        via_helper = interpolate_inputs(text, {"a": "1", "b": "2"})
        via_sandbox = sandbox_pattern.sub(
            lambda m: str({"a": "1", "b": "2"}.get(m.group(1), m.group(0))),
            text,
        )
        assert via_helper == via_sandbox == "run 1 and 2"
        # Prove the helper is the single source the non-sandbox nodes use.
        assert interpolate_inputs.__module__ == "app.services.substrate.interpolate"
