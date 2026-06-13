from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SNAPSHOT_PATH = BACKEND_ROOT / "scripts" / "model_snapshot.json"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.snapshot_diff import diff_snapshots


def _load_committed_snapshot() -> dict:
    assert SNAPSHOT_PATH.exists()
    return json.loads(SNAPSHOT_PATH.read_text())


def _fresh_snapshot() -> dict:
    command = [
        sys.executable,
        "-c",
        "import json; from app.models import Base; from scripts.snapshot_model_metadata import build_snapshot; print(json.dumps(build_snapshot(Base.metadata), sort_keys=True))",
    ]
    result = subprocess.run(command, cwd=BACKEND_ROOT, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _table_by_name(snapshot: dict) -> dict[str, dict]:
    return {table["name"]: table for table in snapshot["tables"]}


def test_snapshot_file_exists_and_is_valid_json():
    snapshot = _load_committed_snapshot()

    assert set(snapshot) == {"alembic_version", "generated_at", "model_count", "tables"}
    assert isinstance(snapshot["tables"], list)
    assert snapshot["model_count"] == len(snapshot["tables"])


def test_snapshot_matches_current_metadata():
    committed = _load_committed_snapshot()
    fresh = _fresh_snapshot()

    assert fresh["tables"] == committed["tables"]


def test_snapshot_diff_catches_introduced_column():
    committed = _load_committed_snapshot()
    fresh = _fresh_snapshot()
    mutated = copy.deepcopy(fresh)

    users = _table_by_name(mutated)["users"]
    users["columns"]["__test_introduced"] = "VARCHAR(50)"

    diff = diff_snapshots(committed, mutated)
    matching = [line for line in diff if "__test_introduced" in line]

    assert len(diff) == 1
    assert matching == ["+ tables.users.columns.__test_introduced = VARCHAR(50) (added)"]


@pytest.mark.integration
def test_step_2_offline_render_still_works():
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend", "alembic", "upgrade", "head", "--sql"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        pytest.skip("docker CLI is unavailable inside the backend container")

    assert result.returncode == 0, result.stderr or result.stdout
    assert any(token in result.stdout for token in ("CREATE", "ALTER", "BEGIN"))


def test_snapshot_diff_silent_on_identical():
    fresh = _fresh_snapshot()

    assert diff_snapshots(fresh, fresh) == []
