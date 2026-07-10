"""Q3 — skill architecture unit tests (DB-free where possible).

Covers:
* Q3-A: ``Skill`` model shape (columns, unique index, types).
* Q3-D: progressive disclosure helpers ``normalize_skill_name`` + service
  list/view separation.
* Q3-E: ``evaluate_skill_write`` PATCH>ADD>CREATE guard (name, regex, cap,
  cosine similarity) — the pure, deterministic core.
* Q3-B: reviewer response parsing of ``proposed_skills`` into
  ``SkillProposedWrite`` (whitelist + bounds).
* Q3-C: governance parity via ``SkillsService.apply_skill_write`` trust
  tier mapping + poison-scan invocation (using a fake async session).

Mirrors the in-process, mock-driven style of ``test_background_review.py``
— no live Postgres required.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.skill_models import ALL_SKILL_PROVENANCE, ALL_SKILL_TRUST_TIERS, Skill
from app.services.memory.background_review_prompt import (
    REVIEWER_ACTION_TO_DB_ACTION,
    REVIEWER_ACTION_TO_WRITE_TYPE,
    REVIEWER_TOOL_WHITELIST,
)
from app.services.memory.background_review_service import (
    BackgroundReviewService,
    SkillProposedWrite,
)
from app.services.skills_service import (
    SkillsService,
    cosine_similarity,
    evaluate_skill_write,
    normalize_skill_name,
    trust_tier_for_provenance,
)

# ── Q3-A: model shape ──────────────────────────────────────────────────────


def test_skill_model_columns_present():
    cols = set(Skill.__table__.columns.keys())
    expected = {
        "id",
        "name",
        "body",
        "frontmatter",
        "trust_tier",
        "version",
        "provenance",
        "workspace_id",
        "user_id",
        "agent_id",
        "created_at",
        "updated_at",
    }
    assert expected <= cols

    # workspace_id is NOT NULL (isolation guardrail).
    ws_col = Skill.__table__.columns["workspace_id"]
    assert ws_col.nullable is False
    # agent_id is nullable (NULL = human-authored).
    assert Skill.__table__.columns["agent_id"].nullable is True


def test_skill_name_unique_per_workspace_index():
    # The unique index ix_skills_workspace_name enforces class-level names.
    idx_names = [ix.name for ix in Skill.__table__.indexes]
    assert "ix_skills_workspace_name" in idx_names


# ── Q3-D: progressive disclosure helpers ───────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("deploy-backend", "deploy-backend"),
        ("Deploy Backend", "Deploy_Backend"),
        ("  run-tests  ", "run-tests"),
        ("my-skill_2026-07-10", None),  # date suffix rejected
        ("fix-task-123", None),  # task suffix rejected
        ("pr_42", None),  # pr suffix rejected
        ("", None),
        ("   ", None),
        ("x" * 500, "x" * 128),  # truncated
    ],
)
def test_normalize_skill_name(raw, expected):
    assert normalize_skill_name(raw) == expected


def test_cosine_similarity_basic():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0]) == 0.0  # length mismatch


def test_trust_tier_for_provenance():
    assert trust_tier_for_provenance("user") == "curated"
    assert trust_tier_for_provenance("agent") == "unverified"
    assert trust_tier_for_provenance("third_party") == "unverified"
    assert trust_tier_for_provenance("garbage") == "unverified"


# ── Q3-E: PATCH > ADD > CREATE guard ───────────────────────────────────────


async def test_evaluate_existing_name_is_patch():
    dec = await evaluate_skill_write(
        raw_name="deploy-backend",
        action="add",
        existing_names=["deploy-backend"],
        per_workspace_count=3,
    )
    assert dec.outcome == "patch"
    assert dec.skill_name == "deploy-backend"


async def test_evaluate_rejects_date_suffix_name():
    dec = await evaluate_skill_write(
        raw_name="deploy-2026-07-10",
        action="add",
        existing_names=[],
        per_workspace_count=0,
    )
    assert dec.outcome == "reject"


async def test_evaluate_rejects_per_workspace_cap():
    dec = await evaluate_skill_write(
        raw_name="new-skill",
        action="add",
        existing_names=["a", "b"],
        per_workspace_count=200,
    )
    assert dec.outcome == "reject"
    assert "cap" in dec.reason


async def test_evaluate_create_passes_guards_without_embed():
    dec = await evaluate_skill_write(
        raw_name="new-skill",
        action="add",
        existing_names=["other-skill"],
        per_workspace_count=1,
    )
    assert dec.outcome == "create"


async def test_evaluate_rejects_similar_create_via_embedding():
    # Deterministic embed_fn: identical vectors -> cosine 1.0.
    def emb(texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    dec = await evaluate_skill_write(
        raw_name="deploy-backend",
        action="add",
        existing_names=["deploy_backend"],
        existing_descriptions=["deploys the backend image"],
        per_workspace_count=1,
        embed_fn=emb,
        threshold=0.85,
    )
    assert dec.outcome == "reject"
    assert dec.suggested_action == "patch"


async def test_evaluate_create_with_dissimilar_embedding_passes():
    # Query vector orthogonal to the single existing skill's vector -> cosine 0.0.
    def emb(texts):
        # texts[0] is the query, texts[1] is the existing skill.
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

    dec = await evaluate_skill_write(
        raw_name="deploy-backend",
        action="add",
        existing_names=["unrelated-skill"],
        existing_descriptions=["does something completely different"],
        per_workspace_count=1,
        embed_fn=emb,
        threshold=0.85,
    )
    assert dec.outcome == "create"


async def test_evaluate_async_embed_fn_supported():
    async def emb(texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    dec = await evaluate_skill_write(
        raw_name="deploy-backend",
        action="add",
        existing_names=["deploy_backend"],
        per_workspace_count=1,
        embed_fn=emb,
    )
    assert dec.outcome == "reject"
    assert dec.suggested_action == "patch"


# ── Q3-B: reviewer skill parsing ───────────────────────────────────────────


def test_parse_reviewer_skills_extracts_valid():
    raw = (
        "{"
        '"reasoning": "x",'
        '"proposed_skills": ['
        '{"action": "skill_create", "name": "deploy-backend",'
        ' "body": "run the deploy script",'
        ' "frontmatter": {"description": "deploys backend"},'
        ' "source_type": "agent"},'
        '{"action": "skill_patch", "name": "run-tests",'
        ' "body": "run the test suite", "source_type": "tool_output"}'
        "]"
        "}"
    )
    svc = BackgroundReviewService()
    out = svc.parse_reviewer_skills(raw)
    assert len(out) == 2
    assert all(isinstance(s, SkillProposedWrite) for s in out)
    assert out[0].name == "deploy-backend"
    assert out[0].action == "add"  # skill_create -> add
    assert out[1].action == "replace"  # skill_patch -> replace


def test_parse_reviewer_skills_drops_non_whitelisted_and_bad_names():
    raw = (
        "{"
        '"proposed_skills": ['
        '{"action": "memory_add", "name": "x", "body": "y"},'  # wrong whitelist
        '{"action": "skill_create", "name": "task-123", "body": "y"},'  # date/task name
        '{"action": "skill_create", "name": "ok", "body": "short body"}'  # valid (>MIN_CHARS)
        "]"
        "}"
    )
    svc = BackgroundReviewService()
    out = svc.parse_reviewer_skills(raw)
    assert len(out) == 1
    assert out[0].name == "ok"


def test_reviewer_whitelist_includes_skills():
    assert "skill_create" in REVIEWER_TOOL_WHITELIST
    assert "skill_patch" in REVIEWER_TOOL_WHITELIST
    assert REVIEWER_ACTION_TO_DB_ACTION["skill_create"] == "add"
    assert REVIEWER_ACTION_TO_DB_ACTION["skill_patch"] == "replace"
    assert REVIEWER_ACTION_TO_WRITE_TYPE["skill_create"] == "skill"
    assert REVIEWER_ACTION_TO_WRITE_TYPE["skill_patch"] == "skill"


# ── Q3-C: governance parity via SkillsService.apply_skill_write ───────────


class _FakeSkillSession:
    """Minimal async session double for SkillsService CRUD."""

    def __init__(self, rows: list | None = None):
        self._rows = list(rows or [])
        self.added: list[Skill] = []
        self.flushed = 0
        self.execute = AsyncMock()

        async def _exec(stmt):
            # SELECT(Skill) -> return the in-memory rows.
            result = MagicMock()
            result.scalars.return_value.all.return_value = list(self._rows)
            result.scalar_one_or_none.return_value = self._rows[0] if self._rows else None
            return result

        self.execute.side_effect = _exec
        self.add = MagicMock(side_effect=lambda obj: self.added.append(obj))
        self.flush = AsyncMock(side_effect=lambda: self._increment())

    def _increment(self):
        self.flushed += 1


async def test_skills_service_create_lands_in_table():
    session = _FakeSkillSession()
    svc = SkillsService(session)
    sid = await svc.apply_skill_write(
        workspace_id="ws-1",
        user_id=1,
        raw_name="deploy-backend",
        body="run deploy script",
        frontmatter={"description": "deploys backend"},
        provenance="agent",
        agent_id="agent-9",
        action="add",
    )
    assert sid is not None
    assert len(session.added) == 1
    sk: Skill = session.added[0]
    assert sk.name == "deploy-backend"
    assert sk.workspace_id == "ws-1"
    assert sk.user_id == 1
    assert sk.agent_id == "agent-9"
    assert sk.trust_tier == "unverified"  # GOV-1.2: agent provenance -> unverified
    assert sk.version == 1


async def test_skills_service_patch_bumps_version_and_history():
    existing = Skill(
        id="s-1",
        name="deploy-backend",
        body="old body",
        frontmatter={"description": "d"},
        trust_tier="unverified",
        version=1,
        provenance="agent",
        workspace_id="ws-1",
        user_id=1,
    )
    session = _FakeSkillSession(rows=[existing])
    svc = SkillsService(session)
    sid = await svc.apply_skill_write(
        workspace_id="ws-1",
        user_id=1,
        raw_name="deploy-backend",  # same name -> PATCH
        body="new body",
        frontmatter={"description": "d"},
        provenance="agent",
        agent_id="agent-9",
        action="add",
    )
    assert sid == "s-1"
    assert existing.version == 2
    assert existing.body == "new body"
    hist = (existing.frontmatter or {}).get("history", [])
    assert hist
    assert hist[0]["body"] == "old body"


async def test_skills_service_rejects_when_guard_blocks():
    # A near-duplicate name under the cap: with an embed_fn the CREATE
    # would be rejected; here we simulate the cap being exceeded.
    rows = [
        Skill(
            id=f"e-{i}",
            name=f"skill-{i}",
            body="b",
            trust_tier="unverified",
            version=1,
            provenance="agent",
            workspace_id="ws-1",
            user_id=1,
        )
        for i in range(200)
    ]
    session = _FakeSkillSession(rows=rows)
    svc = SkillsService(session)
    sid = await svc.apply_skill_write(
        workspace_id="ws-1",
        user_id=1,
        raw_name="brand-new-skill",
        body="a brand new procedure",
        frontmatter={"description": "new"},
        provenance="agent",
        agent_id=None,
        action="add",
    )
    assert sid is None  # rejected by per-workspace cap
    assert session.add.call_count == 0


async def test_skills_service_refuses_missing_workspace():
    session = _FakeSkillSession()
    svc = SkillsService(session)
    sid = await svc.apply_skill_write(
        workspace_id=None,
        user_id=1,
        raw_name="deploy-backend",
        body="b",
        frontmatter={},
        provenance="agent",
        agent_id=None,
        action="add",
    )
    assert sid is None
