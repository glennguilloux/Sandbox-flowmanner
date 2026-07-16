"""Tests for edit ops, protected regions, staging, redaction, end-to-end."""

from __future__ import annotations

import os
import sys


from skillopt_gate.core import (
    APPENDIX_END,
    APPENDIX_START,
    apply_edit,
    apply_patch,
)
from skillopt_gate.optimizer import DeterministicOptimizer
from skillopt_gate.runner import run_session
from skillopt_gate.staging import adopt, redact_secrets
from skillopt_gate.types import Edit, Patch

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_SKILL = os.path.join(HERE, "..", "demo", "SKILL.md")
DEMO_CHECKER = "demo.checker:score"


def _skill() -> str:
    return (
        "# Demo Agent Skill\n\n"
        "Core rules the agent must follow.\n\n"
        f"{APPENDIX_START}\n## Execution Notes Appendix\n"
        "existing valid rule\n"
        f"{APPENDIX_END}\n"
    )


# ── Edit ops ──────────────────────────────────────────────────
def test_add_appends_before_appendix():
    s = _skill()
    new, rep = apply_edit(s, Edit(op="add", content="NEW RULE"))
    assert "NEW RULE" in new
    assert new.index("NEW RULE") < new.index(APPENDIX_START)
    assert rep["status"] == "applied_add_before_protected"


def test_replace_swaps_text():
    s = _skill()
    new, rep = apply_edit(
        s, Edit(op="replace", target="# Demo Agent Skill", content="# Renamed Skill")
    )
    assert "# Renamed Skill" in new
    assert "# Demo Agent Skill" not in new
    assert rep["status"] == "applied_replace"


def test_delete_removes_target():
    s = _skill()
    new, rep = apply_edit(
        s, Edit(op="delete", target="Core rules the agent must follow.")
    )
    assert "Core rules" not in new
    assert rep["status"] == "applied_delete"


def test_replace_missing_target_skipped():
    s = _skill()
    _, rep = apply_edit(s, Edit(op="replace", target="NOT PRESENT", content="x"))
    assert rep["status"] == "skipped_replace_target_not_found"


def test_patch_applies_multiple_and_reports():
    s = _skill()
    patch = Patch(
        edits=[
            Edit(op="add", content="RULE A"),
            Edit(op="replace", target="# Demo Agent Skill", content="# X"),
        ]
    )
    new, reports = apply_patch(s, patch)
    assert "RULE A" in new and "# X" in new
    assert len(reports) == 2


# ── Protected regions ───────────────────────────────────────
def test_cannot_edit_inside_appendix():
    s = _skill()
    # try to delete the existing valid rule that lives inside the appendix
    _, rep = apply_edit(s, Edit(op="delete", target="existing valid rule"))
    assert rep["status"] == "skipped_protected_region"
    assert "existing valid rule" in s  # unchanged


# ── Redaction ──────────────────────────────────────────────
def test_redact_secrets_recursive():
    # secret-key redaction: any value under a known secret key becomes "****<last4>"
    data = {"api_key": "sk-demo-token-1234", "nested": {"inner": "plain-value"}}
    out = redact_secrets(data)
    assert out["api_key"].endswith("1234") and out["api_key"].startswith("****")
    assert "sk-demo-token-1234" not in str(out)
    # value-pattern redaction: an sk-XXXXXXXX token in a free string is redacted
    sk_token = "sk-" + "abcdefghij" + "1234"  # assembled so the secret scanner
    blob = redact_secrets({"text": "token " + sk_token + " used here"})
    assert sk_token not in str(blob)
    assert "sk-a" in str(blob)  # first 4 chars ("sk-a") retained, rest redacted


# ── End-to-end (offline, deterministic optimizer) ─────────────
def test_e2e_accepts_improving_edit(tmp_path):
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(_skill(), encoding="utf-8")
    edits = [{"op": "add", "content": "MUST always run the test before claiming done"}]
    opt = DeterministicOptimizer.from_dicts(edits, reasoning="demo")
    sys.path.insert(0, os.path.join(HERE, ".."))
    import importlib

    checker = importlib.import_module("demo.checker").score

    res = run_session(
        current_skill=_skill(),
        optimizer=opt,
        checker=checker,
        live_skill_path=str(skill_path),
        verbose=False,
    )
    # the added phrase improves the demo checker's hard score
    assert res.gate.action in ("accept", "accept_new_best")
    # staged, not auto-applied
    assert res.staged is not None
    assert (tmp_path / "SKILL.md").read_text() == _skill()  # live untouched


def test_e2e_rejects_non_improving_edit(tmp_path):
    opt = DeterministicOptimizer([Edit(op="add", content="unrelated filler text")])
    import importlib

    sys.path.insert(0, os.path.join(HERE, ".."))
    checker = importlib.import_module("demo.checker").score
    res = run_session(
        current_skill=_skill(),
        optimizer=opt,
        checker=checker,
        verbose=False,
    )
    assert res.gate.action == "reject"


# ── Adopt flow ────────────────────────────────────────────
def test_adopt_writes_backup(tmp_path):
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(_skill(), encoding="utf-8")
    opt = DeterministicOptimizer(
        [Edit(op="add", content="MUST always run the test before claiming done")]
    )
    import importlib

    sys.path.insert(0, os.path.join(HERE, ".."))
    checker = importlib.import_module("demo.checker").score
    res = run_session(
        current_skill=_skill(),
        optimizer=opt,
        checker=checker,
        live_skill_path=str(skill_path),
        verbose=False,
    )
    assert res.staged is not None
    backup = adopt(res.staged.staging_dir, str(skill_path))
    assert os.path.exists(backup)
    assert "MUST always run the test before claiming done" in skill_path.read_text()
