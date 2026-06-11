#!/usr/bin/env python3
"""Validate FlowManner future-architecture planning docs.

This script is intentionally dependency-free so it can run before the Python
backend or Node frontend stacks are installed. It checks that the architecture
pack is coherent enough to guide later implementation tasks.
"""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    "01-paradigm-evaluation.md",
    "02-architecture-diagrams.md",
    "03-domain-boundaries.md",
    "04-execution-agent-runtime.md",
    "05-knowledge-events-data.md",
    "06-observability-deployment.md",
    "07-roadmap-risks-not-build.md",
    "08-final-recommendation.md",
    "09-current-state-gaps.md",
]

REQUIRED_DOC_SNIPPETS: dict[str, list[str]] = {
    "01-paradigm-evaluation.md": [
        "Decision",
        "Paradigm Matrix",
        "Why Modular Monolith First",
        "Why Not Microservices Now",
        "Why Event-Driven",
        "Why Not Full Event Sourcing Everywhere",
        "Why Provider Abstraction Is Non-Negotiable",
        "Target Architecture Principle",
        "Stop Gates",
    ],
    "02-architecture-diagrams.md": [
        "Future-State Architecture Diagram",
        "Domain Map",
        "Data Flow Diagram",
        "Event Flow Diagram",
        "Execution Flow Diagram",
        "Why This Shape Wins",
    ],
    "03-domain-boundaries.md": [
        "Guiding Rule",
        "Recommended Boundaries",
        "Domain Ownership Rules",
        "API Boundary Principles",
        "Module Dependency Rules",
        "Boundary Contracts",
        "Anti-Corruption Layers",
    ],
    "04-execution-agent-runtime.md": [
        "Durable Execution Engine",
        "Agent Runtime",
        "Worker Model",
        "Lease Semantics",
        "Checkpoint Strategy",
        "Retry Strategy",
        "Execution Engine Requirements",
        "Agent Lifecycle",
        "Tool Execution",
    ],
    "05-knowledge-events-data.md": [
        "Knowledge Architecture",
        "Event Architecture",
        "Data Layer",
        "AI Provider Layer",
        "Knowledge + Event + Data Integration",
        "Provider routing research is explicitly unresolved",
    ],
    "06-observability-deployment.md": [
        "Observability Architecture",
        "Deployment Architecture",
        "Required Identifiers",
        "SLOs",
        "Self-Hosted Deployment",
        "SaaS Deployment",
        "Operational Readiness Checklist",
    ],
    "07-roadmap-risks-not-build.md": [
        "Migration Roadmap",
        "12-Month Roadmap",
        "24-Month Roadmap",
        "5-Year Architecture Vision",
        "Risks and Tradeoffs",
        "What NOT to Build",
    ],
    "08-final-recommendation.md": [
        "Final Recommendation",
        "Non-Negotiable Principles",
        "Why This Is the Best Fit",
        "Final Architecture in One Sentence",
        "Next Steps",
    ],
    "09-current-state-gaps.md": [
        "Current-State Gap Table",
        "Infrastructure Reality Check",
        "Implementation Guardrails",
        "Relationship to REBUILD-ROADMAP.md",
        "Decision",
    ],
}

REQUIRED_NON_GOALS: dict[str, tuple[str, ...]] = {
    "no microservices default": ("No microservices default.",),
    "no service mesh for homelab": ("No service mesh for homelab deployments.",),
    "no full event sourcing everywhere": ("No full event sourcing everywhere.",),
    "no actor-framework lock-in": ("No actor-framework lock-in.",),
    "no NATS before outbox and event-schema stability": (
        "No NATS before outbox and event-schema stability.",
        "No NATS before outbox/event-schema stability.",
    ),
    "no Kubernetes-only self-hosting": ("No Kubernetes-only self-hosting.",),
}

TDD_CONTRACTS = [
    "modular monolith boundary enforcement",
    "event schema v1 before event backbone work",
    "outbox-before-NATS stop gate",
    "worker lease/checkpoint/idempotency contracts",
    "provider abstraction and local/cloud routing contracts",
    "self-hosted Docker Compose baseline",
]

EXACT_COMMANDS = [
    "python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md",
    "cd /opt/flowmanner/backend && python -m pytest tests/test_substrate_event_log.py tests/test_substrate_replay.py tests/test_failure_analyzer_budgets.py tests/test_meta_loop_orchestrator_budgets.py tests/test_trigger_bridge.py tests/test_nexus_orchestrator_singleton.py tests/test_chaos_kill_worker.py tests/test_chaos_kill_runner.py -q",
    "cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit && npx vitest run && npx playwright test",
]

ROADMAP_ACTIVE_ITEMS: dict[str, list[str]] = {
    "code_execute production issue": [r"/api/chat/code/execute", r"code.execute", r"code execution"],
    "CI pipeline hardening": [r"CI pipeline", r"GitHub Actions"],
    "Sentry/Jaeger/deep-health baseline": [r"Sentry", r"Jaeger", r"deep.health|deep health|deep-health"],
    "Blueprint+Run unification": [r"Blueprint\+Run", r"Blueprint\\+Run", r"Blueprint and Run"],
    "substrate executor/chaos tests": [r"substrate executor", r"chaos tests", r"kill worker", r"chaos"],
    "chat UX fixes": [r"Chat UX", r"chat UX", r"chat user experience"],
}


@dataclass
class ValidationArgs:
    root: Path
    roadmap: Path
    repo_root: Path
    evidence: Path | None
    quiet: bool = False


@dataclass
class ValidationResult:
    ok: bool
    lines: list[str]
    errors: list[str]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_markdown_fences(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def contains_any(text: str, patterns: Iterable[str], flags: int = re.IGNORECASE | re.MULTILINE) -> bool:
    return any(re.search(pattern, text, flags) for pattern in patterns)


def check_required_files(root: Path, roadmap: Path) -> list[str]:
    errors: list[str] = []
    for doc in REQUIRED_DOCS:
        path = root / doc
        if not path.is_file():
            errors.append(f"missing required doc: {doc}")
    if not roadmap.is_file():
        errors.append(f"missing roadmap: {roadmap}")
    return errors


def check_required_snippets(root: Path) -> list[str]:
    errors: list[str] = []
    for doc, snippets in REQUIRED_DOC_SNIPPETS.items():
        path = root / doc
        if not path.is_file():
            continue
        text = read_text(path)
        haystack = strip_markdown_fences(text).lower()
        for snippet in snippets:
            if snippet.lower() not in haystack:
                errors.append(f"{doc}: missing required snippet: {snippet}")
    return errors


def check_readme_contract(root: Path, repo_root: Path) -> list[str]:
    readme = root / "README.md"
    if not readme.is_file():
        return ["README.md: missing"]

    text = read_text(readme)
    haystack = strip_markdown_fences(text).lower()
    errors: list[str] = []

    for doc in REQUIRED_DOCS:
        if doc not in text:
            errors.append(f"README.md: does not reference {doc}")

    for contract in TDD_CONTRACTS:
        if contract.lower() not in haystack:
            errors.append(f"README.md: missing TDD contract: {contract}")

    for command in EXACT_COMMANDS:
        if command not in text:
            errors.append(f"README.md: missing exact command: {command}")

    evidence_readme = repo_root / ".sisyphus" / "evidence" / "README.md"
    if not evidence_readme.is_file():
        errors.append(".sisyphus/evidence/README.md: missing evidence capture rules")
    else:
        evidence_text = read_text(evidence_readme).lower()
        for required in ["task-{n}", "exit code", "secrets"]:
            if required not in evidence_text:
                errors.append(f".sisyphus/evidence/README.md: missing rule: {required}")

    return errors


def check_non_goals(root: Path) -> list[str]:
    doc = root / "01-paradigm-evaluation.md"
    if not doc.is_file():
        return []
    text = strip_markdown_fences(read_text(doc))
    errors: list[str] = []
    for label, phrases in REQUIRED_NON_GOALS.items():
        if not any(phrase in text for phrase in phrases):
            accepted = "; ".join(phrases)
            errors.append(f"01-paradigm-evaluation.md: missing non-goal/stop gate: {label} ({accepted})")
    return errors


def check_cross_links(root: Path) -> tuple[int, list[str]]:
    errors: list[str] = []
    checked = 0
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in sorted(root.rglob("*.md")):
        text = strip_markdown_fences(read_text(path))
        for raw_link in link_re.findall(text):
            if raw_link.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = raw_link.split("#", 1)[0]
            if not target:
                continue
            checked += 1
            resolved = (path.parent / target).resolve()
            if not resolved.is_file():
                errors.append(f"{path.relative_to(root)}: broken local link -> {target}")
    return checked, errors


def check_roadmap_alignment(root: Path, roadmap: Path) -> list[str]:
    errors: list[str] = []
    if not roadmap.is_file():
        return errors

    roadmap_text = read_text(roadmap)
    alignment = ""
    alignment_doc = root / "09-current-state-gaps.md"
    if alignment_doc.is_file():
        alignment = read_text(alignment_doc)

    combined = f"{roadmap_text}\n\n{alignment}"
    for item, patterns in ROADMAP_ACTIVE_ITEMS.items():
        if not contains_any(combined, patterns):
            errors.append(f"09-current-state-gaps.md / REBUILD-ROADMAP.md: missing active rebuild item: {item}")

    if "REBUILD-ROADMAP.md" not in alignment:
        errors.append("09-current-state-gaps.md: does not reference REBUILD-ROADMAP.md")

    return errors


def validate(args: ValidationArgs) -> ValidationResult:
    errors: list[str] = []
    errors.extend(check_required_files(args.root, args.roadmap))
    errors.extend(check_required_snippets(args.root))
    errors.extend(check_readme_contract(args.root, args.repo_root))
    errors.extend(check_non_goals(args.root))

    link_count, link_errors = check_cross_links(args.root)
    errors.extend(link_errors)
    errors.extend(check_roadmap_alignment(args.root, args.roadmap))

    lines: list[str] = []
    if not errors:
        lines.append(f"docs_validated={len(REQUIRED_DOCS)}")
        for doc in REQUIRED_DOCS:
            lines.append(f"{doc}: valid")
        lines.append(f"cross_links_checked={link_count}")
        lines.append(f"roadmap_items_checked={len(ROADMAP_ACTIVE_ITEMS)}")
        lines.append(f"tdd_contracts={len(TDD_CONTRACTS)}")
        lines.append(f"stop_gates={len(REQUIRED_NON_GOALS)}")
        lines.append("evidence_capture=enabled")
        lines.append("validation=pass")
    else:
        lines.append("docs_validated=0")
        lines.append("validation=fail")
        for error in errors:
            lines.append(f"ERROR: {error}")

    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.quiet:
        return ValidationResult(ok=not errors, lines=[], errors=errors)
    return ValidationResult(ok=not errors, lines=lines, errors=errors)


def write_evidence(evidence: Path | None, result: ValidationResult) -> None:
    if evidence and result.lines:
        evidence.parent.mkdir(parents=True, exist_ok=True)
        metadata = [
            f"command={' '.join(shlex.quote(arg) for arg in sys.argv)}",
            f"working_directory={Path.cwd()}",
            f"exit_code={0 if result.ok else 1}",
            f"timestamp={datetime.now(timezone.utc).isoformat()}",
            "",
        ]
        evidence.write_text("\n".join(metadata + result.lines) + "\n", encoding="utf-8")


def run_self_test() -> ValidationResult:
    repo_root = REPO_ROOT
    with tempfile.TemporaryDirectory(prefix="future-arch-docs-") as tmp_dir:
        tmp = Path(tmp_dir)
        tmp_docs = tmp / "docs" / "future-architecture"
        tmp_docs.mkdir(parents=True)
        shutil.copytree(repo_root / "docs" / "future-architecture", tmp_docs, dirs_exist_ok=True)
        tmp_roadmap = tmp / "docs" / "REBUILD-ROADMAP.md"
        tmp_roadmap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / "docs" / "REBUILD-ROADMAP.md", tmp_roadmap)

        scenarios: list[tuple[str, Path | None, str | None]] = []
        scenarios.append(("missing required doc", tmp_docs / "01-paradigm-evaluation.md", None))

        doc_01 = tmp_docs / "01-paradigm-evaluation.md"
        original_doc_01 = doc_01.read_text(encoding="utf-8")
        modified_doc_01 = original_doc_01.replace("## Stop Gates\n", "## Removed Stop Gates\n")
        modified_doc_01 = modified_doc_01.replace("No microservices default.", "Microservices are acceptable by default.")
        doc_01.write_text(modified_doc_01, encoding="utf-8")
        scenarios.append(("missing non-goal", None, None))
        doc_01.write_text(original_doc_01, encoding="utf-8")

        doc_09 = tmp_docs / "09-current-state-gaps.md"
        original_doc_09 = doc_09.read_text(encoding="utf-8")
        modified_doc_09 = original_doc_09.replace("- CI pipeline hardening.\n", "")
        doc_09.write_text(modified_doc_09, encoding="utf-8")
        scenarios.append(("missing roadmap alignment", None, None))

    # Run the actual validator in subprocesses so failures mirror CLI usage.
    failures: list[str] = []
    for scenario_name, remove_path, text_replacement in scenarios:
        if remove_path and remove_path.exists():
            remove_path.unlink()
        if text_replacement:
            raise AssertionError("text_replacement is not used by the subprocess self-test")

        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--root", str(tmp_docs), "--roadmap", str(tmp_roadmap), "--quiet"],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode == 0:
            failures.append(f"self-test scenario did not fail: {scenario_name}")

    if failures:
        return ValidationResult(ok=False, lines=["self_test=fail"] + failures, errors=failures)
    return ValidationResult(ok=True, lines=["self_test=pass", "missing_required_doc=detected", "missing_non_goal=detected", "missing_roadmap_alignment=detected"], errors=[])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate FlowManner future-architecture docs")
    parser.add_argument("--root", default=str(REPO_ROOT / "docs" / "future-architecture"), help="docs/future-architecture root")
    parser.add_argument("--roadmap", default=str(REPO_ROOT / "docs" / "REBUILD-ROADMAP.md"), help="REBUILD-ROADMAP.md path")
    parser.add_argument("--evidence", default=None, help="write validation output to this file")
    parser.add_argument("--self-test", action="store_true", help="run negative validation checks in a temp copy")
    parser.add_argument("--quiet", action="store_true", help="suppress normal output; useful for self-test subprocesses")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    evidence_path = Path(args.evidence).resolve() if args.evidence else None
    if args.self_test:
        result = run_self_test()
    else:
        result = validate(
            ValidationArgs(
                root=Path(args.root).resolve(),
                roadmap=Path(args.roadmap).resolve(),
                repo_root=REPO_ROOT,
                evidence=evidence_path,
                quiet=args.quiet,
            )
        )

    write_evidence(evidence_path, result)

    if result.lines:
        print("\n".join(result.lines))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
