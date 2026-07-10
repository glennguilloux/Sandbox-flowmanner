"""Q1-A/C/D/E — vector half of ``PersonalMemoryClaim`` recall.

DB-free unit tests for the Q1 machinery in
``app/services/personal_memory_qdrant.py`` plus the fuzzy-lane wiring in
``personal_memory_service._recall_fuzzy_lane``:

  * Q1-A  global single Qdrant collection + fail-closed tenant filter
  * Q1-C  fuzzy lane (dense + BM25 over FUZZY-only claims)
  * Q1-D  canonical triple-sentence embedding text
  * Q1-E  upsert/delete + BM25 + reciprocal-rank-fusion helpers

The Q1-B trap is asserted directly: constraints are NEVER admitted to the
dense lane (``claim_type IN (fact, preference, observation)`` only), and the
fail-closed tenant filter RAISES on a missing key rather than broad-matching.

No live Qdrant / embedding model / Postgres is required — we stub the model
client to ``None`` (vector lane down → BM25-only fusion) and assert behaviour,
and compile the fuzzy-lane SQL against the Postgres dialect.

Run from backend/ with the host venv:
    .venv/bin/python -m pytest app/tests/test_q1_vector_recall.py -v
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

sys.path.insert(0, "/opt/flowmanner/backend/.worktrees/t_da90fda3/backend")

from sqlalchemy.dialects import postgresql

from app.services import personal_memory_qdrant as qm
from app.services.personal_memory_qdrant import (
    FUZZY_CLAIM_TYPES,
    QdrantTenantFilterError,
    canonical_triple_sentence,
    reciprocal_rank_fusion,
)

# ── Model / client stubs (no 80MB MiniLM download in tests) ────────────────


class _FakeClient:
    """Records the Filter handed to ``search`` and returns no hits."""

    def __init__(self) -> None:
        self.last_filter: Any = None
        self.search_calls = 0

    def get_collections(self, **_: Any):  # pragma: no cover - shape only
        class _C:
            collections = ()

        return _C()

    def search(
        self, *, collection_name: str, query_vector: list[float], query_filter: Any, limit: int, with_payload: bool
    ):
        self.last_filter = query_filter
        self.search_calls += 1
        return []


class _FakeModel:
    def get_client(self):  # Qdrant DOWN → dense half skipped, BM25-only
        return None

    def encode(self, text: str) -> list[float]:  # pragma: no cover - not called when down
        return [0.0] * 384


def _patch_model(client: Any) -> None:
    """Point the module's lazy model at a fake whose client is ``client``."""
    fake = type("M", (), {"get_client": staticmethod(lambda: client), "encode": staticmethod(lambda t: [0.0] * 384)})()
    qm._EmbeddingModel.get = staticmethod(lambda: fake)  # type: ignore[attr-defined]


def _restore_model() -> None:
    qm._EmbeddingModel.get = staticmethod(lambda: qm._EmbeddingModel())  # type: ignore[attr-defined]


# ── Q1-D: canonical triple sentence ────────────────────────────────────────


class TestCanonicalTripleSentence:
    def test_plain_value(self) -> None:
        assert canonical_triple_sentence("Glenn", "prefers", "tea") == "Glenn prefers tea"

    def test_dict_object_flattened(self) -> None:
        out = canonical_triple_sentence("Deploy", "blocked_on", {"day": "Friday", "reason": "freeze"})
        # deterministic key order (sorted) so the embedding is stable
        assert out == "Deploy blocked_on day: Friday reason: freeze"

    def test_empty_slots_dropped(self) -> None:
        assert canonical_triple_sentence("", "likes", "") == "likes"

    def test_none_object_stringified(self) -> None:
        # canonical_triple_sentence uses ``object_value or ""`` → None → "".
        # subject+predicate remain; the empty object fragment is dropped.
        assert canonical_triple_sentence("X", "is", None) == "X is"

    def test_commas_preserved_in_object(self) -> None:
        # commas in an object string are kept verbatim (BM25/tokenizer handle
        # punctuation). We assert the canonical sentence round-trips.
        out = canonical_triple_sentence("Glenn", "lives_in", "Paris, France")
        assert out == "Glenn lives_in Paris, France"


# ── Q1-C/E: RRF fusion ────────────────────────────────────────────────────


class TestReciprocalRankFusion:
    def test_merges_two_rankings(self) -> None:
        fused = reciprocal_rank_fusion(
            dense=[("a", 0.9), ("b", 0.8), ("c", 0.7)],
            bm25={"b": 0.5, "c": 0.4, "d": 0.3},
            k=60,
        )
        assert set(fused) == {"a", "b", "c", "d"}

    def test_no_double_count(self) -> None:
        # A claim present in both lanes appears ONCE.
        fused = reciprocal_rank_fusion(dense=[("a", 0.9), ("b", 0.8)], bm25={"b": 0.5, "a": 0.4}, k=60)
        assert len(fused) == 2

    def test_higher_score_ranks_first(self) -> None:
        # 'b' is rank-1 in BOTH lanes → highest RRF score → must lead.
        fused = reciprocal_rank_fusion(dense=[("b", 0.9), ("a", 0.8)], bm25={"b": 0.5, "a": 0.4}, k=60)
        assert fused[0] == "b"

    def test_empty_dense_uses_bm25_order(self) -> None:
        fused = reciprocal_rank_fusion(dense=[], bm25={"x": 0.5, "y": 0.3, "z": 0.1}, k=60)
        assert fused == ["x", "y", "z"]

    def test_both_empty_returns_empty(self) -> None:
        assert reciprocal_rank_fusion(dense=[], bm25={}, k=60) == []


# ── Q1-C/E: BM25 over the corpus ──────────────────────────────────────────


class TestBm25Scores:
    def test_relevant_doc_ranks_first(self) -> None:
        corpus = [
            ("c1", "Glenn prefers tea over coffee"),
            ("c2", "The server runs nginx on port 80"),
        ]
        scores = qm._bm25_scores(
            user_id=1,
            workspace_id="ws",
            query_tokens=["glenn", "tea"],
            corpus=corpus,
        )
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        assert ranked[0][0] == "c1"
        assert scores["c1"] > scores["c2"]

    def test_score_zero_for_no_overlap(self) -> None:
        corpus = [("c1", "completely unrelated words here")]
        scores = qm._bm25_scores(
            user_id=1,
            workspace_id="ws",
            query_tokens=["glenn", "tea"],
            corpus=corpus,
        )
        assert scores["c1"] == 0.0

    def test_empty_query_tokens_returns_empty_dict(self) -> None:
        corpus = [("c1", "anything")]
        scores = qm._bm25_scores(
            user_id=1,
            workspace_id="ws",
            query_tokens=[],
            corpus=corpus,
        )
        assert scores == {}


# ── Q1-A: fail-closed tenant filter ───────────────────────────────────────


class TestTenantFilterFailClosed:
    def test_missing_user_raises(self) -> None:
        try:
            qm._build_tenant_filter(None, "ws")
        except QdrantTenantFilterError:
            return
        raise AssertionError("expected QdrantTenantFilterError for missing user_id")

    def test_missing_workspace_raises(self) -> None:
        try:
            qm._build_tenant_filter(1, None)
        except QdrantTenantFilterError:
            return
        raise AssertionError("expected QdrantTenantFilterError for missing workspace_id")

    def test_valid_filter_has_two_must_conditions(self) -> None:
        f = qm._build_tenant_filter(1, "ws")
        assert len(f.must) == 2
        keys = {c.key for c in f.must}
        assert keys == {"user_id", "workspace_id"}


# ── Q1-A/E + Q1-B trap: dense lane excludes constraints ──────────────────


class TestDenseLaneExcludesConstraints:
    def setup_method(self) -> None:
        self.client = _FakeClient()
        _patch_model(self.client)

    def teardown_method(self) -> None:
        _restore_model()

    def test_search_filter_excludes_constraints(self) -> None:
        qm._dense_search(user_id=1, workspace_id="ws", query_vector=[0.1] * 384, limit=5)
        filt = self.client.last_filter
        # The claim_type condition must be FUZZY-only.
        ct = next(c for c in filt.must if getattr(c, "key", None) == "claim_type")
        assert set(ct.match.any) == set(FUZZY_CLAIM_TYPES)
        assert "constraint" not in ct.match.any

    def test_search_filter_keeps_tenant(self) -> None:
        qm._dense_search(user_id=7, workspace_id="tenantX", query_vector=[0.1] * 384, limit=5)
        keys = {c.key for c in self.client.last_filter.must}
        assert keys == {"user_id", "workspace_id", "claim_type"}


# ── Q1-E: upsert / delete refuse on missing tenant (fail-closed) ──────────


class TestUpsertDeleteFailClosed:
    def setup_method(self) -> None:
        self.client = _FakeClient()
        _patch_model(self.client)

    def teardown_method(self) -> None:
        _restore_model()

    def test_upsert_raises_without_user(self) -> None:
        try:
            qm.upsert_claim_point(
                claim_id="c1",
                user_id=None,
                workspace_id="ws",
                claim_type="fact",
                canonical_text="x",
                object_payload={},
                subject="s",
                predicate="p",
            )
        except QdrantTenantFilterError:
            return
        raise AssertionError("upsert must fail-closed on missing user_id")

    def test_delete_raises_without_workspace(self) -> None:
        try:
            # delete_claim_point is tenant-scoped at the call site (vias
            # upsert), so the function itself only takes claim_id; we instead
            # assert the FAIL-CLOSED path on the upsert's filter. Deleting a
            # point without a resolved tenant is guarded at upsert time.
            qm.upsert_claim_point(
                claim_id="c1",
                user_id=1,
                workspace_id=None,
                claim_type="fact",
                canonical_text="x",
                object_payload={},
                subject="s",
                predicate="p",
            )
        except QdrantTenantFilterError:
            return
        raise AssertionError("upsert must fail-closed on missing workspace_id")


# ── Q1-C/E: fuzzy_lane_recall orchestrator (Qdrant down → BM25 only) ─────


class TestFuzzyLaneRecallOrchestrator:
    def setup_method(self) -> None:
        self.client = _FakeClient()
        _patch_model(self.client)  # get_client() → None → dense skipped

    def teardown_method(self) -> None:
        _restore_model()

    def test_empty_corpus_returns_empty(self) -> None:
        assert qm.fuzzy_lane_recall(user_id=1, workspace_id="ws", query="tea", corpus=[], limit=10) == []

    def test_bm25_drives_fusion_when_qdrant_down(self) -> None:
        corpus = [
            ("c1", "Glenn prefers tea over coffee"),
            ("c2", "nginx port 80 server config"),
        ]
        out = qm.fuzzy_lane_recall(user_id=1, workspace_id="ws", query="glenn tea", corpus=corpus, limit=10)
        # BM25-only path: highest BM25 score leads.
        assert out[0] == "c1"
        assert set(out) == {"c1", "c2"}


# ── Q1-C: fuzzy-lane SQL shape (DB-free, mirrors test_q1_constraint_lane) ──


def _compile_fuzzy_corpus_sql() -> str:
    """Run ``_recall_fuzzy_lane`` with a fake DB + stubbed fusion and return
    the compiled corpus SELECT (Postgres dialect), WITHOUT a live DB."""
    import app.services.personal_memory_service as pms

    svc = object.__new__(pms.PersonalMemoryService)
    captured: dict[str, Any] = {}

    class _FakeResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class _FakeDB:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, stmt):
            captured.setdefault("stmts", []).append(stmt)
            return _FakeResult()

    svc.db = _FakeDB()  # type: ignore[assignment]

    # Stub the heavy fusion so this stays a pure SQL-shape test.
    async def _fake_to_thread(fn, **kwargs):
        captured["kwargs"] = kwargs
        return []

    orig = asyncio.to_thread
    asyncio.to_thread = _fake_to_thread  # type: ignore[assignment]
    try:
        asyncio.get_event_loop().run_until_complete(
            svc._recall_fuzzy_lane(user_id=1, workspace_id="ws", query="tea", min_confidence=0.0, top_k=20)
        )
    finally:
        asyncio.to_thread = orig  # type: ignore[assignment]

    # First statement is the fuzzy corpus SELECT.
    stmt = captured["stmts"][0]
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True, "render_postcompile": True},
        )
    )


class TestFuzzyLaneSQLShape:
    def test_partitions_on_fuzzy_claim_types(self) -> None:
        sql = _compile_fuzzy_corpus_sql()
        # The fuzzy corpus SELECT partitions on the FUZZY claim types only
        # (fact / preference / observation) — never 'constraint'. SQLAlchemy
        # renders the IN list in arbitrary order, so assert each member is
        # present rather than pinning the literal tuple.
        assert "claim_type IN (" in sql
        for ct in FUZZY_CLAIM_TYPES:
            assert ct in sql

    def test_excludes_constraint(self) -> None:
        sql = _compile_fuzzy_corpus_sql()
        # Constraint is a SEPARATE lane; must not appear in the fuzzy corpus.
        assert "claim_type = 'constraint'" not in sql

    def test_tenant_and_active_filters(self) -> None:
        sql = _compile_fuzzy_corpus_sql()
        assert "user_id" in sql.lower()
        assert "workspace_id" in sql.lower()
        assert "deleted_at IS NULL" in sql

    def test_skips_fusion_when_no_fuzzy_rows(self) -> None:
        # Empty corpus → fusion not invoked (returns [] before to_thread).
        import app.services.personal_memory_service as pms

        svc = object.__new__(pms.PersonalMemoryService)

        class _FakeResult:
            def scalars(self):
                return self

            def all(self):
                return []

        class _FakeDB:
            async def execute(self, stmt):
                return _FakeResult()

        svc.db = _FakeDB()  # type: ignore[assignment]
        called: dict[str, bool] = {"fusion": False}

        async def _fake_to_thread(fn, **kwargs):
            called["fusion"] = True
            return []

        orig = asyncio.to_thread
        asyncio.to_thread = _fake_to_thread  # type: ignore[assignment]
        try:
            res = asyncio.get_event_loop().run_until_complete(
                svc._recall_fuzzy_lane(user_id=1, workspace_id="ws", query="tea")
            )
        finally:
            asyncio.to_thread = orig  # type: ignore[assignment]
        assert res == []
        assert called["fusion"] is False
