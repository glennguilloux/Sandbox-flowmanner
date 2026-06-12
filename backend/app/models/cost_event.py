"""Cost category enum for per-step cost attribution (Q1-B Chunk 4).

Six cost categories tracked from day one:
1. llm_tokens    — LLM API calls (already tracked via LLMCallRecord)
2. tool_execution — sandboxd CPU time, code execution
3. embedding     — Qdrant/vector store operations
4. external_api  — web search, third-party integrations
5. storage       — file operations, sandbox snapshots
6. browser       — Playwright/browser automation

Per the Q1-B plan §2 (Resolved Decisions #2), only 3 categories are
actively recorded on day one (llm_tokens, tool_execution, embedding).
The remaining 3 are schema-ready for when there's data to fill them.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime


class CostCategory(str, enum.Enum):
    """Cost categories for per-step attribution."""

    LLM_TOKENS = "llm_tokens"
    TOOL_EXECUTION = "tool_execution"
    EMBEDDING = "embedding"
    EXTERNAL_API = "external_api"
    STORAGE = "storage"
    BROWSER = "browser"


@dataclass
class CostEvent:
    """A single cost event recorded per-step during mission execution.

    This is the in-memory DTO used by the cost engine.  It maps 1:1 to
    a row in ``llm_call_records`` with the Q1-B cost_category columns.

    Attributes:
        category: One of the 6 cost categories.
        cost_usd: Pre-computed cost in USD.
        mission_id: UUID of the owning mission.
        node_id: UUID of the workflow node that incurred the cost.
        run_id: UUID of the substrate run.
        provider: Provider label (e.g. "deepseek", "qdrant", "sandboxd").
        model_id: Model or resource identifier.
        tool_name: Name of the tool that incurred the cost (tool_execution only).
        embedding_tokens: Number of embedding tokens consumed (embedding only).
        input_tokens: Number of input tokens consumed (LLM only).
        output_tokens: Number of output tokens produced (LLM only).
        latency_ms: Round-trip latency in milliseconds.
        workspace_id: Workspace that owns the cost.
        agent_id: Agent that incurred the cost.
        timestamp: When the cost event occurred.
    """

    category: CostCategory
    cost_usd: float
    mission_id: str = ""
    node_id: str = ""
    run_id: str = ""
    provider: str = "unknown"
    model_id: str = ""
    tool_name: str | None = None
    embedding_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    workspace_id: str = ""
    agent_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
