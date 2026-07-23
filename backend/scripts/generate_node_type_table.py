#!/usr/bin/env python3
"""Generate a markdown table of substrate node types and their config keys.

Parses the substrate executor and workflow models with the AST, maps each
NodeType to its handler, collects every ``node.config.get("key")`` call in
that handler, and emits a markdown table.

Usage:
    python backend/scripts/generate_node_type_table.py > backend/docs/substrate-node-types-table.md
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW_MODELS = PROJECT_ROOT / "backend" / "app" / "services" / "substrate" / "workflow_models.py"
NODE_EXECUTOR = PROJECT_ROOT / "backend" / "app" / "services" / "substrate" / "node_executor.py"
LINTER = PROJECT_ROOT / "backend" / "scripts" / "lint_blueprints.py"


def _extract_node_types(path: Path) -> list[tuple[str, str]]:
    """Return NodeType enum (name, value) pairs in definition order."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "NodeType":
            return [
                (target.id, str(stmt.value.value))
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                for target in stmt.targets
                if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Constant)
            ]
    return []


def _find_dispatch_mapping(tree: ast.Module, node_type_values: dict[str, str]) -> dict[str, str]:
    """Map NodeType value -> handler method name from _dispatch's match/case."""
    mapping: dict[str, str] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "_dispatch":
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Match):
                continue
            for case in stmt.cases:
                pattern = case.pattern
                handler_call: str | None = None

                # Find the first await call inside the case body; assume it is
                # the dispatch target (e.g. self._handle_llm(...)).
                for body_stmt in case.body:
                    for child in ast.walk(body_stmt):
                        if isinstance(child, ast.Await):
                            call = child.value
                            if isinstance(call, ast.Call):
                                func = call.func
                                if isinstance(func, ast.Attribute):
                                    handler_call = func.attr
                                elif isinstance(func, ast.Name):
                                    handler_call = func.id
                                break
                    if handler_call:
                        break

                if handler_call is None:
                    continue

                def _patterns_to_names(pat: Any) -> list[str]:
                    names: list[str] = []
                    if isinstance(pat, ast.MatchValue) and isinstance(pat.value, ast.Attribute):
                        names.append(pat.value.attr)
                    elif isinstance(pat, ast.MatchOr):
                        for p in pat.patterns:
                            names.extend(_patterns_to_names(p))
                    return names

                for enum_name in _patterns_to_names(pattern):
                    value = node_type_values.get(enum_name)
                    if value is not None:
                        mapping[value] = handler_call
    return mapping


def _extract_required_config(path: Path) -> tuple[dict[str, set[str]], dict[str, list[set[str]]]]:
    """Parse the linter and return required/alt config keys per node type.

    Returns ``(required, alt_groups)`` where:

    * ``required[node_type]`` is the set of individually required keys.
    * ``alt_groups[node_type]`` is a list of alternative-key groups; at least
      one key from each group must be present.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    required: dict[str, set[str]] = {}
    alt_groups: dict[str, list[set[str]]] = {}

    for node in ast.walk(tree):
        # Handle both `X = {...}` and `X: Type = {...}` (AnnAssign).
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or node.target.id != "REQUIRED_NODE_CONFIG":
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            items = list(zip(node.value.keys, node.value.values, strict=False))
        elif isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name) and t.id == "REQUIRED_NODE_CONFIG"]
            if not targets or not isinstance(node.value, ast.Dict):
                continue
            items = list(zip(node.value.keys, node.value.values, strict=False))
        else:
            continue

        for key_expr, value_expr in items:
            if not isinstance(key_expr, ast.Constant) or not isinstance(key_expr.value, str):
                continue
            node_type = key_expr.value
            if not isinstance(value_expr, ast.List):
                continue
            required.setdefault(node_type, set())
            alt_groups.setdefault(node_type, [])
            for item in value_expr.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    required[node_type].add(item.value)
                elif isinstance(item, ast.List):
                    group: set[str] = set()
                    for alt in item.elts:
                        if isinstance(alt, ast.Constant) and isinstance(alt.value, str):
                            group.add(alt.value)
                    if group:
                        alt_groups[node_type].append(group)

    return required, alt_groups


def _collect_config_keys(tree: ast.Module) -> dict[str, set[str]]:
    """Map handler method name -> set of node.config.get keys."""
    handler_keys: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if not node.name.startswith("_handle_"):
            continue
        keys: set[str] = set()
        for child in ast.walk(node):
            # Match node.config.get("key", default)
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr != "get":
                continue
            if not isinstance(func.value, ast.Attribute):
                continue
            if func.value.attr != "config":
                continue
            if not func.value.value or not isinstance(func.value.value, ast.Name):
                continue
            if func.value.value.id != "node":
                continue
            for arg in child.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.add(arg.value)
                break
        handler_keys[node.name] = keys

    return handler_keys


def _format_key(key: str, required: set[str], alt_groups: list[set[str]]) -> str:
    """Return a key string annotated with required/optional status."""
    if key in required:
        return f"`{key}` (R)"
    for group in alt_groups:
        if key in group:
            return f"`{key}` (Ralt)"
    return f"`{key}` (O)"


def generate_table() -> str:
    node_type_pairs = _extract_node_types(WORKFLOW_MODELS)
    node_type_values = dict(node_type_pairs)
    executor_tree = ast.parse(NODE_EXECUTOR.read_text(encoding="utf-8"))
    dispatch = _find_dispatch_mapping(executor_tree, node_type_values)
    handler_keys = _collect_config_keys(executor_tree)
    required, alt_groups = _extract_required_config(LINTER)

    lines = [
        "# Substrate Node Type Config Table\n",
        "This table is generated automatically from the substrate source.\n\n",
        "**Legend:** `(R)` = required, `(O)` = optional, `(Ralt)` = one of a group of "
        "alternatives must be provided. A `—` means the node is a passthrough with no "
        "handler or no config keys read by the handler.\n",
        "| Node type | Handler | Config keys |",
        "|-----------|---------|-------------|",
    ]

    for _enum_name, value in node_type_pairs:
        handler = dispatch.get(value, "—")
        keys = handler_keys.get(handler, set())
        node_required = required.get(value, set())
        node_alt_groups = alt_groups.get(value, [])
        keys_str = ", ".join(_format_key(k, node_required, node_alt_groups) for k in sorted(keys)) if keys else "—"
        lines.append(f"| `{value}` | `{handler}` | {keys_str} |")

    lines.append("\n## HITL Output Contract\n")
    lines.append(
        "Nodes of type `approval` and `human_review` pause execution until a human "
        "resolves the created inbox item. On resume, the resolved node returns a dict "
        "under `output` with the following keys:\n"
    )
    lines.append("\n| Key | Type | Description |")
    lines.append("|-----|------|-------------|")
    lines.append(
        "| `hitl_resolution` | string | Resolution status returned by the resolver. "
        "One of `approved`, `clarified`, `rejected`, `expired`, or `cancelled`. |"
    )
    lines.append(
        "| `resolution_payload` | dict \\| null | Optional payload supplied by the resolver "
        "(e.g. form data, selected values, structured notes). |"
    )
    lines.append("| `resolution_note` | string \\| null | Free-text note left by the resolver. |")
    lines.append("| `inbox_item_id` | string | UUID of the resolved inbox item. |")
    lines.append(
        "\nThe top-level node result sets `success: true` for `approved`/`clarified`\n"
        "and `success: false` (with an `error` key) for `rejected`/`expired`/`cancelled`. "
        "Blueprint conditions should branch on `inputs['<node_id>']['hitl_resolution']` "
        "using these exact strings.\n"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    output = generate_table()
    dest = PROJECT_ROOT / "backend" / "docs" / "substrate-node-types-table.md"
    dest.write_text(output, encoding="utf-8")
    print(f"Generated {dest}")
