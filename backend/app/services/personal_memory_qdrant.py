"""Q1 vector half — Qdrant wrapper for ``PersonalMemoryClaim`` embeddings.

This module is the **single** home for the Q1-A / Q1-C / Q1-D / Q1-E vector
machinery for personal memory. It is deliberately *independent of the
competitive `recall()` SQL lane* and of the Q1-B constraint lane:

* Q1-A — one GLOBAL Qdrant collection for personal-memory claims (NOT
  per-workspace). Payload indexes on ``user_id``, ``workspace_id``,
  ``claim_type``. **Fail-closed tenant filter**: ``must={user_id,
  workspace_id}``; the wrapper RAISES if either key is missing. We mirror
  the production SQL WHERE in ``PersonalMemoryService.recall`` — broad
  match on a missing key is a security incident, never a silent fallback.
* Q1-C — fuzzy lane for ``fact`` / ``preference`` / ``observation`` claims:
  dense embedding (the shared ``all-MiniLM-L6-v2`` 384d model, loaded
  ONCE process-wide — see ``_EmbeddingModel``) + BM25 over canonical text,
  merged via Reciprocal Rank Fusion ``Σ 1/(k+rank)``. **Constraints never
  enter the dense or RRF lanes** — they live only in the Q1-B SQL lane.
* Q1-D — we embed the *canonical triple sentence* (e.g. ``"prefers theme:
  dark"``), NOT the raw ``object`` JSONB. The ``object`` JSONB is kept in
  the Qdrant payload for exact filtering + constraint matching.
* Q1-E — each claim belongs to exactly one lane (partition on
  ``claim_type``); union by ``claim_id`` is therefore dedup-safe, no
  double-count (enforced by the caller in ``recall``).

## Infra dependency (read before running in prod)

The collection is provisioned idempotently (``recreate=False``) on first
use if it does not exist. If Qdrant is unreachable from the worker, every
*operation* degrades gracefully (returns ``None`` / ``[]`` / skips the
upsert) — recall still works via the SQL + Q1-B lanes. The **fail-closed
tenant filter is the one hard exception**: it raises before any network
call, so a misconfigured missing-key call can never produce a broad query.

Live-provisioning note for Glenn: the collection is created automatically
the first time any claim is upserted OR the first time ``recall`` runs the
fuzzy lane. No manual ``create_collection`` step is required. The model
weights are pulled from the HuggingFace hub on first embed if not cached;
in the Docker image they must be present at build time (see requirements).
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

# ── Constants (single source of truth; reuse to avoid drift) ───────────────

# One GLOBAL collection (not per-workspace) — see Q1-A.
PERSONAL_MEMORY_COLLECTION = "personal_memory_claims"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2

# Reciprocal Rank Fusion constant. k=60 is the classic (Cormack et al.)
# value; large enough that a rank-1 in either list is never swamped by a
# slightly-better-ranked neighbour, small enough to keep the fusion convex.
RRF_K = 60

# Claim types eligible for the dense / BM25 / RRF fuzzy lane. Constraints are
# EXCLUDED by design (Q1-B trap): they are retrieved only by the exact/lexical
# SQL lane in ``PersonalMemoryService._recall_constraint_lane``.
FUZZY_CLAIM_TYPES: frozenset[str] = frozenset({"fact", "preference", "observation"})


# ── Fail-closed tenant filter error ────────────────────────────────────────


class QdrantTenantFilterError(Exception):
    """Raised when a Qdrant personal-memory query is missing a mandatory
    tenant key (``user_id`` and/or ``workspace_id``).

    This is the *fail-closed* guard required by Q1-A: a missing key must
    never silently fall back to a broad (tenant-less) match, because that
    would leak another tenant's memory. The wrapper raises instead of
    querying.
    """


# ── Shared embedding model (loaded ONCE, process-wide) ───────────────────────


class _EmbeddingModel:
    """Process-wide singleton holding the MiniLM model + Qdrant client.

    Analogous to the lazy loaders in ``agent_registry_service.py`` /
    ``embedding_service.py`` but explicit and cached at module scope so the
    80MB MiniLM weights are loaded at most once for the whole backend
    process across all personal-memory call sites. ``encode`` is run on a
    single text per claim (cheap); keep it synchronous to avoid an event-loop
    threadpool hop per row during bulk upserts.
    """

    _instance: _EmbeddingModel | None = None

    def __init__(self) -> None:
        self._model: Any | None = None
        self._model_loaded: bool = False
        self._client: QdrantClient | None = None
        self._client_available: bool | None = None

    @classmethod
    def get(cls) -> _EmbeddingModel:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- embedding model -----------------------------------------------------

    def _load_model(self) -> None:
        if self._model_loaded:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("personal_memory_qdrant: loaded embedding model %s", EMBEDDING_MODEL_NAME)
        except Exception as exc:  # pragma: no cover - depends on env
            logger.warning("personal_memory_qdrant: embedding model unavailable (%s)", exc)
            self._model = None
        finally:
            self._model_loaded = True

    def encode(self, text: str) -> list[float] | None:
        self._load_model()
        if self._model is None:
            return None
        try:
            return self._model.encode(text).tolist()
        except Exception as exc:  # pragma: no cover - depends on env
            logger.warning("personal_memory_qdrant: encode failed (%s)", exc)
            return None

    # -- qdrant client -------------------------------------------------------

    def get_client(self) -> QdrantClient | None:
        if self._client_available is not None and self._client is not None:
            return self._client
        if self._client_available is False:
            return None
        try:
            from qdrant_client import QdrantClient as _QC

            from app.config import settings

            client = _QC(url=settings.QDRANT_URL, timeout=10)
            client.get_collections()
            self._client = client
            self._client_available = True
            logger.info("personal_memory_qdrant: connected to Qdrant at %s", settings.QDRANT_URL)
            return self._client
        except Exception as exc:  # pragma: no cover - depends on env
            logger.warning("personal_memory_qdrant: Qdrant unavailable (%s); vector lane disabled", exc)
            self._client_available = False
            return None

    def ensure_collection(self) -> bool:
        """Idempotently create the global collection + payload indexes.

        Returns ``True`` if the collection is ready (created or already
        existed), ``False`` if Qdrant is unreachable. Never raises on
        infra failure — recall degrades gracefully without the vector lane.
        """
        client = self.get_client()
        if client is None:
            return False
        try:
            from qdrant_client.models import Distance, VectorParams

            if not client.collection_exists(PERSONAL_MEMORY_COLLECTION):
                client.create_collection(
                    collection_name=PERSONAL_MEMORY_COLLECTION,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )
                logger.info("personal_memory_qdrant: created collection %s", PERSONAL_MEMORY_COLLECTION)
            # Payload indexes (Q1-A): tenant filter + claim_type partition.
            for field in ("user_id", "workspace_id", "claim_type"):
                try:
                    client.create_payload_index(
                        collection_name=PERSONAL_MEMORY_COLLECTION,
                        field_name=field,
                        field_schema="keyword",
                    )
                except Exception:
                    # Idempotent: index may already exist; tolerate
                    # "already exists" / "alias" errors across client versions.
                    logger.debug("personal_memory_qdrant: payload index %s already present or skipped", field)
            return True
        except Exception as exc:  # pragma: no cover - depends on env
            logger.warning("personal_memory_qdrant: ensure_collection failed (%s)", exc)
            return False


# ── Canonical triple sentence (Q1-D) ────────────────────────────────────────


def canonical_triple_sentence(subject: str, predicate: str, object_value: Any) -> str:
    """Build the canonical triple sentence that is embedded for retrieval.

    Q1-D: we embed the *human-readable triple*, NOT the raw ``object`` JSONB.
    Example: subject="user", predicate="prefers", object={"theme": "dark"}
    → ``"user prefers theme: dark"``. The ``object`` JSONB itself is stored
    in the Qdrant payload for exact filtering; only the rendered sentence is
    vectorized so semantic match operates on meaning, not dict serialization.
    """
    # Flatten a simple object dict into "k: v" fragments, else stringify.
    if isinstance(object_value, dict):
        obj_text = "" if not object_value else " ".join(f"{k}: {v}" for k, v in object_value.items())
    else:
        obj_text = str(object_value or "")
    parts = [p for p in (str(subject), str(predicate), obj_text) if p]
    return " ".join(parts)


# ── Fail-closed tenant filter (Q1-A) ────────────────────────────────────────


def _build_tenant_filter(user_id: int, workspace_id: str) -> Any:
    """Return a Qdrant ``Filter`` with ``must={user_id, workspace_id}``.

    Raises ``QdrantTenantFilterError`` if either key is missing — the
    fail-closed contract. ``user_id`` is validated as a real int (the SQL
    lane requires it positional); ``workspace_id`` must be a non-empty str.
    """
    if user_id is None or not isinstance(user_id, int):
        raise QdrantTenantFilterError(
            f"personal_memory_qdrant: user_id is required and must be an int for tenant-scoped query, got {user_id!r}"
        )
    if not workspace_id:
        raise QdrantTenantFilterError(
            "personal_memory_qdrant: workspace_id is required (non-empty) for tenant-scoped query"
        )
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return Filter(
        must=[
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)),
        ]
    )


# ── Write path: upsert / delete a claim point (Q1-D/E) ──────────────────────


def upsert_claim_point(
    *,
    claim_id: str,
    user_id: int,
    workspace_id: str,
    claim_type: str,
    canonical_text: str,
    object_payload: Any,
    subject: str,
    predicate: str,
) -> bool:
    """Embed ``canonical_text`` and upsert the claim as a Qdrant point.

    Returns ``True`` on success, ``False`` if Qdrant/the model is
    unavailable (caller treats this as a soft skip — SQL recall still works).
    NEVER raises on infra failure (except the fail-closed filter inside
    ``_build_tenant_filter`` if a key is genuinely missing — that is a bug,
    surfaced loudly rather than silently broadcasting).
    """
    # _build_tenant_filter raises on missing keys (fail-closed). This is the
    # one place we WANT the hard contract to surface a programming error.
    _build_tenant_filter(user_id, workspace_id)

    model = _EmbeddingModel.get()
    if model.ensure_collection() is False:
        return False
    vector = model.encode(canonical_text)
    client = model.get_client()
    if vector is None or client is None:
        return False
    try:
        from qdrant_client.models import PointStruct

        client.upsert(
            collection_name=PERSONAL_MEMORY_COLLECTION,
            points=[
                PointStruct(
                    id=claim_id,
                    vector=vector,
                    payload={
                        "user_id": user_id,
                        "workspace_id": workspace_id,
                        "claim_type": claim_type,
                        "subject": subject,
                        "predicate": predicate,
                        # object JSONB kept verbatim for exact filtering +
                        # constraint match (Q1-D). Never vectorized.
                        "object": object_payload,
                        "canonical_text": canonical_text,
                    },
                )
            ],
        )
        return True
    except Exception as exc:  # pragma: no cover - depends on env
        logger.warning("personal_memory_qdrant: upsert failed for claim %s (%s)", claim_id, exc)
        return False


def delete_claim_point(claim_id: str) -> bool:
    """Delete a claim's Qdrant point (on forget / soft-delete). Best-effort:
    returns ``False`` if Qdrant is unavailable, never raises."""
    model = _EmbeddingModel.get()
    client = model.get_client()
    if client is None:
        return False
    try:
        client.delete(
            collection_name=PERSONAL_MEMORY_COLLECTION,
            points_selector=[claim_id],
        )
        return True
    except Exception as exc:  # pragma: no cover - depends on env
        logger.debug("personal_memory_qdrant: delete failed for claim %s (%s)", claim_id, exc)
        return False


# ── Fuzzy lane: dense search + RRF (Q1-C/E) ─────────────────────────────────


def _dense_search(
    *,
    user_id: int,
    workspace_id: str,
    query_vector: list[float],
    limit: int,
) -> list[tuple[str, float]]:
    """Dense cosine search scoped to the tenant + FUZZY claim types only.

    Constraints are intentionally EXCLUDED (Q1-B trap): the filter adds a
    ``claim_type NOT IN (constraint)`` condition so a "never deploy Fridays"
    constraint can never be cosine-matched against a "deploy Fridays" query.
    Returns ``[(claim_id, score), ...]`` ordered by score desc.
    """
    model = _EmbeddingModel.get()
    client = model.get_client()
    if client is None or query_vector is None:
        return []
    try:
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchAny,
        )

        # Fail-closed tenant filter (raises on missing key).
        tenant = _build_tenant_filter(user_id, workspace_id)
        # Exclude constraints from the dense lane (Q1-B trap).
        claim_filter = Filter(
            must=[
                *tenant.must,
                FieldCondition(
                    key="claim_type",
                    match=MatchAny(any=list(FUZZY_CLAIM_TYPES)),
                ),
            ]
        )
        hits = client.search(
            collection_name=PERSONAL_MEMORY_COLLECTION,
            query_vector=query_vector,
            query_filter=claim_filter,
            limit=limit,
            with_payload=False,
        )
        return [(str(h.id), float(h.score)) for h in hits]
    except QdrantTenantFilterError:
        raise  # fail-closed — never swallow a missing-key call
    except Exception as exc:  # pragma: no cover - depends on env
        logger.warning("personal_memory_qdrant: dense search failed (%s)", exc)
        return []


def _bm25_scores(
    *,
    user_id: int,
    workspace_id: str,
    query_tokens: list[str],
    corpus: list[tuple[str, str]],
) -> dict[str, float]:
    """BM25 over canonical texts, tenant-scoped.

    ``corpus`` is ``[(claim_id, canonical_text), ...]`` for the tenant's
    FUZZY claims. We do not query Qdrant for BM25 — the canonical text +
    claim_type for the tenant's fuzzy claims are fetched from Postgres by the
    caller (``recall`` already has the SQL rows), which is the authoritative
    source and avoids a second store. Constraints are excluded by the caller
    (only FUZZY claim types are passed in).

    Returns ``{claim_id: bm25_score}``. Rank order is derived from this in
    ``reciprocal_rank_fusion``.
    """
    if not query_tokens or not corpus:
        return {}
    n = len(corpus)
    avg_dl = sum(max(1, len(text.split())) for _, text in corpus) / max(1, n)
    k1, b = 1.5, 0.75
    # Document frequency of each query token.
    df: dict[str, int] = {}
    for _, text in corpus:
        toks = set(text.lower().split())
        for qt in query_tokens:
            if qt in toks:
                df[qt] = df.get(qt, 0) + 1
    scores: dict[str, float] = {}
    for cid, text in corpus:
        doc_toks = text.lower().split()
        dl = max(1, len(doc_toks))
        doc_freq: dict[str, int] = {}
        for t in doc_toks:
            doc_freq[t] = doc_freq.get(t, 0) + 1
        score = 0.0
        for qt in query_tokens:
            if qt not in df:
                continue
            idf = math.log((n - df[qt] + 0.5) / (df[qt] + 0.5) + 1.0)
            tf = doc_freq.get(qt, 0)
            if tf == 0:
                continue
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / avg_dl)))
        scores[cid] = score
    return scores


def reciprocal_rank_fusion(
    *,
    dense: list[tuple[str, float]],
    bm25: dict[str, float],
    k: int = RRF_K,
) -> list[str]:
    """Merge dense + BM25 ranks via Reciprocal Rank Fusion ``Σ 1/(k+rank)``.

    Each list is ranked independently (dense by score desc, BM25 by score
    desc), then fused. Higher fused score = more relevant. Returns the
    ordered list of ``claim_id``s (best first). A claim present in only one
    list still gets its RRF contribution, so neither lane dominates when the
    other is empty.

    Determinism: ties in fused score keep insertion order from the dense list
    first, then BM25 (Python dict iteration is ordered), so the output is
    reproducible for identical inputs.
    """
    fused: dict[str, float] = {}

    # Dense ranking (rank 1 = highest score).
    dense_ranked = sorted(dense, key=lambda x: x[1], reverse=True)
    for rank, (cid, _score) in enumerate(dense_ranked, start=1):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)

    # BM25 ranking (rank 1 = highest score).
    bm25_ranked = sorted(bm25.items(), key=lambda x: x[1], reverse=True)
    for rank, (cid, _score) in enumerate(bm25_ranked, start=1):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)

    ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return [cid for cid, _ in ordered]


def fuzzy_lane_recall(
    *,
    user_id: int,
    workspace_id: str,
    query: str,
    corpus: list[tuple[str, str]],
    limit: int,
) -> list[str]:
    """Q1-C/E — run the fuzzy lane end-to-end and return fused ``claim_id``s.

    ``corpus`` is ``[(claim_id, canonical_text), ...]`` for the tenant's
    FUZZY claims (``fact`` / ``preference`` / ``observation``), fetched from
    SQL by the caller. Dense (Qdrant cosine, tenant + fuzzy-only filtered)
    and BM25 (over the corpus) are fused via ``reciprocal_rank_fusion``.

    Sync by design — callers run this through ``asyncio.to_thread`` so the
    (CPU-bound) MiniLM ``encode`` and the Qdrant round-trip never block the
    FastAPI event loop. If Qdrant is unreachable the dense half is skipped
    and BM25 alone drives the fusion; if both are empty, ``[]`` is returned.

    The tenant filter here is fail-closed (``_build_tenant_filter`` raises on
    a missing key) — a misconfigured call is surfaced, never broad-matched.
    """
    query_tokens = [t for t in query.lower().split() if t]
    if not corpus:
        return []
    model = _EmbeddingModel.get()
    client = model.get_client()
    # Only embed when Qdrant is reachable (dense needs both); this also
    # avoids loading the 80MB model when the vector lane is down (BM25 over
    # the SQL corpus still works standalone).
    query_vector = model.encode(query) if client is not None else None
    bm25 = _bm25_scores(
        user_id=user_id,
        workspace_id=workspace_id,
        query_tokens=query_tokens,
        corpus=corpus,
    )
    dense = (
        _dense_search(user_id=user_id, workspace_id=workspace_id, query_vector=query_vector, limit=limit)
        if query_vector
        else []
    )
    return reciprocal_rank_fusion(dense=dense, bm25=bm25)
