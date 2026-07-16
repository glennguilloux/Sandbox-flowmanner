"""Unit tests for validate_blueprint_definition.

Covers the edge-endpoint validation gate that keeps a structurally broken
blueprint (dangling edge) from ever being saved / published.
"""

from __future__ import annotations

from app.services.substrate.adapters import validate_blueprint_definition


def test_valid_snapshot_returns_empty() -> None:
    snapshot = {
        "nodes": [
            {"id": "a", "type": "llm_call"},
            {"id": "b", "type": "llm_call"},
        ],
        "edges": [{"source": "a", "target": "b"}],
    }
    assert validate_blueprint_definition(snapshot) == []


def test_dangling_target_names_ghost() -> None:
    snapshot = {
        "nodes": [{"id": "a", "type": "llm_call"}],
        "edges": [{"source": "a", "target": "ghost"}],
    }
    errors = validate_blueprint_definition(snapshot, blueprint_id="bp-1")
    assert len(errors) == 1
    assert "ghost" in errors[0]
    assert "bp-1" in errors[0]


def test_dangling_source_names_ghost() -> None:
    snapshot = {
        "nodes": [{"id": "b", "type": "llm_call"}],
        "edges": [{"source": "ghost", "target": "b"}],
    }
    errors = validate_blueprint_definition(snapshot, blueprint_id="bp-2")
    assert len(errors) == 1
    assert "ghost" in errors[0]
    assert "bp-2" in errors[0]


def test_sentinel_edges_are_ignored() -> None:
    snapshot = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "a", "type": "llm_call"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "a"},
            {"source": "a", "target": "end"},
        ],
    }
    assert validate_blueprint_definition(snapshot) == []


def test_empty_definition_is_valid() -> None:
    assert validate_blueprint_definition({}) == []
    assert validate_blueprint_definition({"nodes": [], "edges": []}) == []


def test_edge_missing_source_and_target_reports_error() -> None:
    snapshot = {
        "nodes": [{"id": "a", "type": "llm_call"}],
        "edges": [{"source": None, "target": None}],
    }
    errors = validate_blueprint_definition(snapshot)
    assert len(errors) == 1
    assert "missing source/target" in errors[0]
