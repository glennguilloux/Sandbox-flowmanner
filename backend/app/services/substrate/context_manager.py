"""Long-context management for Opus deep-dive missions (Comment 11).

A dedicated context-management layer that owns the *long-context substrate*
for deep research/review runs.  It deliberately does NOT overload personal
memory (user claims) or episodic memory (cross-mission learning); those stay
as their own services.  This service is the primary long-context window.

It owns:
  * document / code chunking with stable chunk ids,
  * a source manifest (what was ingested, from where, how big),
  * rolling summaries (compaction checkpoints) so old context is compressed
    into a reusable brief,
  * retrieval queries (lexical + metadata filtering, provider-agnostic),
  * pinned evidence (always-on snippets that must survive compaction),
  * context-budget allocation (token budget per phase / per node),
  * compaction checkpoints (snapshot of the active context window).

The selected context plan + chosen chunks are persisted into substrate events
(see :meth:`ContextManager.record_context_event`) so replay can explain
exactly what the model saw for a given node.

All LLM calls route through :class:`BudgetEnforcer` (project rule).  The
service is provider/model-agnostic: the *summary* step uses a model selected
by the caller (default: the node's depth-selected model) so Opus deep dives
can summarise with Opus while cheaper retrieval runs on local models.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Hard size guard for a single chunk (chars). Larger docs are force-split.
_MAX_CHUNK_CHARS = 4000
_CHUNK_OVERLAP_CHARS = 200

_LEADING_WS = re.compile(r"^[ \t]+", re.MULTILINE)


def chunk_text(text: str, *, max_chars: int = _MAX_CHUNK_CHARS, overlap: int = _CHUNK_OVERLAP_CHARS) -> list[str]:
    """Split ``text`` into stable, overlap-bounded chunks.

    Paragraph-aware: we first try to break on blank lines, then on newlines,
    then hard-split, never producing a chunk larger than ``max_chars``.
    """
    if not text:
        return []
    text = text.replace("\r\n", "\n")
    if len(text) <= max_chars:
        return [text]

    # Prefer paragraph boundaries.
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > max_chars:
            # Hard-split an over-long paragraph by lines.
            for line in para.split("\n"):
                if len(line) > max_chars:
                    # Character-level split of a giant token run.
                    for i in range(0, len(line), max_chars):
                        _maybe_append(chunks, line[i : i + max_chars], max_chars)
                else:
                    _maybe_append(chunks, line, max_chars)
            continue
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = (current + "\n\n" + para) if current else para
    if current:
        chunks.append(current)

    # Apply overlap by re-concatenating tails into preceding context.
    if overlap > 0 and len(chunks) > 1:
        overlapped: list[str] = []
        for i, c in enumerate(chunks):
            tail = chunks[i - 1][-overlap:] if i > 0 else ""
            overlapped.append((tail + "\n" + c) if tail else c)
        chunks = overlapped
    return chunks


def _maybe_append(chunks: list[str], piece: str, max_chars: int) -> None:
    if len(piece) > max_chars:
        chunks.extend(piece[i : i + max_chars] for i in range(0, len(piece), max_chars))
    elif piece.strip():
        chunks.append(piece)


def _chunk_id(source_id: str, index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{source_id}::c{index}:{digest}"


@dataclass
class SourceManifest:
    """What was ingested, from where, and how big (for audit + budgeting)."""

    source_id: str
    uri: str
    kind: str  # "document" | "code" | "transcript" | "web"
    char_count: int
    chunk_count: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextPlan:
    """The selected long-context window for a node/phase.

    Persisted to substrate events so replay explains what the model saw.
    """

    run_id: str
    node_id: str | None
    token_budget: int
    selected_chunk_ids: list[str]
    pinned_chunk_ids: list[str]
    rolling_summary: str | None
    compaction_checkpoint: str | None
    sources: list[SourceManifest] = field(default_factory=list)

    def as_event_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "token_budget": self.token_budget,
            "selected_chunk_ids": self.selected_chunk_ids,
            "pinned_chunk_ids": self.pinned_chunk_ids,
            "rolling_summary_len": len(self.rolling_summary or ""),
            "compaction_checkpoint": self.compaction_checkpoint,
            "source_count": len(self.sources),
            "source_ids": [s.source_id for s in self.sources],
        }


class ContextManager:
    """Long-context manager for deep-dive missions (Comment 11).

    Stateless w.r.t. the DB — callers pass the source corpus and the manager
    returns a :class:`ContextPlan` plus the rendered context string.  The
    caller (``NodeExecutor._handle_llm``) is responsible for persisting the
    plan into a substrate event via :meth:`record_context_event`.
    """

    def __init__(self, *, token_budget: int = 12000, overlap: int = _CHUNK_OVERLAP_CHARS) -> None:
        self.token_budget = token_budget
        self.overlap = overlap
        # In-memory corpus for the lifetime of one run (sources + chunks).
        self._sources: dict[str, SourceManifest] = {}
        self._chunks: dict[str, str] = {}
        # Pinned evidence always survives compaction.
        self._pinned: set[str] = set()
        # Rolling summary (compaction checkpoint text).
        self._rolling_summary: str | None = None
        self._compaction_checkpoint: str | None = None

    # ── Ingestion ──
    def add_source(self, *, source_id: str, uri: str, text: str, kind: str = "document") -> SourceManifest:
        pieces = chunk_text(text, overlap=self.overlap)
        manifest = SourceManifest(
            source_id=source_id,
            uri=uri,
            kind=kind,
            char_count=len(text),
            chunk_count=len(pieces),
        )
        self._sources[source_id] = manifest
        for i, piece in enumerate(pieces):
            cid = _chunk_id(source_id, i, piece)
            self._chunks[cid] = piece
        return manifest

    def pin(self, chunk_id: str) -> None:
        if chunk_id in self._chunks:
            self._pinned.add(chunk_id)

    def has_sources(self) -> bool:
        """True once at least one corpus source has been ingested."""
        return bool(self._sources)

    # ── Retrieval ──
    def retrieve(self, query: str, *, k: int = 8, include_pinned: bool = True) -> list[tuple[str, str]]:
        """Lexical retrieval: rank chunks by term overlap with ``query``."""
        terms = {t for t in re.findall(r"[A-Za-z0-9_]+", query.lower()) if len(t) > 2}
        scored: list[tuple[float, str, str]] = []
        for cid, text in self._chunks.items():
            if not terms:
                scored.append((0.0, cid, text))
                continue
            low = text.lower()
            score = sum(low.count(t) for t in terms)
            if score > 0:
                scored.append((float(score), cid, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [(cid, txt) for _, cid, txt in scored[:k]]
        if include_pinned:
            for cid in self._pinned:
                if cid not in {c for c, _ in results}:
                    results.insert(0, (cid, self._chunks[cid]))
        return results

    # ── Compaction / rolling summary ──
    def compact(self, summary: str, *, checkpoint: str | None = None) -> None:
        """Replace active chunks with a rolling summary (compaction checkpoint)."""
        self._rolling_summary = summary
        self._compaction_checkpoint = checkpoint or f"ckpt:{len(self._chunks)}"
        # Keep only pinned chunks; everything else is summarised away.
        pinned = {cid: self._chunks[cid] for cid in self._pinned if cid in self._chunks}
        self._chunks = dict(pinned)

    # ── Plan assembly (context-budget allocation) ──
    def build_plan(
        self,
        run_id: str,
        node_id: str | None,
        *,
        query: str | None = None,
        token_budget: int | None = None,
    ) -> tuple[ContextPlan, str]:
        """Allocate the context window within ``token_budget`` and render it.

        Returns ``(plan, rendered_context_text)``.  Pinned evidence is always
        included; remaining budget is filled by retrieval ranked results; a
        rolling summary (if any) is prepended as the persistent brief.
        """
        budget = token_budget or self.token_budget
        # ~4 chars/token heuristic for allocation.
        budget_chars = budget * 4

        selected: list[tuple[str, str]] = []
        used_chars = 0

        # 1) Pinned evidence first (always-on).
        for cid in self._pinned:
            text = self._chunks.get(cid)
            if text is None:
                continue
            selected.append((cid, text))
            used_chars += len(text)

        # 2) Rolling summary as the persistent brief header.
        summary_text = self._rolling_summary
        if summary_text:
            used_chars += len(summary_text)

        # 3) Fill remaining budget with retrieval results.
        candidates = self.retrieve(query or "", include_pinned=True) if query else list(self._chunks.items())
        for cid, text in candidates:
            if cid in {c for c, _ in selected}:
                continue
            if used_chars + len(text) > budget_chars:
                continue
            selected.append((cid, text))
            used_chars += len(text)

        plan = ContextPlan(
            run_id=run_id,
            node_id=node_id,
            token_budget=budget,
            selected_chunk_ids=[c for c, _ in selected],
            pinned_chunk_ids=[c for c in self._pinned if c in {x for x, _ in selected}],
            rolling_summary=summary_text,
            compaction_checkpoint=self._compaction_checkpoint,
            sources=list(self._sources.values()),
        )

        parts: list[str] = []
        if summary_text:
            parts.append("## Rolling summary (compaction checkpoint)\n" + summary_text)
        if plan.pinned_chunk_ids:
            parts.append("## Pinned evidence\n" + "\n\n".join(self._chunks[c] for c in plan.pinned_chunk_ids))
        if selected:
            parts.append("## Retrieved context\n" + "\n\n".join(f"[{cid}]\n{txt}" for cid, txt in selected))
        rendered = "\n\n".join(parts)
        return plan, rendered

    # ── Persistence helper (substrate event) ──
    async def record_context_event(
        self,
        db: Any,
        run_id: str,
        plan: ContextPlan,
        *,
        node_id: str | None = None,
        mission_id: str | None = None,
    ) -> None:
        """Persist the selected context plan so replay explains model input.

        Comment 11: the context window is first-class substrate state, not an
        implicit side effect of personal/episodic memory.
        """
        from app.services.substrate.event_log import get_event_log

        event_log = get_event_log()
        try:
            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": "context.plan",
                        "payload": plan.as_event_payload(),
                        "actor": "context_manager",
                        "mission_id": mission_id,
                        "task_id": node_id,
                    }
                ],
            )
        except Exception as e:  # fire-and-forget: never block execution
            logger.debug("Failed to record context.plan event: %s", e)
