"""Shared prompt/config interpolation for the substrate node executor.

Mirrors the sandbox node's ``{{ inputs.<key> }}`` rendering (see
``node_executor.py`` ``_handle_sandbox_node``) so that non-sandbox node types
(LLM, RAG, web search, ...) can also substitute a run's ``input_data`` into
their config.

We deliberately use a regex substitution rather than ``str.format``: many
config values (e.g. sandbox wrappers, JSON, code) carry literal ``{``/``}``
braces that ``str.format`` would choke on.
"""

from __future__ import annotations

import re
from typing import Any

# Matches {{ inputs.foo }} with optional surrounding whitespace.
_INPUTS_PATTERN = re.compile(r"\{\{\s*inputs\.(\w+)\s*\}\}")


def interpolate_inputs(text: str, inputs: dict[str, Any] | None) -> str:
    """Substitute ``{{ inputs.<key> }}`` placeholders in *text*.

    Args:
        text: the template string (prompt, query, etc.).
        inputs: the run's input values, keyed by name. May be ``None`` or
            empty — in which case the text is returned unchanged.

    Returns:
        The text with every ``{{ inputs.<key> }}`` occurrence replaced by the
        string form of ``inputs[<key>]``. Unknown keys are left verbatim so a
        missing input never silently mangles the template.
    """
    if not text or not inputs:
        return text
    return _INPUTS_PATTERN.sub(
        lambda m: str(inputs.get(m.group(1), m.group(0))),
        text,
    )
