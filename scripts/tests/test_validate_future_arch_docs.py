from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / "scripts" / "validate_future_arch_docs.py"
DOCS_ROOT = REPO_ROOT / "docs" / "future-architecture"
ROADMAP = REPO_ROOT / "docs" / "REBUILD-ROADMAP.md"


def run_validator(root: Path, roadmap: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--root", str(root), "--roadmap", str(roadmap)],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def remove_stop_gate_section(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    marker = "## Stop Gates\n"
    start = text.index(marker)
    next_heading = text.find("\n## ", start + len(marker))
    if next_heading == -1:
        modified = text[:start]
    else:
        modified = text[:start] + text[next_heading + 1 :]
    doc.write_text(modified, encoding="utf-8")


def replace_nats_line(doc: Path, replacement: str) -> None:
    text = doc.read_text(encoding="utf-8")
    target = "- No NATS before outbox and event-schema stability.\n"
    if target not in text:
        raise AssertionError(f"expected NATS stop-gate line not found in {doc}")
    doc.write_text(text.replace(target, f"- {replacement}\n"), encoding="utf-8")


def remove_nats_line(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    target = "- No NATS before outbox and event-schema stability.\n"
    if target not in text:
        raise AssertionError(f"expected NATS stop-gate line not found in {doc}")
    doc.write_text(text.replace(target, ""), encoding="utf-8")


def test_current_pack_validation_passes() -> None:
    proc = run_validator(DOCS_ROOT, ROADMAP)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "docs_validated=9" in proc.stdout
    assert "stop_gates=6" in proc.stdout
    assert "validation=pass" in proc.stdout


def test_current_pack_accepts_nats_slash_variant(tmp_path: Path) -> None:
    tmp_docs = tmp_path / "future-architecture"
    shutil.copytree(DOCS_ROOT, tmp_docs)
    replace_nats_line(tmp_docs / "01-paradigm-evaluation.md", "No NATS before outbox/event-schema stability.")

    proc = run_validator(tmp_docs, ROADMAP)
    output = proc.stdout + proc.stderr

    assert proc.returncode == 0, output


def test_missing_required_non_goal_section_fails_with_name(tmp_path: Path) -> None:
    tmp_docs = tmp_path / "future-architecture"
    shutil.copytree(DOCS_ROOT, tmp_docs)
    remove_stop_gate_section(tmp_docs / "01-paradigm-evaluation.md")

    proc = run_validator(tmp_docs, ROADMAP)
    output = proc.stdout + proc.stderr

    assert proc.returncode != 0
    assert "01-paradigm-evaluation.md" in output
    assert "missing non-goal/stop gate" in output
    assert "no microservices default" in output
    assert "No microservices default." in output
    assert "no NATS before outbox and event-schema stability" in output
    assert "No NATS before outbox and event-schema stability." in output
    assert "No NATS before outbox/event-schema stability." in output
    assert "no Kubernetes-only self-hosting" in output
    assert "No Kubernetes-only self-hosting." in output


def test_missing_single_nats_stop_gate_fails_with_name(tmp_path: Path) -> None:
    tmp_docs = tmp_path / "future-architecture"
    shutil.copytree(DOCS_ROOT, tmp_docs)
    remove_nats_line(tmp_docs / "01-paradigm-evaluation.md")

    proc = run_validator(tmp_docs, ROADMAP)
    output = proc.stdout + proc.stderr

    assert proc.returncode != 0
    assert "01-paradigm-evaluation.md" in output
    assert "missing non-goal/stop gate: no NATS before outbox and event-schema stability" in output
    assert "No NATS before outbox and event-schema stability." in output
    assert "No NATS before outbox/event-schema stability." in output
    assert "no microservices default" not in output
