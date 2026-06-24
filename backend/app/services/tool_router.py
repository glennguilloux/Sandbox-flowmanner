"""Tool Router — sparse tool candidate-set selector (Q2-Q3 Chunk 3).

Scores tools from registry metadata, task text, prior outcomes (via episodic
memory), and permission data, then returns a bounded top-k candidate set.
When routing confidence is low, falls back to the full registry.

Every routing decision is audit-logged to the substrate event log.

Scoring is deterministic (no LLM calls, no embeddings required):
- text_similarity (0.5): Jaccard word overlap between task and tool description
- category_match (0.2): keyword lookup table
- memory_hint (0.2): optional signal from episodic memory
- permission_ok (0.1): hard 0 if denied (tool excluded entirely)

High-risk tools (requires_approval=True) are ALWAYS included regardless of score.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING, Any

from app.models.tool_routing_models import (
    ToolRouteDecidedEvent,
    ToolRouteResult,
    ToolScore,
)

if TYPE_CHECKING:
    from uuid import UUID

    from app.services.episodic_memory_service import EpisodicMemoryService
    from app.services.langgraph.tool_converter import ToolConverter, ToolDefinition
    from app.services.substrate.event_log import EventLog

logger = logging.getLogger(__name__)

# ── Category keyword lookup table ──────────────────────────────────

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "workflow": ["workflow", "n8n", "automate", "automation", "pipeline", "flow"],
    "image": ["image", "photo", "picture", "comfyui", "draw", "generate image", "background"],
    "3d": ["3d", "3d model", "3dglenn", "model generation", "mesh"],
    "search": ["search", "find", "lookup", "query", "discover", "browse"],
    "config": ["config", "configuration", "settings", "save", "load", "preferences"],
    "integration": [
        "integration",
        "slack",
        "github",
        "google",
        "notion",
        "linear",
        "discord",
        "connect",
        "send message",
        "create issue",
        "email",
    ],
}

# ── Text similarity helpers ────────────────────────────────────────

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "so",
        "if",
        "than",
        "too",
        "very",
        "just",
        "about",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "they",
        "them",
        "their",
        "what",
        "which",
        "who",
        "whom",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "only",
        "own",
        "same",
        "also",
    }
)


def _tokenize(text: str) -> set[str]:
    """Lowercase tokenize with stop-word removal."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOP_WORDS and len(w) > 1}


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _task_text_hash(task_text: str) -> str:
    """SHA-256 hex digest of normalized task text for audit privacy."""
    normalized = " ".join(task_text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ── ToolRouter ─────────────────────────────────────────────────────


class ToolRouter:
    """Scored candidate-set selector for tool definitions.

    Scores each tool from registry metadata, task text, and optional
    memory hints, then returns a bounded top-k set. Falls back to the
    full registry when confidence is low.

    Usage::

        converter = ToolConverter()
        router = ToolRouter(registry=converter)
        result = await router.route(task_text="search workflows", workspace_id=uuid, user_id=1)
    """

    # Scoring weights
    WEIGHT_TEXT_SIMILARITY = 0.5
    WEIGHT_CATEGORY_MATCH = 0.2
    WEIGHT_MEMORY_HINT = 0.2
    WEIGHT_PERMISSION_OK = 0.1

    def __init__(
        self,
        registry: ToolConverter,
        memory_service: EpisodicMemoryService | None = None,
        default_k: int = 8,
        min_confidence: float = 0.3,
        audit_log: EventLog | None = None,
    ):
        self._registry = registry
        self._memory_service = memory_service
        self._default_k = default_k
        self._min_confidence = min_confidence
        self._audit_log = audit_log

    # ── Public API ─────────────────────────────────────────────────

    async def route(
        self,
        task_text: str,
        workspace_id: UUID,
        user_id: int,
        *,
        k: int | None = None,
        mission_id: UUID | None = None,
        run_id: str | None = None,
        db: Any = None,
    ) -> ToolRouteResult:
        """Score and select the top-k tool candidates for a task.

        Args:
            task_text: The natural language task description.
            workspace_id: Workspace scope (required).
            user_id: User scope (required).
            k: Override for candidate set size (default: self._default_k).
            mission_id: Optional mission context for audit.
            run_id: Optional run context for audit event emission.
            db: Optional DB session for audit event persistence.

        Returns:
            ToolRouteResult with the candidate set or full-registry fallback.
        """
        k = k or self._default_k
        all_tools = self._registry.list_tools()
        hash_val = _task_text_hash(task_text)

        if not all_tools:
            return ToolRouteResult(
                tools=[],
                mode="fallback-full-registry",
                top_score=0.0,
                reasons={},
                candidates_considered=0,
                candidates_returned=0,
                task_text_hash=hash_val,
                scores=[],
            )

        # Score every tool
        scores: list[ToolScore] = []
        for tool in all_tools:
            score = await self._score_tool(tool, task_text, workspace_id, user_id)
            scores.append(score)

        # Sort by score descending
        scores.sort(key=lambda s: s.score, reverse=True)

        # Determine mode based on top score vs min_confidence
        top_score = scores[0].score if scores else 0.0
        mode: str = "sparse" if top_score >= self._min_confidence else "fallback-full-registry"

        # Build the candidate set
        reasons: dict[str, str] = {}

        if mode == "sparse":
            # Take top-k
            selected = scores[:k]

            # Always include high-risk tools (requires_approval=True)
            always_ids = set(self._always_include_tools())
            selected_ids = {s.tool_id for s in selected}
            for tool in all_tools:
                if tool.tool_id in always_ids and tool.tool_id not in selected_ids:
                    # Find the score for this tool
                    tool_score = next((s for s in scores if s.tool_id == tool.tool_id), None)
                    if tool_score:
                        selected.append(tool_score)
                    else:
                        selected.append(
                            ToolScore(
                                tool_id=tool.tool_id,
                                score=0.0,
                                components={},
                                reasons=["always-include: requires_approval=True"],
                            )
                        )

            # Build reasons dict
            for s in selected:
                reasons[s.tool_id] = "; ".join(s.reasons) if s.reasons else "scored"

            result_tools = [t.to_dict() for t in all_tools if t.tool_id in {s.tool_id for s in selected}]

        else:
            # Fallback: return ALL tools (preserve current behavior)
            result_tools = [t.to_dict() for t in all_tools]
            reasons = {t.tool_id: "fallback: low confidence" for t in all_tools}

        result = ToolRouteResult(
            tools=result_tools,
            mode=mode,
            top_score=top_score,
            reasons=reasons,
            candidates_considered=len(all_tools),
            candidates_returned=len(result_tools),
            task_text_hash=hash_val,
            scores=scores,
        )

        # Emit audit event (best-effort)
        await self._emit_audit_event(
            result=result,
            workspace_id=workspace_id,
            user_id=user_id,
            mission_id=mission_id,
            run_id=run_id,
            db=db,
        )

        return result

    # ── Scoring ────────────────────────────────────────────────────

    async def _score_tool(
        self,
        tool: ToolDefinition,
        task_text: str,
        workspace_id: UUID,
        user_id: int,
    ) -> ToolScore:
        """Compute weighted score for a single tool.

        Components (all in [0.0, 1.0]):
        - text_similarity (0.5): Jaccard word overlap
        - category_match (0.2): keyword lookup
        - memory_hint (0.2): optional episodic memory signal
        - permission_ok (0.1): hard 0 if denied (excludes tool entirely)
        """
        components: dict[str, float] = {}
        reasons: list[str] = []

        # 1. Text similarity
        text_sim = self._text_similarity(tool, task_text)
        components["text_similarity"] = text_sim
        if text_sim > 0.1:
            reasons.append(f"text overlap {text_sim:.2f}")

        # 2. Category match
        cat_match = self._category_match(tool, task_text)
        components["category_match"] = cat_match
        if cat_match >= 1.0:
            reasons.append(f"category '{tool.category}' matched in task")

        # 3. Memory hint (optional)
        mem_hint = await self._memory_hint(tool, task_text, workspace_id, user_id)
        components["memory_hint"] = mem_hint
        if mem_hint > 0.0:
            outcome = "success" if mem_hint >= 1.0 else "failure"
            reasons.append(f"memory hint: prior {outcome}")

        # 4. Permission check
        perm_ok = self._permission_ok(tool, workspace_id, user_id)
        components["permission_ok"] = perm_ok
        if perm_ok == 0.0:
            reasons.append("permission denied")

        # Weighted sum
        score = (
            self.WEIGHT_TEXT_SIMILARITY * text_sim
            + self.WEIGHT_CATEGORY_MATCH * cat_match
            + self.WEIGHT_MEMORY_HINT * mem_hint
            + self.WEIGHT_PERMISSION_OK * perm_ok
        )

        # Hard 0 if permission denied
        if perm_ok == 0.0:
            score = 0.0

        return ToolScore(
            tool_id=tool.tool_id,
            score=round(score, 4),
            components=components,
            reasons=reasons,
        )

    def _text_similarity(self, tool: ToolDefinition, task_text: str) -> float:
        """Jaccard word overlap between task text and tool name+description."""
        task_tokens = _tokenize(task_text)
        tool_tokens = _tokenize(f"{tool.name} {tool.description}")
        return _jaccard_similarity(task_tokens, tool_tokens)

    def _category_match(self, tool: ToolDefinition, task_text: str) -> float:
        """1.0 if task text contains a keyword for the tool's category, 0.5 otherwise."""
        task_lower = task_text.lower()
        keywords = _CATEGORY_KEYWORDS.get(tool.category, [])
        for kw in keywords:
            if kw in task_lower:
                return 1.0
        return 0.5

    async def _memory_hint(
        self,
        tool: ToolDefinition,
        task_text: str,
        workspace_id: UUID,
        user_id: int,
    ) -> float:
        """Query episodic memory for prior tool outcomes.

        Returns:
            1.0 if tool appeared in a successful episode,
            0.5 if tool appeared in a failed episode,
            0.0 if not found or memory service unavailable.
        """
        if self._memory_service is None:
            return 0.0

        try:
            episodes = await self._memory_service.retrieve_relevant(
                db=None,  # type: ignore[arg-type]
                query_text=task_text,
                workspace_id=str(workspace_id),
                user_id=user_id,
                k=5,
            )
        except Exception as exc:
            logger.debug("Memory hint lookup failed for tool %s: %s", tool.tool_id, exc)
            return 0.0

        # Check if this tool appears in episode retrieval_text
        for ep in episodes:
            retrieval_text = ep.get("retrieval_text", "")
            if tool.tool_id in retrieval_text or tool.name.lower() in retrieval_text.lower():
                outcome = ep.get("outcome", "")
                if outcome == "success":
                    return 1.0
                elif outcome == "failure":
                    return 0.5
                return 0.5  # partial or unknown outcome

        return 0.0

    def _permission_ok(
        self,
        tool: ToolDefinition,
        workspace_id: UUID,
        user_id: int,
    ) -> float:
        """Check if user has access to the tool.

        Returns 1.0 if allowed, 0.0 if denied.
        Currently all tools are global (no per-workspace deny-list),
        so this always returns 1.0. A TODO for follow-up permission integration.
        """
        # TODO: integrate with workspace/user permission deny-list when available
        return 1.0

    def _always_include_tools(self) -> list[str]:
        """Tool IDs that MUST be in the candidate set regardless of score.

        High-risk tools (requires_approval=True) are always included
        so the LLM can see them and the approval workflow can trigger.
        Safety over sparsity.
        """
        return [tool.tool_id for tool in self._registry.list_tools() if tool.requires_approval]

    # ── Audit ──────────────────────────────────────────────────────

    async def _emit_audit_event(
        self,
        *,
        result: ToolRouteResult,
        workspace_id: UUID,
        user_id: int,
        mission_id: UUID | None,
        run_id: str | None,
        db: Any,
    ) -> None:
        """Emit a tool_route_decided event to the substrate event log.

        Best-effort — never raises, only logs on failure.
        """
        if run_id is None or db is None:
            return

        if self._audit_log is None:
            try:
                from app.services.substrate.event_log import get_event_log

                self._audit_log = get_event_log()
            except Exception:
                return

        try:
            selected_ids = [t["tool_id"] for t in result.tools]
            event_payload = ToolRouteDecidedEvent(
                mode=result.mode,
                top_score=result.top_score,
                candidates_considered=result.candidates_considered,
                candidates_returned=result.candidates_returned,
                selected_tool_ids=selected_ids,
                task_text_hash=result.task_text_hash,
                workspace_id=str(workspace_id),
                user_id=user_id,
                mission_id=str(mission_id) if mission_id else None,
            )

            from app.models.substrate_models import SubstrateEventType

            await self._audit_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.TOOL_ROUTE_DECIDED,
                        "payload": event_payload.model_dump(),
                        "actor": "tool_router",
                        "mission_id": str(mission_id) if mission_id else None,
                    }
                ],
                mission_id=str(mission_id) if mission_id else None,
            )
            logger.debug(
                "Emitted tool_route_decided event: mode=%s, tools=%d",
                result.mode,
                result.candidates_returned,
            )
        except Exception as exc:
            logger.debug("Failed to emit tool_route_decided audit event: %s", exc)


# ── Singleton ──────────────────────────────────────────────────────

_router: ToolRouter | None = None


def get_tool_router(
    registry: ToolConverter | None = None,
    memory_service: EpisodicMemoryService | None = None,
) -> ToolRouter:
    """Get or create the ToolRouter singleton."""
    global _router
    if _router is None:
        if registry is None:
            from app.services.langgraph.tool_converter import get_tool_converter

            registry = get_tool_converter()
        if memory_service is None:
            try:
                from app.services.episodic_memory_service import get_episodic_memory_service

                memory_service = get_episodic_memory_service()  # Returns None when flag is off
            except Exception:
                memory_service = None
        _router = ToolRouter(
            registry=registry,
            memory_service=memory_service,
        )
    return _router


def reset_tool_router() -> None:
    """Reset the singleton (for testing)."""
    global _router
    _router = None
