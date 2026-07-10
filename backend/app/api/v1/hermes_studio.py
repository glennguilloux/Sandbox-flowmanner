"""FastAPI router exposing the hermes_studio_tricks package to Flowmanner.

This gives the Flowmanner backend (and anything that can call it) safe,
read-only access to:

* Hermes session/message history (read-only view of a Hermes ``state.db``)
* context-compression checkpoints (handoff summaries)
* workspace diffs (what a run changed)

All endpoints are authenticated (``get_current_user``) and the session reader
never writes to the underlying Hermes DB — it opens it read-only.

Routes (mounted under ``/api/hermes-studio``):

    GET  /sessions                     list sessions
    GET  /sessions/{session_id}        session + messages (or chain if compressed)
    GET  /sessions/{session_id}/chain  walk compression chain to one thread
    GET  /sessions/search?q=...        substring search
    POST /checkpoint                   compress a transcript into a handoff summary
    POST /workspace-diff               diff two workspace snapshots

License note: these are independent reimplementations of patterns from the
BSL-licensed hermes-studio repository; no source was copied.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from typing import Any

    from app.hermes_studio_tricks.workspace_diff import WorkspaceDiff
    from app.models.user import User

from app.api.deps import get_current_user
from app.hermes_studio_tricks import (
    ChatMessage,
    CheckpointConfig,
    SessionReader,
    checkpoint,
    compare_snapshots,
    count_tokens,
)
from app.hermes_studio_tricks.context_checkpoint import (
    SUMMARY_PREFIX,
    build_full_prompt,
    build_incremental_prompt,
)

router = APIRouter(prefix="/hermes-studio", tags=["hermes-studio"])


# --- config ---------------------------------------------------------------


def _default_state_db() -> Path:
    """Resolve the Hermes state.db to read.

    Order: HERMES_STUDIO_STATE_DB env -> $HERMES_HOME/state.db -> ~/.hermes/state.db
    """
    env = os.environ.get("HERMES_STUDIO_STATE_DB")
    if env:
        return Path(env).expanduser()
    home = os.environ.get("HERMES_HOME")
    if home:
        return Path(home).expanduser() / "state.db"
    return Path.home() / ".hermes" / "state.db"


# --- request models -------------------------------------------------------


class CheckpointMessage(BaseModel):
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_name: str | None = None


class CheckpointRequest(BaseModel):
    messages: list[CheckpointMessage] = Field(..., min_length=1)
    trigger_tokens: int = Field(100_000, gt=0)
    summary_budget: int = Field(8_000, gt=0)
    tail_message_count: int = Field(10, ge=0)
    head_message_count: int = Field(0, ge=0)
    previous_summary: str | None = None
    previous_last_index: int = -1


class WorkspaceDiffRequest(BaseModel):
    before_root: str
    after_root: str
    workspace: str


# --- helpers --------------------------------------------------------------


def _require_reader() -> SessionReader:
    db = _default_state_db()
    if not db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Hermes state.db not found at {db}",
        )
    return SessionReader(db)


def _to_chat_messages(req_msgs: list[CheckpointMessage]) -> list[ChatMessage]:
    return [
        ChatMessage(
            role=m.role,
            content=m.content,
            tool_calls=m.tool_calls,
            tool_name=m.tool_name,
        )
        for m in req_msgs
    ]


# --- session endpoints ----------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    source: str | None = Query(None, description="filter by session source, e.g. 'tui'"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    with _require_reader() as r:
        sessions = r.list_sessions(source=source, limit=limit, offset=offset)
        return {
            "sessions": [s.__dict__ for s in sessions],
            "count": len(sessions),
        }


@router.get("/sessions/search")
async def search_sessions(
    q: str = Query(..., min_length=1, description="substring to search in messages"),
    limit: int = Query(50, ge=1, le=500),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    with _require_reader() as r:
        results = r.search(q, limit=limit)
        return {"results": results, "count": len(results)}


@router.get("/sessions/{session_id}/chain")
async def get_session_chain(
    session_id: str,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    with _require_reader() as r:
        chain = r.build_chain(session_id)
        if chain is None:
            raise HTTPException(status_code=404, detail="session not found")
        return {
            "root_id": chain.root.id,
            "latest_id": chain.latest_id,
            "sessions": [s.__dict__ for s in chain.sessions],
        }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    with_messages: bool = Query(True),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    with _require_reader() as r:
        session = r.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        payload: dict[str, Any] = {"session": session.__dict__}
        if with_messages:
            payload["messages"] = [m.__dict__ for m in r.get_messages(session_id)]
        return payload


# --- checkpoint endpoint --------------------------------------------------


@router.post("/checkpoint")
async def create_checkpoint(
    req: CheckpointRequest,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Compress a transcript into a handoff summary.

    ``summarize`` is NOT called inside the HTTP request — this endpoint is
    sync and deterministic. To actually produce the summary you call your LLM
    with the returned ``prompt`` and POST the summary back, OR wire a
    summarizer callable server-side. We return the prompt + message plan so
    the caller can run the model themselves (keeps this endpoint free of any
    provider secret in the request path and avoids blocking the request).
    """
    msgs = _to_chat_messages(req.messages)
    cfg = CheckpointConfig(
        trigger_tokens=req.trigger_tokens,
        summary_budget=req.summary_budget,
        tail_message_count=req.tail_message_count,
        head_message_count=req.head_message_count,
    )

    total_tokens = count_tokens(" ".join(m.content for m in msgs))
    under_threshold = total_tokens <= cfg.trigger_tokens

    # Build the prompt the caller should send to the model.
    tail_start = max(cfg.head_message_count, len(msgs) - cfg.tail_message_count)
    if req.previous_summary and req.previous_last_index >= 0:
        to_summarize = msgs[req.previous_last_index + 1 : tail_start]
    else:
        to_summarize = msgs[:tail_start]
    from app.hermes_studio_tricks.context_checkpoint import serialize_for_summary

    transcript = serialize_for_summary(to_summarize)
    prompt = (
        build_incremental_prompt(req.previous_summary, transcript, cfg.summary_budget)
        if req.previous_summary
        else build_full_prompt(transcript, cfg.summary_budget)
    )

    return {
        "under_threshold": under_threshold,
        "total_token_estimate": total_tokens,
        "summary_prefix": SUMMARY_PREFIX,
        "prompt": prompt,
        "tail_messages": [m.__dict__ for m in msgs[tail_start:]],
        "tail_start_index": tail_start,
    }


# --- workspace diff endpoint ----------------------------------------------


@router.post("/workspace-diff")
async def workspace_diff(
    req: WorkspaceDiffRequest,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Diff two workspace snapshots (before/after a run)."""
    if not Path(req.before_root).exists() or not Path(req.after_root).exists():
        raise HTTPException(
            status_code=400,
            detail="before_root and after_root must both exist",
        )
    diff: WorkspaceDiff = compare_snapshots(req.before_root, req.after_root, req.workspace)
    return {
        "kind": diff.kind,
        "root": diff.root,
        "additions": diff.additions,
        "deletions": diff.deletions,
        "truncated": diff.truncated,
        "changes": [c.__dict__ for c in diff.changes],
    }
