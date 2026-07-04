"""Tests for AutoMem Phase 2 — scaffold proposals, meta review, and validation.

Tests follow the pattern from test_memory_actions.py and test_background_review.py.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.scaffold_models import (
    ALL_SCAFFOLD_PROPOSAL_STATUSES,
    ScaffoldProposal,
    ScaffoldProposalStatus,
    ScaffoldVersion,
)

# ── Model tests ───────────────────────────────────────────────────────


class TestScaffoldProposalStatus:
    def test_all_statuses(self):
        assert len(ALL_SCAFFOLD_PROPOSAL_STATUSES) == 4

    def test_pending(self):
        assert ScaffoldProposalStatus.PENDING == "pending"

    def test_approved(self):
        assert ScaffoldProposalStatus.APPROVED == "approved"

    def test_rejected(self):
        assert ScaffoldProposalStatus.REJECTED == "rejected"

    def test_applied(self):
        assert ScaffoldProposalStatus.APPLIED == "applied"


class TestScaffoldProposalModel:
    def test_table_name(self):
        assert ScaffoldProposal.__tablename__ == "scaffold_proposals"

    def test_has_required_columns(self):
        columns = {c.name for c in ScaffoldProposal.__table__.columns}
        required = {
            "id",
            "agent_id",
            "current_prompt_hash",
            "proposed_prompt",
            "reasoning",
            "changes_summary",
            "expected_impact",
            "validation_metrics",
            "status",
            "reviewed_at",
            "reviewed_by",
            "applied_at",
            "applied_version_id",
            "trace_count",
            "meta_model",
        }
        assert required.issubset(columns)

    def test_indexes_defined(self):
        index_names = [idx.name for idx in ScaffoldProposal.__table__.indexes]
        assert "ix_scaffold_proposals_agent_status" in index_names
        assert "ix_scaffold_proposals_status_created" in index_names


class TestScaffoldVersionModel:
    def test_table_name(self):
        assert ScaffoldVersion.__tablename__ == "scaffold_versions"

    def test_has_required_columns(self):
        columns = {c.name for c in ScaffoldVersion.__table__.columns}
        required = {
            "id",
            "agent_id",
            "version",
            "prompt_text",
            "is_active",
            "source_proposal_id",
            "parent_version_id",
        }
        assert required.issubset(columns)

    def test_indexes_defined(self):
        index_names = [idx.name for idx in ScaffoldVersion.__table__.indexes]
        assert "ix_scaffold_versions_agent_version" in index_names
        assert "ix_scaffold_versions_agent_active" in index_names


# ── Trace export tests ────────────────────────────────────────────────


class TestTraceExportService:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    def test_importable(self):
        from app.services.memory.trace_export_service import TraceExportService

        assert TraceExportService is not None


# ── Meta review service tests ─────────────────────────────────────────


class TestMetaReviewService:
    def test_importable(self):
        from app.services.memory.meta_review_service import MetaReviewService

        assert MetaReviewService is not None

    def test_scaffold_proposal_result(self):
        from app.services.memory.meta_review_service import ScaffoldProposalResult

        result = ScaffoldProposalResult(
            success=True,
            reasoning="test",
            proposed_prompt="new prompt",
            confidence=0.8,
            soundness=0.9,
        )
        assert result.success is True
        assert result.confidence == 0.8

    def test_parse_response_direct_json(self):
        from app.services.memory.meta_review_service import MetaReviewService

        service = MetaReviewService.__new__(MetaReviewService)
        parsed = service._parse_response(
            json.dumps(
                {
                    "reasoning": "test",
                    "proposed_prompt": "new prompt",
                    "confidence": 0.8,
                }
            )
        )
        assert parsed is not None
        assert parsed["reasoning"] == "test"

    def test_parse_response_fenced_block(self):
        from app.services.memory.meta_review_service import MetaReviewService

        service = MetaReviewService.__new__(MetaReviewService)
        raw = 'Here is the result:\n```json\n{"reasoning": "test", "proposed_prompt": "new"}\n```\nDone.'
        parsed = service._parse_response(raw)
        assert parsed is not None
        assert parsed["reasoning"] == "test"

    def test_parse_response_invalid(self):
        from app.services.memory.meta_review_service import MetaReviewService

        service = MetaReviewService.__new__(MetaReviewService)
        parsed = service._parse_response("not json at all")
        assert parsed is None


# ── Validation harness tests ──────────────────────────────────────────


class TestValidationHarness:
    def test_importable(self):
        from app.services.memory.validation_harness import ValidationHarness

        assert ValidationHarness is not None

    def test_validation_metrics_to_dict(self):
        from app.services.memory.validation_harness import ValidationMetrics

        metrics = ValidationMetrics(
            approved=True,
            confidence_score=0.8,
            soundness_score=0.9,
            risk_assessment="low",
            reasoning="looks good",
            concerns=["minor issue"],
        )
        d = metrics.to_dict()
        assert d["approved"] is True
        assert d["confidence_score"] == 0.8
        assert d["concerns"] == ["minor issue"]

    def test_parse_response_direct_json(self):
        from app.services.memory.validation_harness import ValidationHarness

        harness = ValidationHarness.__new__(ValidationHarness)
        parsed = harness._parse_response(
            json.dumps(
                {
                    "approved": True,
                    "confidence_score": 0.9,
                    "soundness_score": 0.8,
                    "risk_assessment": "low",
                    "reasoning": "good",
                }
            )
        )
        assert parsed is not None
        assert parsed["approved"] is True


# ── Prompt template tests ─────────────────────────────────────────────


class TestMetaReviewPrompt:
    def test_build_traces_text(self):
        from app.services.memory.meta_review_prompt import build_traces_text

        traces = [
            {
                "title": "Test Mission",
                "success": True,
                "memory_actions": [
                    {"action_type": "recall_episodic"},
                    {"action_type": "log_observation"},
                ],
                "memory_proficiency": {"total_actions": 2, "successful": 2},
            },
        ]
        text = build_traces_text(traces)
        assert "Test Mission" in text
        assert "SUCCESS" in text
        assert "recall_episodic" in text

    def test_build_traces_text_empty(self):
        from app.services.memory.meta_review_prompt import build_traces_text

        text = build_traces_text([])
        assert text == ""

    def test_constants_defined(self):
        from app.services.memory.meta_review_prompt import (
            DEFAULT_META_MODEL,
            MAX_PROPOSED_PROMPT_CHARS,
            META_REVIEW_SYSTEM_PROMPT,
            META_REVIEW_USER_PROMPT,
            MIN_TRACES_FOR_REVIEW,
        )

        assert MIN_TRACES_FOR_REVIEW == 5
        assert MAX_PROPOSED_PROMPT_CHARS == 8000
        assert DEFAULT_META_MODEL == "llamacpp-qwen3.6-27b"
        assert len(META_REVIEW_SYSTEM_PROMPT) > 100
        assert len(META_REVIEW_USER_PROMPT) > 100


# ── Celery task tests ─────────────────────────────────────────────────


class TestMetaReviewTask:
    def test_task_importable(self):
        from app.tasks.meta_review_tasks import review_scaffold

        assert review_scaffold is not None

    def test_task_name(self):
        from app.tasks.meta_review_tasks import review_scaffold

        assert review_scaffold.name == "app.tasks.meta_review_tasks.review_scaffold"


# ── API endpoint tests ────────────────────────────────────────────────


class TestScaffoldAPI:
    def test_router_importable(self):
        from app.api.v1.scaffolds import router

        assert router.prefix == "/scaffolds"

    def test_endpoint_count(self):
        from app.api.v1.scaffolds import router

        routes = [r for r in router.routes if hasattr(r, "methods")]
        assert len(routes) == 6  # list, get, approve, reject, versions, rollback

    def test_endpoint_paths(self):
        from app.api.v1.scaffolds import router

        paths = {r.path for r in router.routes if hasattr(r, "path")}
        assert any("proposals" in p for p in paths)
        assert any("versions" in p for p in paths)
