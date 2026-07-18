"""
Vector & Embedding Tools — Cosine Similarity Calculator.

cosine_similarity_calc → Compute vector similarity scores using NumPy for
    efficient batch comparisons. Supports cosine, dot product, and Euclidean
    distance metrics with top-k filtering and threshold-based filtering.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

import numpy as np
from pydantic import Field, model_validator

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class CosineSimilarityCalcInput(ToolInput):
    """Input schema: query_embedding, corpus_embeddings, top_k, threshold, metric, include_self."""

    query_embedding: list[float] = Field(
        ...,
        description="Query vector to compare against corpus",
    )
    corpus_embeddings: list[list[float]] = Field(
        ...,
        description="List of corpus vectors to compare against",
    )
    top_k: int | None = Field(
        10,
        ge=1,
        le=10000,
        description="Return top-k most similar results",
    )
    threshold: float | None = Field(
        None,
        description="Minimum similarity score (0-1 for cosine). Only return results above this.",
    )
    metric: Literal["cosine", "dot_product", "euclidean"] = Field(
        "cosine",
        description="Similarity metric to compute",
    )
    include_self: bool = Field(
        False,
        description="If a corpus vector is identical to the query, include it",
    )
    return_scores_only: bool = Field(
        False,
        description="Return only scores without metadata (faster)",
    )
    corpus_labels: list[str] | None = Field(
        None,
        description="Optional labels for each corpus vector for identification",
    )

    @model_validator(mode="after")
    def check_dimensions(self):
        """Ensure all corpus vectors match the query vector dimensions."""
        query_dim = len(self.query_embedding)
        for i, vec in enumerate(self.corpus_embeddings):
            if len(vec) != query_dim:
                raise ValueError(
                    f"Dimension mismatch: query has {query_dim}, corpus vector at index {i} has {len(vec)}"
                )
        if self.corpus_labels and len(self.corpus_labels) != len(self.corpus_embeddings):
            raise ValueError(
                f"corpus_labels length ({len(self.corpus_labels)}) must match "
                f"corpus_embeddings length ({len(self.corpus_embeddings)})"
            )
        return self


class CosineSimilarityCalcTool(BaseTool):
    """Compute vector similarity using NumPy for efficient batch comparisons."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="cosine_similarity_calc",
            name="Cosine Similarity Calculator",
            description=(
                "Compute vector similarity scores using NumPy for efficient batch "
                "comparisons. Supports cosine similarity, dot product, and Euclidean "
                "distance with top-k filtering, threshold-based filtering, and "
                "optional corpus labeling."
            ),
            category="vector-embedding",
            input_schema=CosineSimilarityCalcInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer"},
                                "score": {"type": "number"},
                                "label": {"type": "string"},
                                "rank": {"type": "integer"},
                            },
                        },
                    },
                    "metric": {"type": "string"},
                    "top_k": {"type": "integer"},
                    "total_compared": {"type": "integer"},
                    "computation_time_ms": {"type": "number"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["vectors", "embeddings", "similarity", "cosine", "numpy", "rag"],
            requires_auth=False,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = CosineSimilarityCalcInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        start = time.monotonic()

        try:
            results = self._compute(validated)
            computation_time = round((time.monotonic() - start) * 1000, 2)
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "results": results,
                    "metric": validated.metric,
                    "top_k": validated.top_k,
                    "threshold": validated.threshold,
                    "total_compared": len(validated.corpus_embeddings),
                    "computation_time_ms": computation_time,
                    "success": True,
                },
            )
        except Exception as e:
            logger.exception("cosine_similarity_calc failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    def _compute(self, validated: CosineSimilarityCalcInput) -> list[dict[str, Any]]:
        import numpy as np

        query = np.array(validated.query_embedding, dtype=np.float64)
        if not validated.corpus_embeddings:
            return []

        # Stack corpus into matrix (rows = corpus vectors)
        corpus = np.array(validated.corpus_embeddings, dtype=np.float64)

        if validated.metric == "cosine":
            scores = self._cosine_similarity(query, corpus)
        elif validated.metric == "dot_product":
            scores = corpus @ query
        elif validated.metric == "euclidean":
            scores = 1.0 / (1.0 + np.linalg.norm(corpus - query, axis=1))
        else:
            raise ValueError(f"Unknown metric: {validated.metric}")

        labels = validated.corpus_labels or [None] * len(validated.corpus_embeddings)
        results: list[dict[str, Any]] = []
        for i, score in enumerate(scores):
            if not validated.include_self and np.array_equal(query, corpus[i]):
                continue
            if validated.threshold is not None and score < validated.threshold:
                continue
            results.append(
                {
                    "index": i,
                    "score": round(float(score), 6),
                    "label": labels[i] if i < len(labels) else None,
                }
            )

        # Sort descending by score
        results.sort(key=lambda x: x["score"], reverse=True)

        if validated.return_scores_only:
            results = [{"score": r["score"]} for r in results]

        if validated.top_k:
            results = results[: validated.top_k]

        for rank, r in enumerate(results, 1):
            r["rank"] = rank

        return results

    @staticmethod
    def _cosine_similarity(query: np.ndarray, corpus: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between query and each corpus row."""
        import numpy as np

        q_norm = np.linalg.norm(query)
        c_norms = np.linalg.norm(corpus, axis=1)

        # Avoid division by zero
        q_norm = q_norm if q_norm > 0 else 1e-10
        c_norms = np.where(c_norms > 0, c_norms, 1e-10)

        if corpus.shape[0] > 1000:
            # Use einsum for large corpora (more memory-efficient than dot then divide)
            dot = np.einsum("ij,j->i", corpus, query)
        else:
            dot = corpus @ query

        return dot / (q_norm * c_norms)


register_tool(CosineSimilarityCalcTool())
