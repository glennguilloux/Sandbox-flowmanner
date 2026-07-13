"""Comment 9: SecondPassVerifier wired into the inbox drain.

Covers: DeepSeek primary + Anthropic verifier, Opus primary + non-Anthropic
verifier, same-family rejection (verifier disabled), verifier outage
escalation, and lexical-only degraded mode when second-pass is off / no
different-family verifier exists.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("LLM_API_KEY", "test-dummy-key")

from app.services.reviewer_guard.inbox_drain import build_run_context, drain_run_to_inbox
from app.services.reviewer_guard.verifier import SecondPassVerifier, different_family


def _node(node_id, text):
    return SimpleNamespace(id=node_id, output_data={"text": text})


def _make_ctx(run_id="run-1", mission_id="mission-1", user_id=1, reviewer="deepseek-v4-flash"):
    nodes = [
        _node("n1", "The model produced a correct summary grounded in the brief."),
        _node("n2", "Unrelated hallucinated claim with no support anywhere."),
    ]
    ctx = build_run_context(
        run_id=run_id,
        mission_id=mission_id,
        nodes=nodes,
        user_id=user_id,
        brief="The brief states the model should summarize the source.",
    )
    return ctx, reviewer


def _catalog_stub(verifier_ids):
    """Fake catalog returning verifier_ids for select_for_use_case('verifier')."""

    class _Spec:
        def __init__(self, mid):
            self.model_id = mid
            self.input_per_1m = 0.0
            self.output_per_1m = 0.0
            self.local = False

    class _Stub:
        def __init__(self, ids, exclude):
            self._ids = ids
            self._exclude = set(exclude or [])

        def select_for_use_case(self, use_case, **kwargs):
            exclude = set(kwargs.get("exclude_families") or []) | self._exclude
            out = []
            for m in self._ids:
                fam = m.split("/", 1)[0]
                if "/" not in m:
                    fam = m.split("-", 1)[0]
                if fam in exclude:
                    continue
                out.append(_Spec(m))
            return out

    return _Stub(verifier_ids, [])


def _settings_stub(second_pass=False, premium=False):
    return SimpleNamespace(
        REVIEWER_GUARD_SECOND_PASS_ENABLED=second_pass,
        REVIEWER_GUARD_DRAIN_ENABLED=True,
        ENABLE_PREMIUM_MODELS=premium,
    )


async def _run(reviewer, verifier_ids, second_pass, premium=False, fail_verifier=False):
    ctx, _ = _make_ctx(reviewer=reviewer)
    settings = _settings_stub(second_pass=second_pass, premium=premium)
    catalog = _catalog_stub(verifier_ids)

    interrupts = []
    service = MagicMock()
    service.create_interrupt = AsyncMock(side_effect=lambda **kw: interrupts.append(kw))

    # verifier injected via the drain path uses enforcer.call; if fail_verifier
    # we make the injected SecondPassVerifier degrade.
    def _make_guard(*a, **k):
        # Patch SecondPassVerifier.averify to a fake that asserts/supports.
        real = SecondPassVerifier.__init__

        class _F(SecondPassVerifier):
            async def averify(self, *, transcript_text, claim_id, claim_content):
                if fail_verifier:
                    return SimpleNamespace(
                        supports=False, evidence="", reason="boom", model_id=self.model_id, degraded=True
                    )
                # supports grounded claims, rejects the hallucinated one
                return SimpleNamespace(
                    supports="hallucinated" not in claim_content,
                    evidence="x",
                    reason="ok",
                    model_id=self.model_id,
                    degraded=False,
                )

        return _F(*a, **k)

    with (
        patch("app.config.settings", settings),
        patch("app.services.model_catalog.get_model_catalog", lambda: catalog),
        patch("app.services.reviewer_guard.inbox_drain.SecondPassVerifier", _make_guard),
        patch("app.services.hitl_service.HITLService", return_value=service),
        patch("app.models.hitl_models.HumanInterruptType") as hit,
    ):
        hit.ESCALATION = "escalation"
        drained = await drain_run_to_inbox(db=MagicMock(), ctx=ctx, reviewer_model=reviewer)
    return drained, interrupts


@pytest.mark.asyncio
async def test_deepseek_primary_with_anthropic_verifier():
    drained, interrupts = await _run(
        reviewer="deepseek-v4-flash",
        verifier_ids=["claude-3-haiku", "gpt-4o"],
        second_pass=True,
    )
    # The hallucinated node (n2) should still escalate; grounded n1 should not.
    assert drained >= 1
    escalated_claims = {i.get("proposed_action", {}).get("claim_id") for i in interrupts}
    # n2 (the hallucinated node) must be among escalations.
    assert any("n2" in c for c in escalated_claims), escalated_claims
    # A verifier was actually selected and used (different family than deepseek).
    assert any(i.get("context", {}).get("verifier_model") == "claude-3-haiku" for i in interrupts)


@pytest.mark.asyncio
async def test_opus_primary_with_non_anthropic_verifier():
    drained, interrupts = await _run(
        reviewer="claude-3-opus",
        verifier_ids=["deepseek-chat", "gpt-4o"],
        second_pass=True,
        premium=True,
    )
    assert drained >= 1
    chosen = {i.get("context", {}).get("verifier_model") for i in interrupts}
    assert "claude-3-opus" not in chosen  # never same-family


@pytest.mark.asyncio
async def test_same_family_rejection_uses_lexical_only():
    # Reviewer is deepseek; only deepseek verifier available → rejected, lexical-only.
    settings = _settings_stub(second_pass=True)
    catalog = _catalog_stub(["deepseek-chat"])
    ctx, reviewer = _make_ctx(reviewer="deepseek-v4-flash")
    interrupts = []
    service = MagicMock()
    service.create_interrupt = AsyncMock(side_effect=lambda **kw: interrupts.append(kw))

    with (
        patch("app.config.settings", settings),
        patch("app.services.model_catalog.get_model_catalog", lambda: catalog),
        patch("app.services.hitl_service.HITLService", return_value=service),
    ):
        drained = await drain_run_to_inbox(db=MagicMock(), ctx=ctx, reviewer_model=reviewer)
    assert drained >= 1
    # No verifier was ever selected (same family) → lexical-only degradation.
    assert all(i.get("context", {}).get("second_pass") == "lexical_only" for i in interrupts)
    assert all(i.get("context", {}).get("verifier_model") is None for i in interrupts)


@pytest.mark.asyncio
async def test_lexical_only_when_second_pass_disabled():
    settings = _settings_stub(second_pass=False)
    catalog = _catalog_stub(["claude-3-haiku"])
    ctx, reviewer = _make_ctx(reviewer="deepseek-v4-flash")
    interrupts = []
    service = MagicMock()
    service.create_interrupt = AsyncMock(side_effect=lambda **kw: interrupts.append(kw))

    with (
        patch("app.config.settings", settings),
        patch("app.services.model_catalog.get_model_catalog", lambda: catalog),
        patch("app.services.hitl_service.HITLService", return_value=service),
    ):
        drained = await drain_run_to_inbox(db=MagicMock(), ctx=ctx, reviewer_model=reviewer)
    assert drained >= 1
    assert all(i.get("context", {}).get("second_pass") == "lexical_only" for i in interrupts)


@pytest.mark.asyncio
async def test_verifier_outage_escalates_on_uncertainty():
    # Verifier deployed but the LLM call fails → degraded → escalate on uncertainty.
    drained, interrupts = await _run(
        reviewer="deepseek-v4-flash",
        verifier_ids=["claude-3-haiku"],
        second_pass=True,
        fail_verifier=True,
    )
    assert drained >= 1
    # Even the grounded claim escalates because the verifier degraded.
    assert any(i.get("context", {}).get("verifier_model") == "claude-3-haiku" for i in interrupts)


def test_different_family_helper():
    assert different_family("deepseek-v4-flash", "claude-3-haiku")
    assert different_family("deepseek/foo", "openai/bar")
    assert not different_family("deepseek-v4-flash", "deepseek-chat")
