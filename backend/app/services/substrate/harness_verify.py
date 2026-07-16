"""Re-export the prototype's canonical ``verify_candidate`` static gate.

The meta-optimizer (``.sisyphus/prototypes/harness_meta_optimizer.py``) owns
the structural feasibility gate (edge-target validation, forbidden tools,
personal-memory constraint invariants). The evaluator shim MUST use the SAME
function so a candidate rejected by the optimizer cannot later pass the evaluator
with a divergent reimplementation.

This module locates the prototype on disk and re-exports ``verify_candidate``.
If the prototype cannot be found, it raises loudly -- we never fall back to a
silently different gate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_CANDIDATE_PATHS = [
    Path(__file__).resolve().parents[4] / ".sisyphus" / "prototypes" / "harness_meta_optimizer.py",
    Path("/opt/flowmanner/.sisyphus/prototypes/harness_meta_optimizer.py"),
]


def _load_verify_candidate():
    for path in _CANDIDATE_PATHS:
        if path.exists():
            spec = importlib.util.spec_from_file_location("harness_meta_optimizer_proto", str(path))
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            # The prototype imports only stdlib + optional yaml; keep it isolated
            # from any ambient backend state by loading it under a unique name.
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module.verify_candidate
    raise RuntimeError(
        "Could not locate the harness meta-optimizer prototype "
        "(.sisyphus/prototypes/harness_meta_optimizer.py) to reuse verify_candidate. "
        "Evaluator safety gate cannot diverge from the optimizer's gate."
    )


verify_candidate = _load_verify_candidate()
