"""Phase 4 tests: validate the three browser blueprints load through the adapter.

Each blueprint YAML file is loaded as a snapshot dict and fed through
``blueprint_to_workflow()``. The tests assert:
- The workflow type is GRAPH (required for {{node.field}} interpolation).
- No nodes are silently dropped (all nodes survive the adapter).
- No edges are silently dropped.
- Edge endpoints reference real nodes (no orphan edges).
- Node types are correctly mapped to NodeType enum values.
- Conditional edges have the expected condition expressions.
- Budget is correctly parsed.

These are structural validation tests — they do NOT execute the blueprints
(which would require a running browser + Qdrant + LLM gateway). They verify
the blueprint definitions are well-formed and will survive adapter conversion
without errors.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Lazy import so the test file can be collected without the full backend
# environment loaded (the YAML loading is pure stdlib).
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from app.services.substrate.adapters import blueprint_to_workflow
from app.services.substrate.workflow_models import NodeType, WorkflowType


# ── Helpers ──────────────────────────────────────────────────────────

_BLUEPRINTS_DIR = Path(__file__).resolve().parents[2] / "blueprints"


def _load_blueprint_yaml(filename: str) -> dict:
    """Load a blueprint YAML file and return its ``definition`` section as a
    snapshot dict suitable for ``blueprint_to_workflow``.
    """
    if yaml is None:
        pytest.skip("PyYAML not installed")
    yaml_path = _BLUEPRINTS_DIR / filename
    if not yaml_path.exists():
        pytest.skip(f"Blueprint file not found: {yaml_path}")
    with open(yaml_path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    # The YAML file has top-level metadata (name, description, inputs) and
    # a ``definition`` key that holds the actual blueprint snapshot. We
    # extract the definition and add the title/description from the
    # top-level so the adapter can read them.
    snapshot = doc.get("definition", {})
    snapshot["title"] = doc.get("name", "")
    snapshot["description"] = doc.get("description", "")
    return snapshot


def _node_ids(workflow) -> set[str]:
    return {n.id for n in workflow.nodes}


def _edge_pairs(workflow) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in workflow.edges}


# ── Blueprint #20: Scrape → diff → alert ──────────────────────────────


class TestScrapeDiffAlertBlueprint:
    """Validate the scrape-diff-alert blueprint (#20)."""

    @pytest.fixture
    def wf(self):
        snapshot = _load_blueprint_yaml("scrape-diff-alert.yaml")
        return blueprint_to_workflow(snapshot, blueprint_id="bp-scrape-diff", user_id="test")

    def test_workflow_type_is_graph(self, wf):
        assert wf.type == WorkflowType.GRAPH

    def test_all_nodes_survive_adapter(self, wf):
        expected = {"snap", "read_prior", "set_current_fp", "set_prior_fp", "diff", "notify", "persist"}
        assert _node_ids(wf) == expected

    def test_all_edges_survive_adapter(self, wf):
        # 6 edges (including the conditional edge from diff → notify)
        assert len(wf.edges) == 6

    def test_no_orphan_edges(self, wf):
        ids = _node_ids(wf)
        for edge in wf.edges:
            assert edge.source in ids, f"Edge source {edge.source} not in nodes"
            assert edge.target in ids, f"Edge target {edge.target} not in nodes"

    def test_conditional_edge_has_condition(self, wf):
        """The diff → notify edge must carry the condition '{{diff.value}}'."""
        conditional = [e for e in wf.edges if e.condition]
        assert len(conditional) == 1
        assert conditional[0].source == "diff"
        assert conditional[0].target == "notify"
        assert "diff.value" in conditional[0].condition

    def test_node_types_correct(self, wf):
        nm = {n.id: n.type for n in wf.nodes}
        assert nm["snap"] == NodeType.BROWSER_SNAPSHOT
        assert nm["read_prior"] == NodeType.MEMORY_READ
        assert nm["set_current_fp"] == NodeType.VARIABLE_SET
        assert nm["set_prior_fp"] == NodeType.VARIABLE_SET
        assert nm["diff"] == NodeType.CONDITION
        assert nm["notify"] == NodeType.WEBHOOK
        assert nm["persist"] == NodeType.MEMORY_WRITE

    def test_memory_write_config(self, wf):
        persist = next(n for n in wf.nodes if n.id == "persist")
        assert persist.config.get("collection") == "flowmanner_memory"
        assert "text" in persist.config
        assert "payload" in persist.config

    def test_memory_read_config(self, wf):
        reader = next(n for n in wf.nodes if n.id == "read_prior")
        assert reader.config.get("collection") == "flowmanner_memory"
        assert reader.config.get("topK") == 1

    def test_condition_expression_present(self, wf):
        diff = next(n for n in wf.nodes if n.id == "diff")
        expr = diff.config.get("expression")
        assert expr is not None
        assert "previous_outputs" in expr

    def test_budget_parsed(self, wf):
        assert float(wf.budget.max_cost_usd) == 0.50
        assert wf.budget.max_wall_time_seconds == 120


# ── Blueprint #18: Web-recon ──────────────────────────────────────────


class TestWebReconBlueprint:
    """Validate the web-recon blueprint (#18)."""

    @pytest.fixture
    def wf(self):
        snapshot = _load_blueprint_yaml("web-recon.yaml")
        return blueprint_to_workflow(snapshot, blueprint_id="bp-web-recon", user_id="test")

    def test_workflow_type_is_graph(self, wf):
        assert wf.type == WorkflowType.GRAPH

    def test_all_nodes_survive_adapter(self, wf):
        expected = {
            "nav", "snap", "shot",
            "set_url", "set_title", "set_fp",
            "summarize", "store",
        }
        assert _node_ids(wf) == expected

    def test_all_edges_survive_adapter(self, wf):
        # 9 edges connecting the chain
        assert len(wf.edges) == 9

    def test_no_orphan_edges(self, wf):
        ids = _node_ids(wf)
        for edge in wf.edges:
            assert edge.source in ids, f"Edge source {edge.source} not in nodes"
            assert edge.target in ids, f"Edge target {edge.target} not in nodes"

    def test_node_types_correct(self, wf):
        nm = {n.id: n.type for n in wf.nodes}
        assert nm["nav"] == NodeType.BROWSER_NAVIGATE
        assert nm["snap"] == NodeType.BROWSER_SNAPSHOT
        assert nm["shot"] == NodeType.BROWSER_SCREENSHOT
        assert nm["set_url"] == NodeType.VARIABLE_SET
        assert nm["set_title"] == NodeType.VARIABLE_SET
        assert nm["set_fp"] == NodeType.VARIABLE_SET
        assert nm["summarize"] == NodeType.LLM_CALL
        assert nm["store"] == NodeType.MEMORY_WRITE

    def test_llm_node_has_prompt(self, wf):
        llm = next(n for n in wf.nodes if n.id == "summarize")
        assert "prompt" in llm.config
        assert "{{ inputs.page_url }}" in llm.config["prompt"]

    def test_navigate_has_url_param(self, wf):
        nav = next(n for n in wf.nodes if n.id == "nav")
        params = nav.config.get("params", {})
        assert "url" in params

    def test_budget_parsed(self, wf):
        assert float(wf.budget.max_cost_usd) == 1.00
        assert wf.budget.max_wall_time_seconds == 180


# ── Blueprint #19: Auth-flow tester ───────────────────────────────────


class TestAuthFlowTesterBlueprint:
    """Validate the auth-flow-tester blueprint (#19)."""

    @pytest.fixture
    def wf(self):
        snapshot = _load_blueprint_yaml("auth-flow-tester.yaml")
        return blueprint_to_workflow(snapshot, blueprint_id="bp-auth-test", user_id="test")

    def test_workflow_type_is_graph(self, wf):
        assert wf.type == WorkflowType.GRAPH

    def test_all_nodes_survive_adapter(self, wf):
        expected = {
            "nav", "snap_login", "type_user", "type_pass",
            "click_submit", "snap_post", "shot",
            "set_post_url", "set_login_url",
            "check_auth", "alert_fail", "close",
        }
        assert _node_ids(wf) == expected

    def test_all_edges_survive_adapter(self, wf):
        # 12 edges (11 unconditional + 1 conditional from check_auth → alert_fail)
        assert len(wf.edges) == 12

    def test_no_orphan_edges(self, wf):
        ids = _node_ids(wf)
        for edge in wf.edges:
            assert edge.source in ids, f"Edge source {edge.source} not in nodes"
            assert edge.target in ids, f"Edge target {edge.target} not in nodes"

    def test_node_types_correct(self, wf):
        nm = {n.id: n.type for n in wf.nodes}
        assert nm["nav"] == NodeType.BROWSER_NAVIGATE
        assert nm["snap_login"] == NodeType.BROWSER_SNAPSHOT
        assert nm["type_user"] == NodeType.BROWSER_TYPE
        assert nm["type_pass"] == NodeType.BROWSER_TYPE
        assert nm["click_submit"] == NodeType.BROWSER_CLICK
        assert nm["snap_post"] == NodeType.BROWSER_SNAPSHOT
        assert nm["shot"] == NodeType.BROWSER_SCREENSHOT
        assert nm["set_post_url"] == NodeType.VARIABLE_SET
        assert nm["set_login_url"] == NodeType.VARIABLE_SET
        assert nm["check_auth"] == NodeType.CONDITION
        assert nm["alert_fail"] == NodeType.WEBHOOK
        assert nm["close"] == NodeType.BROWSER_CLOSE

    def test_type_nodes_have_selector_param(self, wf):
        """browser_type nodes must use the `selector` param (Phase 1 feature)."""
        for nid in ("type_user", "type_pass"):
            node = next(n for n in wf.nodes if n.id == nid)
            params = node.config.get("params", {})
            assert "selector" in params, f"{nid} missing selector param"
            assert "text" in params, f"{nid} missing text param"

    def test_click_node_has_selector_param(self, wf):
        node = next(n for n in wf.nodes if n.id == "click_submit")
        params = node.config.get("params", {})
        assert "selector" in params

    def test_conditional_edge_negates_condition(self, wf):
        """The check_auth → alert_fail edge fires when auth FAILED (not succeeded)."""
        conditional = [e for e in wf.edges if e.condition]
        assert len(conditional) == 1
        assert conditional[0].source == "check_auth"
        assert conditional[0].target == "alert_fail"
        assert "not" in conditional[0].condition.lower()
        assert "check_auth.value" in conditional[0].condition

    def test_condition_expression_present(self, wf):
        node = next(n for n in wf.nodes if n.id == "check_auth")
        expr = node.config.get("expression")
        assert expr is not None
        assert "previous_outputs" in expr
        assert "set_post_url" in expr
        assert "set_login_url" in expr

    def test_budget_parsed(self, wf):
        assert float(wf.budget.max_cost_usd) == 0.50
        assert wf.budget.max_wall_time_seconds == 120
