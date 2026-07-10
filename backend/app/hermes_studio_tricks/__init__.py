"""Reusable patterns borrowed (independently reimplemented) from Hermes Studio.

Three license-clean modules for Flowmanner:
* session_reader  — read-only view over a Hermes ``state.db``
* context_checkpoint — context-compression "handoff" summary
* workspace_diff  — git/filesystem diff of a run's workspace
"""

from app.hermes_studio_tricks.context_checkpoint import (
    SUMMARY_PREFIX,
    ChatMessage,
    CheckpointConfig,
    CheckpointResult,
    checkpoint,
    count_tokens,
)
from app.hermes_studio_tricks.session_reader import (
    HermesMessage,
    HermesSession,
    SessionChain,
    SessionReader,
)
from app.hermes_studio_tricks.workspace_diff import (
    FileDiff,
    WorkspaceDiff,
    compare_snapshots,
)

__all__ = [
    "SUMMARY_PREFIX",
    "ChatMessage",
    "CheckpointConfig",
    "CheckpointResult",
    "FileDiff",
    "HermesMessage",
    "HermesSession",
    "SessionChain",
    "SessionReader",
    "WorkspaceDiff",
    "checkpoint",
    "compare_snapshots",
    "count_tokens",
]
