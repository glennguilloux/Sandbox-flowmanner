"""Read-only reader over a Hermes Agent ``state.db``.

This mirrors the *pattern* used by Hermes Studio's ``sessions-db.ts``: the
agent runtime's canonical SQLite store is opened **read-only** so a dashboard
(or any Flowmanner service) can surface existing sessions/messages without ever
touching the agent's own state. We keep a separate Flowmanner DB for anything we
mutate; this module never writes.

The Hermes ``state.db`` schema (observed on the live profile DB):

    sessions(id, source, user_id, model, title, started_at, ended_at,
             end_reason, message_count, tool_call_count, parent_session_id, ...)
    messages(id, session_id, role, content, tool_name, token_count,
             timestamp, reasoning_content, ...)

Compression in Hermes ends one session with ``end_reason IN ('compression',
'compressed')`` and starts a ``compress_*`` child linked by
``parent_session_id``. We walk that chain to present one continuous thread.

License note: this is an independent reimplementation of the *idea*; no code
was copied from the BSL-licensed hermes-studio repository.
"""

from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

COMPRESSION_END_REASONS = {"compression", "compressed"}
# Session ids Hermes uses for compaction bookkeeping must be excluded from lists.
IGNORED_ID_PREFIXES = ("compress_",)


def _open_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite DB in read-only mode (URI mode, shared-cache disabled)."""
    p = Path(db_path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"state.db not found: {p}")
    uri = p.as_uri()  # file:///abs/path
    con = sqlite3.connect(f"{uri}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


@dataclass
class HermesMessage:
    id: int
    session_id: str
    role: str
    content: str
    tool_name: str | None
    token_count: int | None
    timestamp: float
    reasoning: str | None


@dataclass
class HermesSession:
    id: str
    source: str | None
    user_id: str | None
    model: str
    title: str | None
    started_at: float
    ended_at: float | None
    end_reason: str | None
    message_count: int
    tool_call_count: int
    preview: str
    last_active: float
    # chain metadata
    parent_session_id: str | None
    is_compression_continuation: bool = False


@dataclass
class SessionChain:
    root: HermesSession
    sessions: list[HermesSession]
    latest_id: str


class SessionReader:
    """Read-only access to a single Hermes ``state.db``."""

    def __init__(self, db_path: str | Path) -> None:
        self._con = _open_readonly(db_path)

    def __enter__(self) -> SessionReader:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._con.close()

    # -- sessions ---------------------------------------------------------

    def list_sessions(
        self,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HermesSession]:
        clauses = ["source != 'tool'"]
        params: list[Any] = []
        for prefix in IGNORED_ID_PREFIXES:
            clauses.append("id NOT LIKE ?")
            params.append(f"{prefix}%")
        if source:
            clauses.append("source = ?")
            params.append(source)
        sql = f"""
            SELECT
                s.*,
                COALESCE(
                    (SELECT SUBSTR(REPLACE(REPLACE(m.content, CHAR(10), ' '),
                                           CHAR(13), ' '), 1, 63)
                     FROM messages m
                     WHERE m.session_id = s.id AND m.role = 'user'
                       AND m.content IS NOT NULL
                     ORDER BY m.timestamp, m.id LIMIT 1), '') AS preview,
                COALESCE(
                    (SELECT MAX(m2.timestamp) FROM messages m2
                     WHERE m2.session_id = s.id), s.started_at) AS last_active
            FROM sessions s
            WHERE {' AND '.join(clauses)}
            ORDER BY last_active DESC, s.id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = self._con.execute(sql, params).fetchall()
        return [self._map_session(r) for r in rows]

    def get_session(self, session_id: str) -> HermesSession | None:
        row = self._con.execute(
            """
            SELECT
                s.*,
                COALESCE(
                    (SELECT SUBSTR(REPLACE(REPLACE(m.content, CHAR(10), ' '),
                                           CHAR(13), ' '), 1, 63)
                     FROM messages m
                     WHERE m.session_id = s.id AND m.role = 'user'
                       AND m.content IS NOT NULL
                     ORDER BY m.timestamp, m.id LIMIT 1), '') AS preview,
                COALESCE(
                    (SELECT MAX(m2.timestamp) FROM messages m2
                     WHERE m2.session_id = s.id), s.started_at) AS last_active
            FROM sessions s WHERE s.id = ?
            """,
            (session_id,),
        ).fetchone()
        return self._map_session(row) if row else None

    def build_chain(self, session_id: str) -> SessionChain | None:
        """Walk the parent_session_id compression chain to one continuous thread."""
        root = self.get_session(session_id)
        if root is None:
            return None
        sessions = [root]
        # Walk backward to the true root.
        current = root
        seen = {root.id}
        for _ in range(100):
            if not current.parent_session_id:
                break
            parent = self.get_session(current.parent_session_id)
            if parent is None:
                break
            if parent.id in seen:
                break
            # Only treat as continuation if parent was compressed and this
            # started at/after parent ended.
            if current.is_compression_continuation:
                sessions.insert(0, parent)
                seen.add(parent.id)
                current = parent
            else:
                break
        latest = max(sessions, key=lambda s: (s.last_active, s.id))
        return SessionChain(root=root, sessions=sessions, latest_id=latest.id)

    # -- messages ---------------------------------------------------------

    def get_messages(self, session_id: str) -> list[HermesMessage]:
        rows = self._con.execute(
            """
            SELECT id, session_id, role, content, tool_name, token_count,
                   timestamp, reasoning_content
            FROM messages
            WHERE session_id = ?
            ORDER BY timestamp ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [self._map_message(r) for r in rows]

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Literal substring search across message content (case-insensitive)."""
        lowered = query.lower()
        like = f"%{lowered}%"
        rows = self._con.execute(
            """
            SELECT s.id AS session_id, s.title, s.source,
                   m.id AS matched_message_id,
                   substr(m.content, max(1, instr(LOWER(m.content), ?) - 40), 120) AS snippet
            FROM sessions s
            JOIN messages m ON m.session_id = s.id
            WHERE s.source != 'tool' AND LOWER(m.content) LIKE ? ESCAPE '\\'
            ORDER BY s.started_at DESC, m.timestamp DESC
            LIMIT ?
            """,
            (lowered, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- mapping ----------------------------------------------------------

    @staticmethod
    def _num(v: Any, default: int = 0) -> int:
        if v is None or v == "":
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _str(v: Any) -> str | None:
        if v is None or v == "":
            return None
        return str(v)

    def _map_session(self, row: sqlite3.Row) -> HermesSession:
        return HermesSession(
            id=str(row["id"]),
            source=self._str(row["source"]),
            user_id=self._str(row["user_id"]),
            model=str(row["model"] or ""),
            title=self._str(row["title"]),
            started_at=float(row["started_at"] or 0),
            ended_at=self._num(row["ended_at"]) or None,
            end_reason=self._str(row["end_reason"]),
            message_count=self._num(row["message_count"]),
            tool_call_count=self._num(row["tool_call_count"]),
            preview=str(row["preview"] or ""),
            last_active=float(row["last_active"] or row["started_at"] or 0),
            parent_session_id=self._str(row["parent_session_id"]),
        )

    @staticmethod
    def _map_message(row: sqlite3.Row) -> HermesMessage:
        return HermesMessage(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            role=str(row["role"] or ""),
            content=str(row["content"] or ""),
            tool_name=SessionReader._str(row["tool_name"]),
            token_count=row["token_count"],
            timestamp=float(row["timestamp"] or 0),
            reasoning=SessionReader._str(row["reasoning_content"]),
        )


def read_sessions(db_path: str | Path) -> Iterable[HermesSession]:
    with SessionReader(db_path) as reader:
        return reader.list_sessions(limit=200)
