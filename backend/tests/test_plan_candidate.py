"""Unit tests for PlanCandidate dataclass."""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.services.plan_selection.plan_candidate import PlanCandidate


class TestPlanCandidateDataclass:
    """PlanCandidate: construction and field defaults."""

    def test_basic_construction(self):
        cand = PlanCandidate(
            plan_id="test_v1",
            generation_strategy="heuristic",
            tasks=[{"title": "T1", "task_type": "llm"}],
        )
        assert cand.plan_id == "test_v1"
        assert cand.generation_strategy == "heuristic"
        assert len(cand.tasks) == 1
        assert cand.estimated_cost_usd == 0.0
        assert cand.estimated_latency_ms == 0
        assert cand.estimated_tokens == 0
        assert cand.quality_score == 0.0
        assert cand.risk_flags == []
        assert cand.rationale == ""

    def test_full_construction(self):
        cand = PlanCandidate(
            plan_id="llm_a",
            generation_strategy="llm_persona",
            tasks=[{"title": "T1"}, {"title": "T2"}],
            estimated_cost_usd=0.05,
            estimated_latency_ms=4000,
            estimated_tokens=2000,
            quality_score=0.75,
            risk_flags=["unbounded_retry"],
            rationale="Concise plan",
        )
        assert cand.estimated_cost_usd == 0.05
        assert cand.quality_score == 0.75
        assert cand.risk_flags == ["unbounded_retry"]


class TestPlanCandidateSerialization:
    """PlanCandidate: to_dict / from_dict round-trip."""

    def test_to_dict(self):
        cand = PlanCandidate(
            plan_id="h1",
            generation_strategy="heuristic",
            tasks=[{"title": "T1"}],
            estimated_cost_usd=0.01,
            quality_score=0.8,
        )
        d = cand.to_dict()
        assert d["plan_id"] == "h1"
        assert d["generation_strategy"] == "heuristic"
        assert d["tasks"] == [{"title": "T1"}]
        assert d["estimated_cost_usd"] == 0.01
        assert d["quality_score"] == 0.8

    def test_from_dict(self):
        d = {
            "plan_id": "llm_b",
            "generation_strategy": "llm_persona",
            "tasks": [{"title": "A"}, {"title": "B"}],
            "estimated_cost_usd": 0.03,
            "estimated_latency_ms": 6000,
            "estimated_tokens": 3000,
            "quality_score": 0.65,
            "risk_flags": ["no_fallback"],
            "rationale": "Thorough plan",
        }
        cand = PlanCandidate.from_dict(d)
        assert cand.plan_id == "llm_b"
        assert cand.estimated_cost_usd == 0.03
        assert cand.risk_flags == ["no_fallback"]

    def test_round_trip(self):
        original = PlanCandidate(
            plan_id="rt",
            generation_strategy="heuristic",
            tasks=[{"title": "T1", "task_type": "code"}],
            estimated_cost_usd=0.0,
            estimated_latency_ms=2000,
            estimated_tokens=1000,
            quality_score=0.9,
            risk_flags=[],
            rationale="test",
        )
        restored = PlanCandidate.from_dict(original.to_dict())
        assert restored.plan_id == original.plan_id
        assert restored.tasks == original.tasks
        assert restored.quality_score == original.quality_score
        assert restored.risk_flags == original.risk_flags
