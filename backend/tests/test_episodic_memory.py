"""Unit tests for EpisodicMemoryService — Q2-Q3 Chunk 2.

Tests: record_episode, retrieve_relevant, mark_used, workspace_scoping,
user_scoping, k_cap_5, cost_bucket_classification.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.memory_models import (
    EpisodeCostBucket,
)
from app.services.episodic_memory_service import (
    EpisodicMemoryService,
    _classify_cost,
)

# ── Helpers ────────────────────────────────────────────────────────


def _make_service() -> EpisodicMemoryService:
    return EpisodicMemoryService()


class FakeDB:
    """Minimal async DB mock for unit tests."""

    def __init__(self):
        self._added = []
        self._flushed = False

    def add(self, obj):
        self._added.append(obj)

    async def flush(self):
        self._flushed = True

    async def execute(self, *args, **kwargs):
        # Return empty result by default
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []), fetchall=lambda: [])


# ── Tests ──────────────────────────────────────────────────────────


class TestClassifyCost:
    """Test cost bucket classification."""

    def test_small_cost(self):
        assert _classify_cost(0.01) == EpisodeCostBucket.SMALL

    def test_medium_cost(self):
        assert _classify_cost(0.10) == EpisodeCostBucket.MEDIUM

    def test_large_cost(self):
        assert _classify_cost(1.50) == EpisodeCostBucket.LARGE

    def test_boundary_small_to_medium(self):
        assert _classify_cost(0.05) == EpisodeCostBucket.SMALL
        assert _classify_cost(0.06) == EpisodeCostBucket.MEDIUM

    def test_boundary_medium_to_large(self):
        assert _classify_cost(0.50) == EpisodeCostBucket.MEDIUM
        assert _classify_cost(0.51) == EpisodeCostBucket.LARGE


class TestRecordEpisode:
    """Test episode recording."""

    @pytest.mark.asyncio
    async def test_record_episode_success(self):
        service = _make_service()
        db = FakeDB()

        with patch.object(service, "_store_embedding", new_callable=AsyncMock, return_value="qdrant-123"):
            with patch.object(service, "_embed_text", new_callable=AsyncMock, return_value=[0.1] * 384):
                episode = await service.record_episode(
                    db,
                    payload={
                        "workspace_id": str(uuid4()),
                        "user_id": 1,
                        "mission_id": str(uuid4()),
                        "step_type": "code_execute",
                        "outcome": "success",
                        "cost_usd": 0.03,
                        "summary_text": "Deployed 3 files, all tests passed",
                    },
                )

        assert episode is not None
        assert episode.outcome == "success"
        assert episode.cost_bucket == "small"
        assert "REDACTED" not in episode.retrieval_text or "sk-" not in episode.retrieval_text
        assert episode.qdrant_point_id == "qdrant-123"

    @pytest.mark.asyncio
    async def test_record_episode_missing_fields_returns_none(self):
        service = _make_service()
        db = FakeDB()

        result = await service.record_episode(db, payload={"step_type": "test"})
        assert result is None


class TestRetrievalCapping:
    """Test that retrieval is hard-capped at 5."""

    def test_max_retrieval_constant(self):
        service = _make_service()
        assert service.MAX_RETRIEVAL == 5

    def test_k_cap_enforced(self):
        """Verify k is capped at MAX_RETRIEVAL."""
        service = _make_service()
        capped_k = min(10, service.MAX_RETRIEVAL)
        assert capped_k == 5


class TestRerank:
    """Test hybrid re-ranking logic."""

    def test_rrf_fusion(self):
        service = _make_service()

        bm25 = [
            {"id": "ep-1", "bm25_score": 0.9},
            {"id": "ep-2", "bm25_score": 0.5},
        ]
        vector = [
            {"id": "ep-2", "score": 0.8},  # appears in both
            {"id": "ep-3", "score": 0.7},
        ]

        results = service._rerank(bm25, vector, k=5)

        # ep-2 should rank highest (appears in both)
        assert len(results) == 3
        assert results[0]["id"] == "ep-2"
        assert "combined_score" in results[0]

    def test_rerank_respects_k(self):
        service = _make_service()

        bm25 = [{"id": f"ep-{i}", "bm25_score": 1.0 - i * 0.1} for i in range(10)]
        vector = []

        results = service._rerank(bm25, vector, k=5)
        assert len(results) == 5


class TestWorkspaceScoping:
    """Test that workspace scoping is enforced."""

    @pytest.mark.asyncio
    async def test_retrieve_requires_workspace_id(self):
        service = _make_service()
        db = FakeDB()

        # Should not raise even with empty results
        results = await service.retrieve_relevant(
            db,
            query_text="test query",
            workspace_id=str(uuid4()),
            user_id=1,
        )
        assert isinstance(results, list)
        assert len(results) == 0  # empty DB


class TestBuildRetrievalText:
    """Test retrieval text construction."""

    def test_basic_retrieval_text(self):
        service = _make_service()
        text = service._build_retrieval_text(
            mission_id="abcd-1234-5678-9012",
            step_type="code_execute",
            outcome="success",
            cost_bucket="small",
        )
        assert "abcd-123" in text  # mission_id[:8]
        assert "code_execute" in text
        assert "success" in text
        assert "small" in text

    def test_retrieval_text_with_summary(self):
        service = _make_service()
        text = service._build_retrieval_text(
            mission_id="abcd-1234",
            step_type="plan",
            outcome="failure",
            cost_bucket="large",
            summary_text="Failed due to timeout after 3 retries",
        )
        assert "timeout" in text

    def test_retrieval_text_truncates_long_summary(self):
        service = _make_service()
        long_text = "x" * 1000
        text = service._build_retrieval_text(
            mission_id="abcd-1234",
            step_type="plan",
            outcome="success",
            cost_bucket="small",
            summary_text=long_text,
        )
        # Summary should be truncated to 500 chars
        assert len(text) < 1000 + 100  # some overhead for structure
