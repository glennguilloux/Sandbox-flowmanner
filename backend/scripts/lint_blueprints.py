#!/usr/bin/env python3
"""Lint/validate all blueprint YAML files in the repository.

Discovers ``*.yaml`` files under ``backend/`` and ``blueprints/`` (and any
other configured directories), parses each once, and runs the existing
``validate_blueprint_definition`` and ``blueprint_to_workflow`` validators from
``app.services.substrate.adapters`` on files that look like blueprints.

Exit code:
    0 if every discovered blueprint passes validation.
    1 if any file fails YAML parsing or substrate validation.

Usage:
    python scripts/lint_blueprints.py [path...]

If no paths are provided, the default search directories are used.
"""

from __future__ import annotations

import argparse
import difflib
import io
import json
import sys
import traceback
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML

# Ensure app imports resolve when the script is run from the backend dir.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.substrate.adapters import (
    InvalidBlueprintGraphError,
    blueprint_to_workflow,
    validate_blueprint_definition,
)

# Directories to scan when no explicit paths are given, relative to the
# repository root (the parent of the backend directory).
DEFAULT_DIRS = ["backend", "blueprints"]

# Directories that commonly contain non-blueprint YAML files (docs, CI, git
# worktrees, virtualenvs, caches, etc.) and should be skipped by default.
DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".github",
        ".venv",
        ".worktrees",
        "docs",
        "Docs",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".codegraph",
        ".sisyphus",
        ".hermes",
        "htmlcov",
        "uploads",
    }
)

# Blueprint files must declare both of these keys at the top level.
REQUIRED_TOP_KEYS = ["version", "name", "blueprint_type", "definition"]

# Type alias for a single required config specifier: either a single key or a
# list of alternative keys (at least one required).
NodeConfigSpec = str | list[str]

# Per-node required config keys. Extend this mapping as the substrate learns
# new node types.
#
# Each value is a list of required config specifiers. A specifier can be:
#   - a string: the key must be present in the node's config.
#   - a list of strings: at least one of the keys must be present.
REQUIRED_NODE_CONFIG: dict[str, list[NodeConfigSpec]] = {
    "split": ["splitOn"],
    "merge": ["mergeStrategy"],
    "sandbox": ["task_prompt"],
    "llm_call": ["prompt"],
    "variable_set": ["varName", ["varValue", "varExpr"]],
    "transform": ["transformType", "transformExpression"],
    "filter": ["transformType", "transformExpression"],
    "llm_eval": ["prompt"],
    "condition": ["expression"],
    "validate_schema": ["schema"],
    "memory_write": ["collection"],
    "memory_read": ["query"],
    "webhook": ["url"],
    "log": ["level", "message"],
    "router": ["routes"],
    "delay": ["delayMs"],
    "retry": ["maxRetries"],
    "timeout": ["timeoutMs"],
    "cache_get": ["key"],
    "browser_navigate": ["params"],
    "browser_click": ["params"],
    "browser_type": ["params"],
    "browser_scroll": ["params"],
}


def _is_excluded(path: Path) -> bool:
    """Return True if ``path`` is inside a directory that should be skipped."""
    return any(part in DEFAULT_EXCLUDED_DIRS for part in path.parts)


def discover_yaml_files(paths: list[Path]) -> list[Path]:
    """Return a sorted list of YAML files under ``paths``.

    ``paths`` may be directories (scanned recursively for *.yaml / *.yml) or
    individual files.  Directories in ``DEFAULT_EXCLUDED_DIRS`` are skipped.
    """
    files: set[Path] = set()
    for path in paths:
        if not path.exists():
            print(f"[WARN] Path not found, skipping: {path}")
            continue
        if path.is_file() and path.suffix.lower() in (".yaml", ".yml"):
            resolved = path.resolve()
            if not _is_excluded(resolved):
                files.add(resolved)
        elif path.is_dir():
            for pattern in ("*.yaml", "*.yml"):
                for candidate in path.rglob(pattern):
                    resolved = candidate.resolve()
                    if not _is_excluded(resolved):
                        files.add(resolved)
    return sorted(files)


def looks_like_blueprint(data: Any) -> bool:
    """Return True if the parsed YAML has the shape of a blueprint definition."""
    return isinstance(data, dict) and "blueprint_type" in data and "definition" in data


def validate_node_constraints(definition: dict) -> list[str]:
    """Return a list of validation errors for per-node required config keys.

    Checks each node in ``definition["nodes"]`` against ``REQUIRED_NODE_CONFIG``.
    Unknown node types are ignored.
    """
    errors: list[str] = []
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return errors

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        if not isinstance(node_type, str):
            continue
        config = node.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        for spec in REQUIRED_NODE_CONFIG.get(node_type, []):
            # spec is either a single required key or a list of alternatives.
            required_keys = [spec] if isinstance(spec, str) else spec

            if not any(key in config for key in required_keys):
                node_id = node.get("id", "<unknown>")
                key_description = " or ".join(required_keys)
                errors.append(
                    f"Node '{node_id}' of type '{node_type}' is missing required config key: {key_description}"
                )

    return errors


def _is_non_empty_string(value: Any) -> bool:
    """Return True if ``value`` is a string with at least one non-whitespace character.

    Example:
        >>> _is_non_empty_string("hello")
        True
        >>> _is_non_empty_string("   ")
        False
        >>> _is_non_empty_string(None)
        False
    """
    return isinstance(value, str) and value.strip() != ""


def _validate_browser_params(
    node_id: str,
    node_type: str,
    config: dict[str, Any],
    *,
    required_param_key: str | None = None,
    require_ref_or_selector: bool = False,
) -> list[str]:
    """Validate the ``params`` mapping for browser action nodes.

    Returns a list of validation errors. ``params`` must be a dict. If
    ``required_param_key`` is provided, it must map to a non-empty string.
    When ``require_ref_or_selector`` is true, at least one of ``params.ref``
    or ``params.selector`` must be a non-empty string.

    Args:
        node_id: Identifier of the node being validated.
        node_type: The node type (e.g. ``browser_click``).
        config: The node's ``config`` mapping.
        required_param_key: Optional key inside ``params`` that must be a non-empty string.
        require_ref_or_selector: If true, require ``params.ref`` or ``params.selector``.

    Returns:
        A list of error strings. Empty when the config is valid.

    Example:
        >>> _validate_browser_params(
        ...     "b1", "browser_click", {"params": {"selector": "#btn"}},
        ...     require_ref_or_selector=True,
        ... )
        []
        >>> _validate_browser_params(
        ...     "b1", "browser_click", {"params": {}}, require_ref_or_selector=True,
        ... )
        ["Node 'b1' of type 'browser_click': config.params must contain either 'ref' or 'selector'"]
    """
    errors: list[str] = []
    params = config.get("params")
    if not isinstance(params, dict):
        errors.append(f"Node '{node_id}' of type '{node_type}': config.params must be a mapping")
        return errors

    if required_param_key is not None:
        value = params.get(required_param_key)
        if not _is_non_empty_string(value):
            errors.append(
                f"Node '{node_id}' of type '{node_type}': config.params.{required_param_key} must be a non-empty string"
            )

    if require_ref_or_selector:
        ref = params.get("ref")
        selector = params.get("selector")
        if not _is_non_empty_string(ref) and not _is_non_empty_string(selector):
            errors.append(
                f"Node '{node_id}' of type '{node_type}': config.params must contain either 'ref' or 'selector'"
            )

    return errors


def _validate_transform_like_node(
    node_id: str,
    node_type: str,
    config: dict[str, Any],
    allowed_types: tuple[str, ...],
    transform_type_error: str,
) -> list[str]:
    """Validate shared transform/filter config keys.

    Returns a list of validation errors for ``transformType`` and
    ``transformExpression``.

    Args:
        node_id: Identifier of the node being validated.
        node_type: The node type (e.g. ``transform`` or ``filter``).
        config: The node's ``config`` mapping.
        allowed_types: Tuple of valid values for ``transformType``.
        transform_type_error: Human-readable error message appended when
            ``transformType`` is not in ``allowed_types``.

    Returns:
        A list of error strings. Empty when the config is valid.

    Example:
        >>> _validate_transform_like_node(
        ...     "f1", "filter", {"transformType": "map"}, ("filter",), "must be filter"
        ... )
        ["Node 'f1' of type 'filter': must be filter", \"Node 'f1' of type 'filter': config.transformExpression must be a non-empty string\"]
    """
    errors: list[str] = []
    transform_type = config.get("transformType")
    if transform_type not in allowed_types:
        errors.append(f"Node '{node_id}' of type '{node_type}': {transform_type_error}")
    transform_expression = config.get("transformExpression")
    if not _is_non_empty_string(transform_expression):
        errors.append(f"Node '{node_id}' of type '{node_type}': config.transformExpression must be a non-empty string")
    return errors


def validate_node_config_values(definition: dict) -> list[str]:
    """Return a list of validation errors for node config *values*.

    This complements :func:`validate_node_constraints` by checking that
    required config values are well-formed (non-empty strings, valid enum
    values, positive numbers, etc.).  Unknown node types are ignored and a
    missing ``config`` is treated as an empty dict.
    """
    errors: list[str] = []
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return errors

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        if not isinstance(node_type, str):
            continue
        node_id = node.get("id", "<unknown>")
        config = node.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        def _error(node_id: str, node_type: str, message: str) -> None:
            errors.append(f"Node '{node_id}' of type '{node_type}': {message}")

        if node_type == "split":
            split_on = config.get("splitOn")
            if not _is_non_empty_string(split_on):
                _error(node_id, node_type, "config.splitOn must be a non-empty string")

        elif node_type == "variable_set":
            var_name = config.get("varName")
            if not _is_non_empty_string(var_name):
                _error(node_id, node_type, "config.varName must be a non-empty string")

        elif node_type == "log":
            level = config.get("level")
            if level not in ("info", "warning", "error"):
                _error(node_id, node_type, "config.level must be one of 'info', 'warning', or 'error'")
            message_text = config.get("message")
            if not _is_non_empty_string(message_text):
                _error(node_id, node_type, "config.message must be a non-empty string")

        elif node_type == "transform":
            errors.extend(
                _validate_transform_like_node(
                    node_id,
                    node_type,
                    config,
                    ("map", "filter", "expression"),
                    "config.transformType must be one of 'map', 'filter', or 'expression'",
                )
            )

        elif node_type == "filter":
            errors.extend(
                _validate_transform_like_node(
                    node_id,
                    node_type,
                    config,
                    ("filter",),
                    "config.transformType must be 'filter'",
                )
            )

        elif node_type == "llm_eval":
            prompt = config.get("prompt")
            if not _is_non_empty_string(prompt):
                _error(node_id, node_type, "config.prompt must be a non-empty string")

        elif node_type == "browser_navigate":
            errors.extend(_validate_browser_params(node_id, node_type, config, required_param_key="url"))

        elif node_type == "browser_click":
            errors.extend(_validate_browser_params(node_id, node_type, config, require_ref_or_selector=True))

        elif node_type == "browser_type":
            errors.extend(
                _validate_browser_params(
                    node_id,
                    node_type,
                    config,
                    required_param_key="text",
                    require_ref_or_selector=True,
                )
            )

        elif node_type == "browser_scroll":
            errors.extend(_validate_browser_params(node_id, node_type, config))

        elif node_type == "validate_schema":
            schema = config.get("schema")
            if not isinstance(schema, dict):
                _error(node_id, node_type, "config.schema must be a mapping (JSON schema object)")

        elif node_type == "webhook":
            url = config.get("url")
            if not _is_non_empty_string(url):
                _error(node_id, node_type, "config.url must be a non-empty string")

        elif node_type == "delay":
            delay_ms = config.get("delayMs")
            if not isinstance(delay_ms, (int, float)) or isinstance(delay_ms, bool) or delay_ms <= 0:
                _error(node_id, node_type, "config.delayMs must be a positive number (milliseconds)")

        elif node_type == "retry":
            max_retries = config.get("maxRetries")
            if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries <= 0:
                _error(node_id, node_type, "config.maxRetries must be a positive integer")

        elif node_type == "timeout":
            timeout_ms = config.get("timeoutMs")
            if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
                _error(node_id, node_type, "config.timeoutMs must be a positive integer (milliseconds)")
            wrapped_node_id = config.get("wrapped_node_id")
            if wrapped_node_id is not None and not _is_non_empty_string(wrapped_node_id):
                _error(node_id, node_type, "config.wrapped_node_id must be a non-empty string")

        elif node_type == "cache_get":
            key = config.get("key")
            if not _is_non_empty_string(key):
                _error(node_id, node_type, "config.key must be a non-empty string")

        elif node_type == "condition":
            expression = config.get("expression")
            if not _is_non_empty_string(expression):
                _error(node_id, node_type, "config.expression must be a non-empty string")

        elif node_type == "memory_write":
            collection = config.get("collection")
            if not _is_non_empty_string(collection):
                _error(node_id, node_type, "config.collection must be a non-empty string")

        elif node_type == "memory_read":
            query = config.get("query")
            if not _is_non_empty_string(query):
                _error(node_id, node_type, "config.query must be a non-empty string")

        elif node_type == "router":
            routes = config.get("routes")
            if not isinstance(routes, list) or len(routes) == 0:
                _error(node_id, node_type, "config.routes must be a non-empty list")

    return errors


def _looks_like_template(value: Any) -> bool:
    """Return True if ``value`` is a string containing Jinja-style template markers."""
    return isinstance(value, str) and "{{" in value and "}}" in value


def _get_router_route_ids(config: dict[str, Any]) -> set[str]:
    """Return the set of declared route ids for a router node config.

    Supports both the modern ``routerConfig.routes`` shape and the legacy
    top-level ``routes`` key, plus ``defaultRouteId``.
    """
    route_ids: set[str] = set()
    router_config = config.get("routerConfig") if isinstance(config.get("routerConfig"), dict) else {}
    routes = router_config.get("routes") if router_config.get("routes") is not None else config.get("routes")

    if isinstance(routes, list):
        for route in routes:
            if isinstance(route, dict):
                rid = route.get("id")
                if _is_non_empty_string(rid):
                    route_ids.add(rid)

    default_route_id = router_config.get("defaultRouteId") or config.get("defaultRouteId")
    if _is_non_empty_string(default_route_id):
        route_ids.add(default_route_id)

    return route_ids


def validate_edge_semantics(definition: dict, *, blueprint_type: str = "dag") -> list[str]:
    """Return a list of validation errors for edge conditions.

    Branching node types require specific condition values on their outgoing
    edges.  DAG strategy condition nodes must use literal ``"true"`` /
    ``"false"`` conditions; graph strategy condition edges may use template
    expressions (e.g. ``"{{ node.value }}"``).
    """
    errors: list[str] = []
    nodes = definition.get("nodes")
    edges = definition.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return errors

    node_types: dict[str, str] = {}
    node_configs: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if isinstance(node, dict):
            node_id = node.get("id")
            node_type = node.get("type")
            if isinstance(node_id, str) and isinstance(node_type, str):
                node_types[node_id] = node_type
                node_configs[node_id] = node.get("config") or {}

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source")
        target = edge.get("target")
        condition = edge.get("condition")
        source_type = node_types.get(source)
        if source_type is None:
            continue

        if source_type == "condition":
            # DAG strategy requires literal boolean strings; graph strategy
            # supports template expressions like "{{node.value}}" and also
            # allows unconditioned edges (always taken).
            if blueprint_type == "dag" and condition not in ("true", "false"):
                errors.append(
                    f"Edge from condition node '{source}' to '{target}' must have condition 'true' or 'false'"
                )
        elif source_type == "timeout":
            if condition not in (None, "default", "on_timeout"):
                errors.append(
                    f"Edge from timeout node '{source}' to '{target}' "
                    "must have condition 'on_timeout', 'default', or no condition"
                )
        elif source_type == "validate_schema":
            if condition not in ("default", "on_invalid"):
                errors.append(
                    f"Edge from validate_schema node '{source}' to '{target}' "
                    "must have condition 'default' or 'on_invalid'"
                )
        elif source_type == "router":
            if not _is_non_empty_string(condition):
                errors.append(
                    f"Edge from router node '{source}' to '{target}' must have a non-empty condition (route id)"
                )
            elif not _looks_like_template(condition):
                valid_route_ids = _get_router_route_ids(node_configs.get(source) or {})
                if valid_route_ids and condition not in valid_route_ids:
                    errors.append(
                        f"Edge from router node '{source}' to '{target}' has condition '{condition}' "
                        "which does not match any declared route id"
                    )

    # Timeout-specific structural checks.
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        if not isinstance(node_id, str):
            continue
        outgoing = [e for e in edges if isinstance(e, dict) and e.get("source") == node_id]

        if node_type == "timeout":
            raw_config = node.get("config")
            config = raw_config if isinstance(raw_config, dict) else {}
            has_wrapped = _is_non_empty_string(config.get("wrapped_node_id"))
            has_default = any(e.get("condition") in (None, "default") for e in outgoing if isinstance(e, dict))
            has_on_timeout = any(e.get("condition") == "on_timeout" for e in outgoing if isinstance(e, dict))

            if not has_wrapped and not has_default:
                errors.append(
                    f"Timeout node '{node_id}' must specify config.wrapped_node_id or have a default outgoing edge"
                )
            if not has_on_timeout:
                errors.append(f"Timeout node '{node_id}' should have an outgoing 'on_timeout' edge")

        if node_type == "validate_schema":
            default_edges = [e for e in outgoing if e.get("condition") == "default"]
            on_invalid_edges = [e for e in outgoing if e.get("condition") == "on_invalid"]

            if outgoing and not default_edges and not on_invalid_edges:
                errors.append(
                    f"Validate schema node '{node_id}' has outgoing edges but none use 'default' or 'on_invalid'"
                )

            if (
                default_edges
                and on_invalid_edges
                and default_edges[0].get("target") == on_invalid_edges[0].get("target")
            ):
                errors.append(
                    f"Validate schema node '{node_id}' must route 'default' and 'on_invalid' to different targets"
                )

        # DAG condition nodes must branch to exactly one true and one false target.
        if blueprint_type == "dag" and node_type == "condition":
            true_edges = [e for e in outgoing if e.get("condition") == "true"]
            false_edges = [e for e in outgoing if e.get("condition") == "false"]
            if len(true_edges) != 1:
                errors.append(
                    f"Condition node '{node_id}' must have exactly one outgoing 'true' edge (found {len(true_edges)})"
                )
            if len(false_edges) != 1:
                errors.append(
                    f"Condition node '{node_id}' must have exactly one outgoing 'false' edge (found {len(false_edges)})"
                )
            if (
                len(true_edges) == 1
                and len(false_edges) == 1
                and true_edges[0].get("target") == false_edges[0].get("target")
            ):
                errors.append(f"Condition node '{node_id}' must route 'true' and 'false' to different targets")

    return errors


def validate_blueprint(path: Path, data: dict, *, verbose: bool = False) -> list[str]:
    """Return a list of validation errors for a parsed blueprint.

    Steps:
        1. Presence of required top-level keys.
        2. Per-node config constraint validation.
        3. Per-node config value validation.
        4. Edge condition semantics validation.
        5. ``validate_blueprint_definition`` edge/node graph checks.
        6. ``blueprint_to_workflow`` adapter conversion (catches malformed
           nodes, edges, budgets, etc.).
    """
    errors: list[str] = []

    # 1. Required top-level keys.
    errors.extend(f"Missing required top-level key: {key}" for key in REQUIRED_TOP_KEYS if key not in data)

    definition = data.get("definition")
    if not isinstance(definition, dict):
        # blueprint_to_workflow/validate_blueprint_definition expect a dict.
        errors.append("definition must be a mapping")
        return errors

    # 2. Per-node config constraint validation.
    errors.extend(validate_node_constraints(definition))

    # 3. Per-node config value validation.
    errors.extend(validate_node_config_values(definition))

    # 4. Edge condition semantics validation.
    errors.extend(validate_edge_semantics(definition, blueprint_type=data.get("blueprint_type", "dag")))

    # 5. Edge/node graph validation.
    try:
        graph_errors = validate_blueprint_definition(definition)
    except Exception as exc:
        if verbose:
            traceback.print_exc()
        graph_errors = [f"validate_blueprint_definition raised {type(exc).__name__}: {exc}"]
    if graph_errors:
        errors.extend(graph_errors)

    # 5. Adapter conversion (catches malformed nodes/edges/budgets).
    try:
        blueprint_to_workflow(definition, blueprint_id=str(path))
    except InvalidBlueprintGraphError as exc:
        errors.append(f"Invalid blueprint graph: {exc}")
    except Exception as exc:
        if verbose:
            traceback.print_exc()
        errors.append(f"blueprint_to_workflow raised {type(exc).__name__}: {exc}")

    return errors


def _ensure_config(node: MutableMapping[str, Any]) -> MutableMapping[str, Any] | None:
    """Return the node's config dict, initializing an missing/None one."""
    if "config" not in node or node.get("config") is None:
        node["config"] = {}
    config = node["config"]
    if not isinstance(config, MutableMapping):
        return None
    return config


def apply_fixes(data: MutableMapping[str, Any]) -> list[str]:
    """Apply safe auto-corrections to a parsed blueprint.

    Mutates ``data`` in place and returns a list of human-readable change
    descriptions.  Fixes are idempotent: running this twice on the same
    blueprint should produce no new changes on the second run.

    Currently implemented fixes:

    * Rename deprecated keys: ``duration`` → ``delayMs``,
      ``max_retries`` → ``maxRetries``.
    * Add sensible defaults for missing optional keys:
      ``log.level``, ``log.message``, ``merge.mergeStrategy``, ``split.mode``,
      ``webhook.method``, ``memory_read.collection``,
      ``validate_schema.payload_key``, ``file_operation.operation``.
    * Trim leading/trailing whitespace from structural string values.
    * Ensure ``definition.nodes`` and ``definition.edges`` exist.
    """
    changes: list[str] = []
    definition = data.get("definition")
    if not isinstance(definition, MutableMapping):
        return changes

    if "nodes" not in definition:
        definition["nodes"] = []
        changes.append("Added missing definition.nodes")
    if "edges" not in definition:
        definition["edges"] = []
        changes.append("Added missing definition.edges")

    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return changes

    for node in nodes:
        if not isinstance(node, MutableMapping):
            continue

        node_id = node.get("id", "<unknown>")
        node_type = node.get("type")
        config = _ensure_config(node)
        if config is None:
            continue

        # ---- Rename deprecated keys ------------------------------------
        # `duration` was originally specified in seconds; the executor now
        # expects `delayMs` in milliseconds. Convert on the way through.
        if "duration" in config:
            if "delayMs" not in config:
                removed = config.pop("duration")
                try:
                    converted = int(float(removed) * 1000)
                except (TypeError, ValueError):
                    converted = 0
                if converted > 0:
                    config["delayMs"] = converted
                    changes.append(
                        f"Node '{node_id}': renamed config.duration -> config.delayMs "
                        f"(converted {removed!r} seconds -> {converted} ms)"
                    )
                else:
                    changes.append(
                        f"Node '{node_id}': removed config.duration "
                        f"(could not convert value {removed!r} to milliseconds)"
                    )
            else:
                removed = config.pop("duration")
                changes.append(
                    f"Node '{node_id}': removed deprecated config.duration "
                    f"(delayMs already present; had value {removed!r})"
                )

        if "max_retries" in config:
            if "maxRetries" not in config:
                config["maxRetries"] = config.pop("max_retries")
                changes.append(f"Node '{node_id}': renamed config.max_retries -> config.maxRetries")
            else:
                removed = config.pop("max_retries")
                changes.append(
                    f"Node '{node_id}': removed deprecated config.max_retries "
                    f"(maxRetries already present; had value {removed!r})"
                )

        # ---- Trim structural strings -----------------------------------
        for key in ("splitOn", "varName", "expression", "collection", "query", "url", "key"):
            if key in config and isinstance(config[key], str):
                original = config[key]
                trimmed = original.strip()
                if trimmed != original:
                    config[key] = trimmed
                    changes.append(f"Node '{node_id}': trimmed whitespace from config.{key}")

        # ---- Add sensible defaults -------------------------------------
        if node_type == "log":
            if "level" not in config:
                config["level"] = "info"
                changes.append(f"Node '{node_id}': set default config.level='info'")
            if "message" not in config:
                fallback = node.get("title") or node.get("description") or str(node_id)
                config["message"] = fallback
                changes.append(f"Node '{node_id}': set default config.message from node title/description/id")

        if node_type == "merge" and "mergeStrategy" not in config:
            config["mergeStrategy"] = "concat"
            changes.append(f"Node '{node_id}': set default config.mergeStrategy='concat'")

        if node_type == "split" and "mode" not in config:
            config["mode"] = "item"
            changes.append(f"Node '{node_id}': set default config.mode='item'")

        if node_type == "webhook" and "method" not in config:
            config["method"] = "POST"
            changes.append(f"Node '{node_id}': set default config.method='POST'")

        if node_type == "memory_read" and "collection" not in config:
            config["collection"] = "flowmanner_memory"
            changes.append(f"Node '{node_id}': set default config.collection='flowmanner_memory'")

        if node_type == "validate_schema" and "payload_key" not in config:
            config["payload_key"] = "payload"
            changes.append(f"Node '{node_id}': set default config.payload_key='payload'")

        if node_type == "file_operation" and "operation" not in config:
            config["operation"] = "read"
            changes.append(f"Node '{node_id}': set default config.operation='read'")

    return changes


def _load_yaml_ruamel(path: Path) -> tuple[Any, YAML]:
    """Load a YAML file with ruamel.yaml, returning the tree and parser."""
    ruamel_parser = YAML(typ="rt")
    ruamel_parser.preserve_quotes = True  # type: ignore[attr-defined]
    ruamel_parser.indent(mapping=2, sequence=4, offset=2)  # type: ignore[attr-defined]
    with path.open("r", encoding="utf-8") as fh:
        tree = ruamel_parser.load(fh)
    return tree, ruamel_parser


def _to_plain_dict(tree: Any) -> Any:
    """Convert a ruamel.yaml tree to a plain Python dict/list/primitive tree."""
    return json.loads(json.dumps(tree, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint/validate Flowmanner blueprint YAML files.")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Directories or files to lint (default: backend/ and blueprints/)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print full tracebacks for unexpected validation errors",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix common blueprint issues in place",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --fix, show changes without writing files",
    )
    args = parser.parse_args(argv)

    if args.dry_run and not args.fix:
        parser.error("--dry-run only makes sense with --fix")

    if args.paths:
        search_paths = args.paths
    else:
        # Resolve default directories relative to the repo root.
        repo_root = BACKEND_DIR.parent
        search_paths = [repo_root / d for d in DEFAULT_DIRS]

    yaml_files = discover_yaml_files(search_paths)

    print(f"Scanning {len(yaml_files)} YAML file(s) for blueprints...\n")

    repo_root = BACKEND_DIR.parent
    failures: list[tuple[Path, list[str]]] = []
    validated = 0

    for path in yaml_files:
        try:
            rel_path = path.relative_to(repo_root)
        except ValueError:
            rel_path = path
        raw_text = path.read_text(encoding="utf-8")

        # Parse once; YAML errors are reported as validation failures.
        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            failures.append((path, [f"Invalid YAML: {exc}"]))
            print(f"❌ {rel_path}")
            print(f"   - Invalid YAML: {exc}")
            continue

        # Skip files that are not blueprints (e.g. docker-compose, CI configs).
        if not looks_like_blueprint(data):
            continue

        validated += 1
        errors = validate_blueprint(path, data, verbose=args.verbose)
        if errors and not args.fix:
            print(f" {rel_path}")
            for err in errors:
                print(f"   - {err}")
            failures.append((path, errors))
            continue

        if not args.fix:
            print(f"✅ {rel_path}")
            continue

        # --fix mode --------------------------------------------------------
        try:
            tree, ruamel_parser = _load_yaml_ruamel(path)
        except yaml.YAMLError as exc:
            failures.append((path, [f"Invalid YAML: {exc}"]))
            print(f"❌ {rel_path}")
            print(f"   - Invalid YAML: {exc}")
            continue

        if not isinstance(tree, MutableMapping):
            print(f"❌ {rel_path}")
            print("   - Cannot fix: top-level YAML is not a mapping")
            failures.append((path, ["Top-level YAML is not a mapping"]))
            continue

        changes = apply_fixes(tree)
        fixed_plain = _to_plain_dict(tree)
        post_fix_errors = validate_blueprint(path, fixed_plain, verbose=args.verbose)

        if post_fix_errors:
            print(f"❌ {rel_path}")
            for err in post_fix_errors:
                print(f"   - {err}")
            failures.append((path, post_fix_errors))
            continue

        if not changes:
            print(f"✅ {rel_path}")
            continue

        if args.dry_run:
            print(f"🔧 {rel_path} (dry-run)")
            for change in changes:
                print(f"   - {change}")
            # Render a diff between original and fixed YAML.
            new_text_io = io.StringIO()
            ruamel_parser.dump(tree, new_text_io)
            new_text = new_text_io.getvalue()
            diff = list(
                difflib.unified_diff(
                    raw_text.splitlines(keepends=True),
                    new_text.splitlines(keepends=True),
                    fromfile=str(rel_path),
                    tofile=str(rel_path),
                )
            )
            if diff:
                print("".join(diff))
            continue

        # Apply the fix in place.
        new_text_io = io.StringIO()
        ruamel_parser.dump(tree, new_text_io)
        path.write_text(new_text_io.getvalue(), encoding="utf-8")
        print(f" {rel_path}")
        for change in changes:
            print(f"   - {change}")

    print()
    if failures:
        total_errors = sum(len(errs) for _, errs in failures)
        print(f"Failures: {len(failures)} file(s), {total_errors} error(s).")
        return 1

    print(f"All {validated} blueprint(s) passed validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
