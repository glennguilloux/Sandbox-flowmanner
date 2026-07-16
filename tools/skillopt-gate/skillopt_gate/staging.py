"""Staging: write a reviewed proposal to disk; optional secret redaction.

By default the optimizer only STAGES — it never mutates a live skill. The
proposal is written to ``<skill>.staged/`` with the candidate skill, the
gate decision, and per-edit reports. A human (or an explicit ``--adopt``)
applies it. This matches Hermes autonomy rules.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

_SECRET_KEYS = {"api_key", "openai_api_key", "anthropic_api_key", "azure_api_key"}
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]{8,})|(AKIA[0-9A-Z]{16})")


def redact_secrets(obj: Any) -> Any:
    """Recursively redact secret-looking strings/keys in a structure."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _SECRET_KEYS and isinstance(v, str):
                out[k] = ("*" * 4 + v[-4:]) if len(v) > 4 else "****"
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(obj, list):
        return [redact_secrets(x) for x in obj]
    if isinstance(obj, str):
        return _SECRET_RE.sub(lambda m: m.group(0)[:4] + "[redacted]", obj)
    return obj


@dataclass
class StageResult:
    staging_dir: str
    candidate_skill_path: str
    report_path: str
    diagnostics_path: str | None = None


def write_staging(
    *,
    live_skill_path: str,
    report: dict,
    candidate_skill: str,
    per_edit_reports: list[dict],
) -> StageResult:
    """Write the proposal to ``<live>.staged/``. Never overwrites the live file."""
    base = live_skill_path + ".staged"
    os.makedirs(base, exist_ok=True)
    cand_path = os.path.join(base, "best_skill.proposed.md")
    with open(cand_path, "w", encoding="utf-8") as f:
        f.write(candidate_skill)

    report_path = os.path.join(base, "report.json")
    payload = {
        "gate_action": report.get("action"),
        "candidate_score": report.get("candidate_score"),
        "current_score": report.get("current_score"),
        "best_score": report.get("best_score"),
        "n_edits": len(per_edit_reports),
        "per_edit": per_edit_reports,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(redact_secrets(payload), f, indent=2, ensure_ascii=False)

    return StageResult(
        staging_dir=base,
        candidate_skill_path=cand_path,
        report_path=report_path,
    )


def adopt(staging_dir: str, live_skill_path: str) -> str:
    """Apply a staged ``best_skill.proposed.md`` to the live skill, write backup."""
    cand_path = os.path.join(staging_dir, "best_skill.proposed.md")
    if not os.path.exists(cand_path):
        raise FileNotFoundError(f"no staged candidate at {cand_path}")
    with open(cand_path, encoding="utf-8") as f:
        new_text = f.read()
    backup = live_skill_path + ".bak"
    if os.path.exists(live_skill_path):
        with open(live_skill_path, encoding="utf-8") as f:
            old = f.read()
        with open(backup, "w", encoding="utf-8") as f:
            f.write(old)
    with open(live_skill_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return backup
