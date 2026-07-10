"""Tests for the hermes_studio_tricks package.

Run from the backend dir:
    cd /opt/flowmanner/backend && python -m pytest app/hermes_studio_tricks/tests -q
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.hermes_studio_tricks import (
    ChatMessage,
    CheckpointConfig,
    HermesSession,
    SessionReader,
    WorkspaceDiff,
    checkpoint,
    compare_snapshots,
    count_tokens,
)

LIVE_DB = Path.home() / ".hermes" / "state.db"


# --- Module 1: session reader --------------------------------------------


def test_reader_opens_live_db():
    if not LIVE_DB.exists():
        pytest.skip("no live state.db on this machine")
    with SessionReader(LIVE_DB) as r:
        sessions = r.list_sessions(limit=50)
        assert isinstance(sessions, list)
        # We know the live DB has at least a few sessions.
        assert len(sessions) > 0
        s0 = sessions[0]
        assert isinstance(s0, HermesSession)
        assert s0.id
        # Must be opened read-only: writing raises.
        with pytest.raises(sqlite3.OperationalError):
            r._con.execute("UPDATE sessions SET title = 'x' WHERE id = ?", (s0.id,))


def test_reader_messages_and_search():
    if not LIVE_DB.exists():
        pytest.skip("no live state.db on this machine")
    with SessionReader(LIVE_DB) as r:
        sessions = r.list_sessions(limit=10)
        assert sessions
        sid = sessions[0].id
        msgs = r.get_messages(sid)
        # messages come back ordered
        ts = [m.timestamp for m in msgs]
        assert ts == sorted(ts)
        # search returns dicts with a snippet or empty list
        results = r.search("the")
        assert isinstance(results, list)


def test_reader_missing_db_raises():
    with pytest.raises(FileNotFoundError):
        SessionReader("/no/such/state.db")


def test_chain_walk_no_crash():
    if not LIVE_DB.exists():
        pytest.skip("no live state.db on this machine")
    with SessionReader(LIVE_DB) as r:
        sessions = r.list_sessions(limit=5)
        for s in sessions:
            chain = r.build_chain(s.id)
            assert chain is not None
            assert chain.root.id == s.id
            assert chain.latest_id


# --- Module 2: context checkpoint ----------------------------------------


def _fake_summarizer(prompt: str) -> str:
    # Echo a deterministic summary for testing.
    return "## Active Task\nImplement the feature.\n## Completed Actions\n1. READ x [tool: read]"


def test_checkpoint_under_threshold_returns_verbatim():
    msgs = [ChatMessage("user", "hello"), ChatMessage("assistant", "hi")]
    res = checkpoint(msgs, _fake_summarizer)
    assert res.compressed is False
    assert res.messages == msgs


def test_checkpoint_over_threshold_compresses():
    # Build a big transcript to exceed the default 100k trigger.
    big = "word " * 40000  # ~40k tokens
    msgs = [
        ChatMessage("user", big),
        ChatMessage("assistant", big),
        ChatMessage("user", "final question?"),
    ]
    cfg = CheckpointConfig(trigger_tokens=10_000, tail_message_count=1)
    res = checkpoint(msgs, _fake_summarizer, config=cfg)
    assert res.compressed is True
    assert res.llm_compressed is True
    # tail (the final question) is preserved verbatim
    assert any(m.content == "final question?" for m in res.messages)
    # summary message present
    assert any(m.content.startswith("[CONTEXT COMPACTION") for m in res.messages)


def test_checkpoint_incremental_uses_previous_summary():
    big = "word " * 40000
    msgs = [ChatMessage("user", big), ChatMessage("assistant", big)]
    cfg = CheckpointConfig(trigger_tokens=10_000, tail_message_count=0)
    res1 = checkpoint(msgs, _fake_summarizer, config=cfg, previous_summary=None, previous_last_index=-1)
    assert res1.compressed
    # Second pass should call incremental prompt with the previous summary.
    seen = {}

    def summarizer2(prompt: str) -> str:
        seen["incremental"] = "PREVIOUS SUMMARY:" in prompt
        return "## Active Task\nnext\n"

    msgs2 = [*msgs, ChatMessage("user", big)]
    res2 = checkpoint(
        msgs2,
        summarizer2,
        config=cfg,
        previous_summary=res1.messages[0].content,
        previous_last_index=0,
    )
    assert res2.compressed
    assert seen.get("incremental") is True


def test_token_count_pathological_run_does_not_hang():
    # 5000 unbroken CJK chars would hang naive tiktoken; must return quickly.
    import time

    cjk = "中" * 5000
    t0 = time.time()
    n = count_tokens(cjk)
    dt = time.time() - t0
    assert dt < 1.0, f"token count took too long: {dt:.2f}s"
    assert n > 0


# --- Module 3: workspace diff --------------------------------------------


def _make_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def test_diff_filesystem_added_modified_deleted():
    with tempfile.TemporaryDirectory() as d:
        before = Path(d) / "before"
        after = Path(d) / "after"
        _make_tree(before, {"a.txt": "one", "b.txt": "keep"})
        _make_tree(after, {"a.txt": "one-changed", "c.txt": "new"})
        diff = compare_snapshots(str(before), str(after), str(after))
        assert isinstance(diff, WorkspaceDiff)
        by_path = {c.path: c for c in diff.changes}
        assert "a.txt" in by_path
        assert by_path["a.txt"].change_type == "modified"
        assert "b.txt" in by_path
        assert by_path["b.txt"].change_type == "deleted"
        assert "c.txt" in by_path
        assert by_path["c.txt"].change_type == "added"


def test_diff_ignores_node_modules():
    with tempfile.TemporaryDirectory() as d:
        before = Path(d) / "before"
        after = Path(d) / "after"
        _make_tree(before, {"good.txt": "x"})
        _make_tree(after, {"good.txt": "x", "node_modules/lib/index.js": "y"})
        diff = compare_snapshots(str(before), str(after), str(after))
        paths = {c.path for c in diff.changes}
        assert "node_modules/lib/index.js" not in paths


def test_diff_within_git_repo():
    import subprocess

    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        (repo / "f.py").write_text("print(1)\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
        (repo / "f.py").write_text("print(1)\nprint(2)\n")
        diff = compare_snapshots(str(repo), str(repo), str(repo))
        assert diff.kind == "git"
        assert any(c.path == "f.py" for c in diff.changes)
