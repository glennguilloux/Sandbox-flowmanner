"""Unit tests for backend/scripts/lint_blueprints.py.

Covers YAML discovery, directory exclusion, and the validation path
without requiring a live database or the full FastAPI app.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
import yaml


def _import_generator_module() -> ModuleType:
    """Import generate_node_type_table.py by file location."""
    generator_path = Path(__file__).resolve().parent.parent / "scripts" / "generate_node_type_table.py"
    spec = importlib.util.spec_from_file_location("generate_node_type_table", generator_path)
    if spec is None or spec.loader is None:  # type: ignore[union-attr]
        raise ImportError(f"Could not load {generator_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_node_type_table"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


if TYPE_CHECKING:
    from types import ModuleType

# The script lives under backend/scripts/; import it as a module by name.
SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "lint_blueprints.py"


def _import_lint_module() -> ModuleType:
    """Import lint_blueprints.py with the backend/ dir on sys.path."""
    backend_dir = str(Path(__file__).resolve().parent.parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    import importlib

    # Import via spec so the file can be re-loaded even if a previous import
    # attempt happened during collection.
    spec = importlib.util.spec_from_file_location("lint_blueprints", SCRIPT_PATH)
    if spec is None or spec.loader is None:  # type: ignore[union-attr]
        raise ImportError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_blueprints"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="module")
def lint() -> ModuleType:
    """Provide the lint_blueprints module under test."""
    return _import_lint_module()


class TestDiscoverYamlFiles:
    """Discovery behaviour: files, directories, missing paths, exclusions."""

    def test_finds_yaml_and_yml_files(self, lint: ModuleType, tmp_path: Path) -> None:
        base = tmp_path / "repo"
        base.mkdir()
        files = [
            base / "a.yaml",
            base / "b.yml",
            base / "c.txt",
            base / "nested" / "d.yaml",
        ]
        for f in files:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("name: test")
        discovered = lint.discover_yaml_files([base])
        expected = sorted([f.resolve() for f in files if f.suffix in (".yaml", ".yml")])
        assert discovered == expected

    def test_accepts_individual_files(self, lint: ModuleType, tmp_path: Path) -> None:
        file_ok = tmp_path / "blueprint.yaml"
        file_ok.write_text("name: test")
        discovered = lint.discover_yaml_files([file_ok])
        assert discovered == [file_ok.resolve()]

    def test_ignores_missing_paths(self, lint: ModuleType, tmp_path: Path) -> None:
        missing = tmp_path / "missing"
        existing = tmp_path / "exists.yaml"
        existing.write_text("name: test")
        with patch("builtins.print"):
            discovered = lint.discover_yaml_files([missing, existing])
        assert discovered == [existing.resolve()]

    def test_skips_excluded_directories(self, lint: ModuleType, tmp_path: Path) -> None:
        # Create YAML files inside an excluded dir and a sibling allowed dir.
        excluded = tmp_path / "docs"
        excluded.mkdir()
        (excluded / "ignored.yaml").write_text("name: ignored")

        allowed = tmp_path / "blueprints"
        allowed.mkdir()
        (allowed / "kept.yaml").write_text("name: kept")

        discovered = lint.discover_yaml_files([tmp_path])
        assert discovered == [(allowed / "kept.yaml").resolve()]

    def test_exclusion_is_exact_match(self, lint: ModuleType, tmp_path: Path) -> None:
        # A directory named "docs2" should NOT be excluded.
        not_docs = tmp_path / "docs2"
        not_docs.mkdir()
        (not_docs / "kept.yaml").write_text("name: kept")

        discovered = lint.discover_yaml_files([tmp_path])
        assert discovered == [(not_docs / "kept.yaml").resolve()]


class TestIsExcluded:
    """Direct checks for the _is_excluded helper."""

    def test_excluded_dirs_are_skipped(self, lint: ModuleType) -> None:
        for name in lint.DEFAULT_EXCLUDED_DIRS:
            path = Path(f"/repo/{name}/file.yaml")
            assert lint._is_excluded(path) is True

    def test_non_excluded_dirs_are_allowed(self, lint: ModuleType) -> None:
        path = Path("/repo/blueprints/audit.yaml")
        assert lint._is_excluded(path) is False


class TestLooksLikeBlueprint:
    """Identification of blueprint-shaped YAML payloads."""

    def test_true_when_keys_present(self, lint: ModuleType) -> None:
        assert (
            lint.looks_like_blueprint(
                {
                    "version": 1,
                    "name": "audit",
                    "blueprint_type": "dag",
                    "definition": {"nodes": []},
                }
            )
            is True
        )

    @pytest.mark.parametrize("missing", ["blueprint_type", "definition"])
    def test_false_when_key_missing(self, lint: ModuleType, missing: str) -> None:
        data = {"blueprint_type": "dag", "definition": {"nodes": []}}
        del data[missing]
        assert lint.looks_like_blueprint(data) is False

    def test_false_when_not_dict(self, lint: ModuleType) -> None:
        assert lint.looks_like_blueprint(["not", "a", "dict"]) is False


class TestValidateNodeConstraints:
    """Per-node required config keys."""

    def test_split_node_requires_splitOn(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "split_repos", "type": "split", "config": {"mode": "item"}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("split_repos" in e and "splitOn" in e for e in errors)

    def test_merge_node_requires_mergeStrategy(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "merge_results", "type": "merge", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("merge_results" in e and "mergeStrategy" in e for e in errors)

    def test_sandbox_node_requires_task_prompt(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "audit_repo", "type": "sandbox", "config": {"template": "python-img"}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("audit_repo" in e and "task_prompt" in e for e in errors)

    def test_valid_nodes_pass(self, lint: ModuleType) -> None:
        definition = {
            "nodes": [
                {"id": "split_repos", "type": "split", "config": {"splitOn": "inputs.repos"}},
                {"id": "merge_results", "type": "merge", "config": {"mergeStrategy": "concat"}},
                {
                    "id": "audit_repo",
                    "type": "sandbox",
                    "config": {"task_prompt": "echo done"},
                },
            ]
        }
        assert lint.validate_node_constraints(definition) == []

    def test_unknown_node_types_are_ignored(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "x", "type": "future_node", "config": {}}]}
        assert lint.validate_node_constraints(definition) == []

    def test_non_list_nodes_is_noop(self, lint: ModuleType) -> None:
        assert lint.validate_node_constraints({"nodes": None}) == []

    def test_missing_config_treated_as_empty(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "split", "type": "split"}]}
        errors = lint.validate_node_constraints(definition)
        assert any("splitOn" in e for e in errors)

    def test_llm_call_requires_prompt(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "rank", "type": "llm_call", "config": {"temperature": 0.3}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("rank" in e and "prompt" in e for e in errors)

    def test_llm_call_with_prompt_passes(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "rank", "type": "llm_call", "config": {"prompt": "rank repos"}}]}
        assert lint.validate_node_constraints(definition) == []

    def test_variable_set_requires_varName(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "set_merged", "type": "variable_set", "config": {"varExpr": "1+1"}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("set_merged" in e and "varName" in e for e in errors)

    def test_variable_set_requires_varValue_or_varExpr(self, lint: ModuleType) -> None:
        definition = {
            "nodes": [
                {
                    "id": "set_merged",
                    "type": "variable_set",
                    "config": {"varName": "merged_results"},
                }
            ]
        }
        errors = lint.validate_node_constraints(definition)
        assert any("set_merged" in e and "varValue" in e and "varExpr" in e for e in errors)

    def test_variable_set_with_varValue_passes(self, lint: ModuleType) -> None:
        definition = {
            "nodes": [
                {
                    "id": "set_merged",
                    "type": "variable_set",
                    "config": {"varName": "merged_results", "varValue": "x"},
                }
            ]
        }
        assert lint.validate_node_constraints(definition) == []

    def test_variable_set_with_varExpr_passes(self, lint: ModuleType) -> None:
        definition = {
            "nodes": [
                {
                    "id": "set_merged",
                    "type": "variable_set",
                    "config": {"varName": "merged_results", "varExpr": "previous_outputs['x']"},
                }
            ]
        }
        assert lint.validate_node_constraints(definition) == []

    # ---- New node types added to REQUIRED_NODE_CONFIG ----------------------

    def test_transform_requires_transformType_and_transformExpression(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "t", "type": "transform", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("transformType" in e for e in errors)
        assert any("transformExpression" in e for e in errors)

    def test_condition_requires_expression(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "c", "type": "condition", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("expression" in e for e in errors)

    def test_validate_schema_requires_schema(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "vs", "type": "validate_schema", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("schema" in e for e in errors)

    def test_memory_write_requires_collection(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "mw", "type": "memory_write", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("collection" in e for e in errors)

    def test_memory_read_requires_query(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "mr", "type": "memory_read", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("query" in e for e in errors)

    def test_webhook_requires_url(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "wh", "type": "webhook", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("url" in e for e in errors)

    def test_log_requires_level_and_message(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "log", "type": "log", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("level" in e for e in errors)
        assert any("message" in e for e in errors)

    def test_router_requires_routes(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "r", "type": "router", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("routes" in e for e in errors)

    def test_delay_requires_delay_ms(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "d", "type": "delay", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("delayMs" in e for e in errors)

    def test_retry_requires_max_retries(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "r", "type": "retry", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("maxRetries" in e for e in errors)

    def test_cache_get_requires_key(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "cg", "type": "cache_get", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("key" in e for e in errors)

    def test_filter_requires_transformType_and_transformExpression(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "f", "type": "filter", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("transformType" in e for e in errors)
        assert any("transformExpression" in e for e in errors)

    def test_llm_eval_requires_prompt(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "ev", "type": "llm_eval", "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("prompt" in e for e in errors)

    @pytest.mark.parametrize("node_type", ["browser_navigate", "browser_click", "browser_type", "browser_scroll"])
    def test_browser_nodes_require_params(self, lint: ModuleType, node_type: str) -> None:
        definition = {"nodes": [{"id": "b", "type": node_type, "config": {}}]}
        errors = lint.validate_node_constraints(definition)
        assert any("params" in e for e in errors)


class TestValidateNodeConfigValues:
    """Stricter validation of config *values* beyond simple key presence."""

    def _node(self, node_type: str, config: dict) -> dict:
        return {"nodes": [{"id": "n1", "type": node_type, "config": config}]}

    @pytest.mark.parametrize("value", ["", "   ", "\t\n", None])
    def test_split_requires_non_empty_splitOn(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("split", {"splitOn": value})
        errors = lint.validate_node_config_values(definition)
        assert any("splitOn" in e and "non-empty" in e for e in errors)

    def test_split_valid_splitOn_passes(self, lint: ModuleType) -> None:
        definition = self._node("split", {"splitOn": "inputs.repos"})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_variable_set_requires_non_empty_varName(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("variable_set", {"varName": value})
        errors = lint.validate_node_config_values(definition)
        assert any("varName" in e and "non-empty" in e for e in errors)

    def test_variable_set_valid_varName_passes(self, lint: ModuleType) -> None:
        definition = self._node("variable_set", {"varName": "merged_results"})
        assert lint.validate_node_config_values(definition) == []

    def test_unknown_node_types_are_ignored_for_values(self, lint: ModuleType) -> None:
        definition = self._node("future_node", {"value": ""})
        assert lint.validate_node_config_values(definition) == []

    def test_missing_config_treated_as_empty_for_values(self, lint: ModuleType) -> None:
        definition = {"nodes": [{"id": "split", "type": "split"}]}
        errors = lint.validate_node_config_values(definition)
        assert any("splitOn" in e and "non-empty" in e for e in errors)

    @pytest.mark.parametrize("value", ["", "   ", "bad"])
    def test_transform_requires_valid_transformType(self, lint: ModuleType, value: str) -> None:
        definition = self._node("transform", {"transformType": value})
        errors = lint.validate_node_config_values(definition)
        assert any("transformType" in e and "'map', 'filter', or 'expression'" in e for e in errors)

    def test_transform_valid_transformType_passes(self, lint: ModuleType) -> None:
        for ttype in ("map", "filter", "expression"):
            definition = self._node("transform", {"transformType": ttype, "transformExpression": "x"})
            assert lint.validate_node_config_values(definition) == []

    def test_validate_schema_requires_dict_schema(self, lint: ModuleType) -> None:
        definition = self._node("validate_schema", {"schema": "not-a-dict"})
        errors = lint.validate_node_config_values(definition)
        assert any("schema must be a mapping" in e for e in errors)

    def test_validate_schema_dict_schema_passes(self, lint: ModuleType) -> None:
        definition = self._node("validate_schema", {"schema": {"type": "object"}})
        assert lint.validate_node_config_values(definition) == []

    def test_webhook_requires_non_empty_url(self, lint: ModuleType) -> None:
        definition = self._node("webhook", {"url": "   "})
        errors = lint.validate_node_config_values(definition)
        assert any("url" in e and "non-empty" in e for e in errors)

    def test_webhook_valid_url_passes(self, lint: ModuleType) -> None:
        definition = self._node("webhook", {"url": "https://example.com/hook"})
        assert lint.validate_node_config_values(definition) == []

    def test_cache_get_requires_non_empty_key(self, lint: ModuleType) -> None:
        definition = self._node("cache_get", {"key": ""})
        errors = lint.validate_node_config_values(definition)
        assert any("key" in e and "non-empty" in e for e in errors)

    def test_cache_get_valid_key_passes(self, lint: ModuleType) -> None:
        definition = self._node("cache_get", {"key": "session_id"})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", [-1, 0, "ten", None, True])
    def test_delay_requires_positive_delay_ms(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("delay", {"delayMs": value})
        errors = lint.validate_node_config_values(definition)
        assert any("delayMs" in e and "positive number" in e for e in errors)

    def test_delay_valid_delay_ms_passes(self, lint: ModuleType) -> None:
        definition = self._node("delay", {"delayMs": 500})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", [-1, 0, "three", None, 1.5])
    def test_retry_requires_positive_integer_max_retries(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("retry", {"maxRetries": value})
        errors = lint.validate_node_config_values(definition)
        assert any("maxRetries" in e and "positive integer" in e for e in errors)

    def test_retry_valid_max_retries_passes(self, lint: ModuleType) -> None:
        definition = self._node("retry", {"maxRetries": 3})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", [-1, 0, "60000", None, True])
    def test_timeout_requires_positive_integer_timeout_ms(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("timeout", {"timeoutMs": value})
        errors = lint.validate_node_config_values(definition)
        assert any("timeoutMs" in e and "positive integer" in e for e in errors)

    def test_timeout_valid_timeout_ms_passes(self, lint: ModuleType) -> None:
        definition = self._node("timeout", {"timeoutMs": 60000})
        assert lint.validate_node_config_values(definition) == []

    def test_timeout_rejects_empty_wrapped_node_id(self, lint: ModuleType) -> None:
        definition = self._node("timeout", {"timeoutMs": 1000, "wrapped_node_id": "  "})
        errors = lint.validate_node_config_values(definition)
        assert any("wrapped_node_id" in e and "non-empty" in e for e in errors)

    @pytest.mark.parametrize("level", ["info", "warning", "error"])
    def test_log_valid_level_and_message_passes(self, lint: ModuleType, level: str) -> None:
        definition = self._node("log", {"level": level, "message": "hello"})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("level", ["", "verbose", None])
    def test_log_rejects_invalid_level(self, lint: ModuleType, level: Any) -> None:
        definition = self._node("log", {"level": level, "message": "hello"})
        errors = lint.validate_node_config_values(definition)
        assert any("level must be one of" in e for e in errors)

    @pytest.mark.parametrize("message", ["", "   ", None])
    def test_log_rejects_empty_message(self, lint: ModuleType, message: Any) -> None:
        definition = self._node("log", {"level": "info", "message": message})
        errors = lint.validate_node_config_values(definition)
        assert any("message must be a non-empty" in e for e in errors)

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_condition_requires_non_empty_expression(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("condition", {"expression": value})
        errors = lint.validate_node_config_values(definition)
        assert any("expression" in e and "non-empty" in e for e in errors)

    def test_condition_valid_expression_passes(self, lint: ModuleType) -> None:
        definition = self._node("condition", {"expression": "inputs['ready']"})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_memory_write_requires_non_empty_collection(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("memory_write", {"collection": value})
        errors = lint.validate_node_config_values(definition)
        assert any("collection" in e and "non-empty" in e for e in errors)

    def test_memory_write_valid_collection_passes(self, lint: ModuleType) -> None:
        definition = self._node("memory_write", {"collection": "flowmanner_memory"})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_memory_read_requires_non_empty_query(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("memory_read", {"query": value})
        errors = lint.validate_node_config_values(definition)
        assert any("query" in e and "non-empty" in e for e in errors)

    def test_memory_read_valid_query_passes(self, lint: ModuleType) -> None:
        definition = self._node("memory_read", {"query": "search terms"})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", ["not-a-list", {}, [], None])
    def test_router_requires_non_empty_routes_list(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("router", {"routes": value})
        errors = lint.validate_node_config_values(definition)
        assert any("routes" in e and "non-empty list" in e for e in errors)

    def test_router_valid_routes_passes(self, lint: ModuleType) -> None:
        definition = self._node("router", {"routes": [{"target": "node_a"}]})
        assert lint.validate_node_config_values(definition) == []

    # ---- New node type value validation ----------------------------------

    def test_filter_requires_filter_transformType_and_expression(self, lint: ModuleType) -> None:
        definition = self._node("filter", {"transformType": "filter", "transformExpression": "x > 1"})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_filter_rejects_empty_transformExpression(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("filter", {"transformType": "filter", "transformExpression": value})
        errors = lint.validate_node_config_values(definition)
        assert any("transformExpression" in e and "non-empty" in e for e in errors)

    def test_filter_transformType_must_be_filter(self, lint: ModuleType) -> None:
        definition = self._node("filter", {"transformType": "map", "transformExpression": "x > 1"})
        errors = lint.validate_node_config_values(definition)
        assert any("transformType must be 'filter'" in e for e in errors)

    def test_llm_eval_requires_non_empty_prompt(self, lint: ModuleType) -> None:
        definition = self._node("llm_eval", {"prompt": ""})
        errors = lint.validate_node_config_values(definition)
        assert any("prompt" in e and "non-empty" in e for e in errors)

    def test_llm_eval_valid_prompt_passes(self, lint: ModuleType) -> None:
        definition = self._node("llm_eval", {"prompt": "judge this output"})
        assert lint.validate_node_config_values(definition) == []

    def test_browser_navigate_requires_dict_params_with_url(self, lint: ModuleType) -> None:
        definition = self._node("browser_navigate", {"params": {"url": "https://example.com"}})
        assert lint.validate_node_config_values(definition) == []

    @pytest.mark.parametrize("value", ["not-a-dict", None])
    def test_browser_navigate_rejects_non_dict_params(self, lint: ModuleType, value: Any) -> None:
        definition = self._node("browser_navigate", {"params": value})
        errors = lint.validate_node_config_values(definition)
        assert any("params must be a mapping" in e for e in errors)

    def test_browser_navigate_requires_non_empty_url(self, lint: ModuleType) -> None:
        definition = self._node("browser_navigate", {"params": {"url": ""}})
        errors = lint.validate_node_config_values(definition)
        assert any("params.url" in e and "non-empty" in e for e in errors)

    def test_browser_click_requires_dict_params(self, lint: ModuleType) -> None:
        definition = self._node("browser_click", {"params": {"selector": "#btn"}})
        assert lint.validate_node_config_values(definition) == []

    def test_browser_click_requires_ref_or_selector(self, lint: ModuleType) -> None:
        definition = self._node("browser_click", {"params": {"other": "value"}})
        errors = lint.validate_node_config_values(definition)
        assert any("ref" in e and "selector" in e for e in errors)

    def test_browser_click_accepts_ref(self, lint: ModuleType) -> None:
        definition = self._node("browser_click", {"params": {"ref": "e1"}})
        assert lint.validate_node_config_values(definition) == []

    def test_browser_click_rejects_non_dict_params(self, lint: ModuleType) -> None:
        definition = self._node("browser_click", {"params": "bad"})
        errors = lint.validate_node_config_values(definition)
        assert any("params must be a mapping" in e for e in errors)

    def test_browser_type_requires_dict_params_with_text(self, lint: ModuleType) -> None:
        definition = self._node("browser_type", {"params": {"selector": "#input", "text": "hello"}})
        assert lint.validate_node_config_values(definition) == []

    def test_browser_type_requires_non_empty_text(self, lint: ModuleType) -> None:
        definition = self._node("browser_type", {"params": {"text": ""}})
        errors = lint.validate_node_config_values(definition)
        assert any("params.text" in e and "non-empty" in e for e in errors)

    def test_browser_type_requires_ref_or_selector(self, lint: ModuleType) -> None:
        definition = self._node("browser_type", {"params": {"text": "hello"}})
        errors = lint.validate_node_config_values(definition)
        assert any("ref" in e and "selector" in e for e in errors)

    def test_browser_type_accepts_ref(self, lint: ModuleType) -> None:
        definition = self._node("browser_type", {"params": {"ref": "e1", "text": "hello"}})
        assert lint.validate_node_config_values(definition) == []

    def test_browser_scroll_accepts_empty_dict_params(self, lint: ModuleType) -> None:
        definition = self._node("browser_scroll", {"params": {}})
        assert lint.validate_node_config_values(definition) == []

    def test_browser_scroll_requires_dict_params(self, lint: ModuleType) -> None:
        definition = self._node("browser_scroll", {"params": "bad"})
        errors = lint.validate_node_config_values(definition)
        assert any("params must be a mapping" in e for e in errors)

    @pytest.mark.parametrize("node_type", ["browser_snapshot", "browser_screenshot", "browser_close"])
    def test_optional_browser_nodes_pass_with_empty_params(self, lint: ModuleType, node_type: str) -> None:
        definition = self._node(node_type, {})
        assert lint.validate_node_config_values(definition) == []


class TestNodeTypeTableDrift:
    """Ensure generated node type table stays in sync with the linter/source."""

    def test_generated_table_matches_committed_table(self) -> None:
        """Regenerate the table and assert it matches the committed version."""
        generator = _import_generator_module()
        generated = generator.generate_table()
        table_path = Path(__file__).resolve().parent.parent / "docs" / "substrate-node-types-table.md"
        committed = table_path.read_text(encoding="utf-8")
        assert generated == committed, (
            "Generated node type table drifts from committed table. "
            f"Run `python {generator.__file__}` to regenerate it."
        )


class TestValidateEdgeSemantics:
    """Edge condition values must match their source node type."""

    def _definition(self, nodes: list[dict], edges: list[dict]) -> dict:
        return {"nodes": nodes, "edges": edges}

    def test_condition_edge_true_false_are_valid(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "c", "type": "condition", "config": {"expression": "x"}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "b", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "c", "target": "a", "condition": "true"},
                {"source": "c", "target": "b", "condition": "false"},
            ],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_condition_edge_rejects_invalid_condition(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "c", "type": "condition", "config": {"expression": "x"}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "c", "target": "a", "condition": "maybe"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("condition node" in e and "'true' or 'false'" in e for e in errors)

    def test_timeout_edges_accept_default_and_on_timeout(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "t", "type": "timeout", "config": {"timeoutMs": 1000}},
                {"id": "child", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "fallback", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "t", "target": "child"},
                {"source": "t", "target": "fallback", "condition": "on_timeout"},
            ],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_timeout_edge_rejects_invalid_condition(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "t", "type": "timeout", "config": {"timeoutMs": 1000}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "t", "target": "a", "condition": "timeout"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("timeout node" in e and "'on_timeout', 'default', or no condition" in e for e in errors)

    def test_timeout_requires_on_timeout_edge(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "t", "type": "timeout", "config": {"timeoutMs": 1000}},
                {"id": "child", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "t", "target": "child"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("on_timeout" in e for e in errors)

    def test_timeout_requires_default_child(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "t", "type": "timeout", "config": {"timeoutMs": 1000}},
                {"id": "fallback", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "t", "target": "fallback", "condition": "on_timeout"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("wrapped_node_id" in e and "default outgoing edge" in e for e in errors)

    def test_timeout_wrapped_node_id_satisfies_default_child(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "t", "type": "timeout", "config": {"timeoutMs": 1000, "wrapped_node_id": "child"}},
                {"id": "fallback", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "t", "target": "fallback", "condition": "on_timeout"}],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_validate_schema_edges_accept_default_and_on_invalid(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "vs", "type": "validate_schema", "config": {"schema": {}}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "b", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "vs", "target": "a", "condition": "default"},
                {"source": "vs", "target": "b", "condition": "on_invalid"},
            ],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_router_edge_requires_non_empty_condition(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "r", "type": "router", "config": {"routes": [{"target": "a"}]}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "r", "target": "a"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("router node" in e and "non-empty condition" in e for e in errors)

    def test_non_branching_nodes_allow_unconditioned_edges(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "l", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "next", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "l", "target": "next"}],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_dag_condition_requires_one_true_and_one_false_edge(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "c", "type": "condition", "config": {"expression": "x"}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "b", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "c", "target": "a", "condition": "true"},
                {"source": "c", "target": "b", "condition": "false"},
            ],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_dag_condition_rejects_missing_branches(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "c", "type": "condition", "config": {"expression": "x"}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "c", "target": "a", "condition": "true"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("exactly one outgoing 'false' edge" in e for e in errors)

    def test_dag_condition_rejects_duplicate_branches(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "c", "type": "condition", "config": {"expression": "x"}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "b", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "d", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "c", "target": "a", "condition": "true"},
                {"source": "c", "target": "b", "condition": "true"},
                {"source": "c", "target": "d", "condition": "false"},
            ],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("exactly one outgoing 'true' edge" in e for e in errors)

    def test_dag_condition_rejects_same_target_for_both_branches(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "c", "type": "condition", "config": {"expression": "x"}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "c", "target": "a", "condition": "true"},
                {"source": "c", "target": "a", "condition": "false"},
            ],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("different targets" in e for e in errors)

    def test_validate_schema_rejects_invalid_condition(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "vs", "type": "validate_schema", "config": {"schema": {}}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "vs", "target": "a", "condition": "other"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("must have condition 'default' or 'on_invalid'" in e for e in errors)

    def test_validate_schema_structural_check_flags_edges_without_default_or_on_invalid(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "vs", "type": "validate_schema", "config": {"schema": {}}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "b", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "vs", "target": "a"},
                {"source": "vs", "target": "b"},
            ],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("has outgoing edges but none use" in e for e in errors)

    def test_validate_schema_rejects_unconditioned_edge(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "vs", "type": "validate_schema", "config": {"schema": {}}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "vs", "target": "a"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("must have condition 'default' or 'on_invalid'" in e for e in errors)

    def test_validate_schema_allows_terminal_node(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "vs", "type": "validate_schema", "config": {"schema": {}}},
            ],
            [],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_validate_schema_default_and_on_invalid_must_target_different_nodes(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "vs", "type": "validate_schema", "config": {"schema": {}}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "vs", "target": "a", "condition": "default"},
                {"source": "vs", "target": "a", "condition": "on_invalid"},
            ],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("different targets" in e for e in errors)

    def test_router_edge_matches_declared_route_id(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {
                    "id": "r",
                    "type": "router",
                    "config": {"routes": [{"id": "route_a"}, {"id": "route_b"}]},
                },
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "b", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "r", "target": "a", "condition": "route_a"},
                {"source": "r", "target": "b", "condition": "route_b"},
            ],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_router_edge_rejects_unknown_route_id(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {
                    "id": "r",
                    "type": "router",
                    "config": {"routes": [{"id": "route_a"}]},
                },
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "r", "target": "a", "condition": "route_b"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("route_b" in e and "does not match any declared route id" in e for e in errors)

    def test_router_edge_accepts_route_id_from_router_config(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {
                    "id": "r",
                    "type": "router",
                    "config": {"routerConfig": {"routes": [{"id": "alpha"}]}},
                },
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "r", "target": "a", "condition": "alpha"}],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_router_edge_accepts_default_route_id(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {
                    "id": "r",
                    "type": "router",
                    "config": {"routes": [], "defaultRouteId": "fallback"},
                },
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "r", "target": "a", "condition": "fallback"}],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_router_edge_skips_template_condition_when_route_ids_unknown(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "r", "type": "router", "config": {"routes": []}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "r", "target": "a", "condition": "{{ inputs.route }}"}],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_retry_with_one_default_edge_passes(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "r", "type": "retry", "config": {"maxRetries": 3}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "r", "target": "a"}],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_retry_with_wrapped_node_id_passes(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "r", "type": "retry", "config": {"maxRetries": 3, "wrapped_node_id": "a"}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [],
        )
        assert lint.validate_edge_semantics(definition) == []

    def test_retry_requires_default_edge_or_wrapped_node_id(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "r", "type": "retry", "config": {"maxRetries": 3}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("exactly one default outgoing edge" in e for e in errors)

    def test_retry_rejects_multiple_outgoing_edges(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "r", "type": "retry", "config": {"maxRetries": 3}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
                {"id": "b", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [
                {"source": "r", "target": "a"},
                {"source": "r", "target": "b"},
            ],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("exactly one default outgoing edge" in e for e in errors)

    def test_retry_rejects_conditioned_edge_as_only_outgoing(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "r", "type": "retry", "config": {"maxRetries": 3}},
                {"id": "a", "type": "log", "config": {"level": "info", "message": "x"}},
            ],
            [{"source": "r", "target": "a", "condition": "default"}],
        )
        # condition 'default' is allowed as a default edge
        assert lint.validate_edge_semantics(definition) == []

    def test_delay_cycle_two_nodes(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "d1", "type": "delay", "config": {"delayMs": 1000}},
                {"id": "d2", "type": "delay", "config": {"delayMs": 1000}},
            ],
            [
                {"source": "d1", "target": "d2"},
                {"source": "d2", "target": "d1"},
            ],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("part of a cycle" in e for e in errors)

    def test_delay_self_loop(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "d", "type": "delay", "config": {"delayMs": 1000}},
            ],
            [{"source": "d", "target": "d"}],
        )
        errors = lint.validate_edge_semantics(definition)
        assert any("part of a cycle" in e for e in errors)

    def test_delay_no_cycle_when_mixed_with_other_nodes(self, lint: ModuleType) -> None:
        definition = self._definition(
            [
                {"id": "d1", "type": "delay", "config": {"delayMs": 1000}},
                {"id": "c", "type": "condition", "config": {"expression": "x"}},
                {"id": "d2", "type": "delay", "config": {"delayMs": 1000}},
            ],
            [
                {"source": "d1", "target": "c"},
                {"source": "c", "target": "d2", "condition": "true"},
                {"source": "c", "target": "d1", "condition": "false"},
            ],
        )
        assert lint.validate_edge_semantics(definition) == []


class TestValidateBlueprint:
    """Validation path: required keys, graph errors, and adapter conversion."""

    def test_valid_blueprint_passes(self, lint: ModuleType, tmp_path: Path) -> None:
        data = {
            "version": 1,
            "name": "test-bp",
            "blueprint_type": "dag",
            "definition": {"nodes": [], "edges": []},
        }
        with (
            patch.object(lint, "validate_blueprint_definition", return_value=[]),
            patch.object(lint, "blueprint_to_workflow", return_value=None),
        ):
            errors = lint.validate_blueprint(tmp_path / "x.yaml", data)
        assert errors == []

    def test_missing_required_keys_reported(self, lint: ModuleType, tmp_path: Path) -> None:
        data: dict = {"version": 1, "definition": {"nodes": [], "edges": []}}
        # name and blueprint_type are missing.
        with (
            patch.object(lint, "validate_blueprint_definition", return_value=[]),
            patch.object(lint, "blueprint_to_workflow", return_value=None),
        ):
            errors = lint.validate_blueprint(tmp_path / "x.yaml", data)
        assert "Missing required top-level key: name" in errors
        assert "Missing required top-level key: blueprint_type" in errors

    def test_definition_must_be_mapping(self, lint: ModuleType, tmp_path: Path) -> None:
        data = {"version": 1, "name": "x", "blueprint_type": "dag", "definition": "bad"}
        errors = lint.validate_blueprint(tmp_path / "x.yaml", data)
        assert any("definition must be a mapping" in e for e in errors)

    def test_graph_validator_errors_returned(self, lint: ModuleType, tmp_path: Path) -> None:
        data = {
            "version": 1,
            "name": "x",
            "blueprint_type": "dag",
            "definition": {"nodes": [], "edges": []},
        }
        with (
            patch.object(lint, "validate_blueprint_definition", return_value=["bad edge"]),
            patch.object(lint, "blueprint_to_workflow", return_value=None),
        ):
            errors = lint.validate_blueprint(tmp_path / "x.yaml", data)
        assert "bad edge" in errors

    def test_adapter_invalid_graph_error(self, lint: ModuleType, tmp_path: Path) -> None:
        data = {
            "version": 1,
            "name": "x",
            "blueprint_type": "dag",
            "definition": {"nodes": [], "edges": []},
        }
        exc = lint.InvalidBlueprintGraphError("cycle detected")
        with (
            patch.object(lint, "validate_blueprint_definition", return_value=[]),
            patch.object(lint, "blueprint_to_workflow", side_effect=exc),
        ):
            errors = lint.validate_blueprint(tmp_path / "x.yaml", data)
        assert any("cycle detected" in e for e in errors)

    def test_unexpected_adapter_error_reported(self, lint: ModuleType, tmp_path: Path) -> None:
        data = {
            "version": 1,
            "name": "x",
            "blueprint_type": "dag",
            "definition": {"nodes": [], "edges": []},
        }
        with (
            patch.object(lint, "validate_blueprint_definition", return_value=[]),
            patch.object(lint, "blueprint_to_workflow", side_effect=RuntimeError("boom")),
        ):
            errors = lint.validate_blueprint(tmp_path / "x.yaml", data)
        assert any("RuntimeError: boom" in e for e in errors)


class TestMain:
    """End-to-end CLI behaviour using a temporary directory tree."""

    @pytest.fixture
    def sample_blueprint(self) -> dict:
        return {
            "version": 1,
            "name": "audit",
            "blueprint_type": "solo",
            "definition": {"nodes": []},
        }

    def test_returns_zero_when_all_blueprints_valid(
        self, lint: ModuleType, tmp_path: Path, sample_blueprint: dict
    ) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        (bp_dir / "audit.yaml").write_text(yaml.safe_dump(sample_blueprint))

        with (
            patch.object(lint, "validate_blueprint_definition", return_value=[]),
            patch.object(lint, "blueprint_to_workflow", return_value=None),
        ):
            result = lint.main([str(bp_dir)])

        assert result == 0

    def test_returns_one_when_blueprint_invalid(self, lint: ModuleType, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        # Missing required keys.
        (bp_dir / "bad.yaml").write_text(yaml.safe_dump({"blueprint_type": "dag", "definition": {}}))

        result = lint.main([str(bp_dir)])
        assert result == 1

    def test_returns_one_on_yaml_parse_error(self, lint: ModuleType, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        (bp_dir / "broken.yaml").write_text("{not valid yaml")

        result = lint.main([str(bp_dir)])
        assert result == 1

    def test_non_blueprint_yaml_is_ignored(self, lint: ModuleType, tmp_path: Path) -> None:
        bp_dir = tmp_path / "configs"
        bp_dir.mkdir()
        (bp_dir / "docker-compose.yaml").write_text("services:\n  app: null\n")

        result = lint.main([str(bp_dir)])
        assert result == 0

    def test_excluded_dirs_are_skipped_in_main(self, lint: ModuleType, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        # Even though this looks like a blueprint, it is inside docs/ and
        # should be skipped entirely.
        (docs / "ignored.yaml").write_text(
            yaml.safe_dump({"version": 1, "name": "x", "blueprint_type": "dag", "definition": {}})
        )

        result = lint.main([str(tmp_path)])
        assert result == 0

    def test_reliability_example_blueprint_passes(self, lint: ModuleType) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        path = repo_root / "backend" / "flowmanner-reliability-blueprint.yaml"
        result = lint.main([str(path)])
        assert result == 0


class TestApplyFixes:
    """Safe auto-corrections applied by apply_fixes()."""

    def _blueprint(self, nodes: list[dict] | None = None, *, with_edges: bool = True) -> dict:
        data: dict = {
            "version": 1,
            "name": "fixture",
            "blueprint_type": "dag",
            "definition": {"nodes": nodes or []},
        }
        if with_edges:
            data["definition"]["edges"] = []
        return data

    def test_renames_duration_to_delay_ms(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "d", "type": "delay", "config": {"duration": 2}}])
        changes = lint.apply_fixes(data)
        assert "renamed config.duration -> config.delayMs" in changes[0]
        # duration was in seconds, delayMs is in milliseconds.
        assert data["definition"]["nodes"][0]["config"]["delayMs"] == 2000
        assert "duration" not in data["definition"]["nodes"][0]["config"]

    def test_duration_conversion_accepts_string_number(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "d", "type": "delay", "config": {"duration": "2"}}])
        changes = lint.apply_fixes(data)
        assert any("renamed config.duration" in c for c in changes)
        assert data["definition"]["nodes"][0]["config"]["delayMs"] == 2000

    def test_duration_conversion_accepts_float(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "d", "type": "delay", "config": {"duration": 1.5}}])
        changes = lint.apply_fixes(data)
        assert any("renamed config.duration" in c for c in changes)
        assert data["definition"]["nodes"][0]["config"]["delayMs"] == 1500

    @pytest.mark.parametrize("value", [0, -1, "five"])
    def test_duration_conversion_rejects_invalid(self, lint: ModuleType, value: Any) -> None:
        data = self._blueprint([{"id": "d", "type": "delay", "config": {"duration": value}}])
        changes = lint.apply_fixes(data)
        assert any("could not convert value" in c for c in changes)
        assert "delayMs" not in data["definition"]["nodes"][0]["config"]
        assert "duration" not in data["definition"]["nodes"][0]["config"]

    def test_renames_max_retries_to_max_retries_camel(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "r", "type": "retry", "config": {"max_retries": 5}}])
        changes = lint.apply_fixes(data)
        assert "renamed config.max_retries -> config.maxRetries" in changes[0]
        assert data["definition"]["nodes"][0]["config"]["maxRetries"] == 5

    def test_collision_removes_deprecated_key(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "d", "type": "delay", "config": {"duration": 1000, "delayMs": 500}}])
        changes = lint.apply_fixes(data)
        assert any("removed deprecated config.duration" in c for c in changes)
        assert data["definition"]["nodes"][0]["config"]["delayMs"] == 500

    def test_log_defaults_added(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "log1", "type": "log", "config": {}, "title": "Step done"}])
        changes = lint.apply_fixes(data)
        config = data["definition"]["nodes"][0]["config"]
        assert config["level"] == "info"
        assert config["message"] == "Step done"
        assert any("set default config.level" in c for c in changes)
        assert any("set default config.message" in c for c in changes)

    def test_merge_default_strategy(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "m", "type": "merge", "config": {}}])
        changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"][0]["config"]["mergeStrategy"] == "concat"
        assert any("mergeStrategy" in c for c in changes)

    def test_split_default_mode(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "s", "type": "split", "config": {"splitOn": "items"}}])
        _changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"][0]["config"]["mode"] == "item"

    def test_webhook_default_method(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "wh", "type": "webhook", "config": {"url": "x"}}])
        _changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"][0]["config"]["method"] == "POST"

    def test_memory_read_default_collection(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "mr", "type": "memory_read", "config": {"query": "x"}}])
        _changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"][0]["config"]["collection"] == "flowmanner_memory"

    def test_validate_schema_default_payload_key(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "vs", "type": "validate_schema", "config": {"schema": {}}}])
        _changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"][0]["config"]["payload_key"] == "payload"

    def test_file_operation_default_operation(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "fo", "type": "file_operation", "config": {}}])
        _changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"][0]["config"]["operation"] == "read"

    def test_trims_whitespace_on_structural_strings(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "s", "type": "split", "config": {"splitOn": "  inputs.items  "}}])
        changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"][0]["config"]["splitOn"] == "inputs.items"
        assert any("trimmed whitespace" in c for c in changes)

    def test_does_not_trim_prompt_strings(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "l", "type": "llm_call", "config": {"prompt": "  keep spaces  "}}])
        changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"][0]["config"]["prompt"] == "  keep spaces  "
        assert not any("trimmed" in c for c in changes)

    def test_adds_missing_definition_nodes_and_edges(self, lint: ModuleType) -> None:
        data: dict = {
            "version": 1,
            "name": "x",
            "blueprint_type": "dag",
            "definition": {},
        }
        changes = lint.apply_fixes(data)
        assert data["definition"]["nodes"] == []
        assert data["definition"]["edges"] == []
        assert any("definition.nodes" in c for c in changes)
        assert any("definition.edges" in c for c in changes)

    def test_idempotent_no_changes_on_second_run(self, lint: ModuleType) -> None:
        data = self._blueprint([{"id": "d", "type": "delay", "config": {"duration": 1000}}])
        first = lint.apply_fixes(data)
        assert len(first) > 0
        second = lint.apply_fixes(data)
        assert second == []


class TestFixCLI:
    """CLI --fix and --dry-run behaviour."""

    def _sample_blueprint(self) -> dict:
        return {
            "version": 1,
            "name": "audit",
            "blueprint_type": "solo",
            "definition": {"nodes": []},
        }

    def test_dry_run_does_not_write_file(self, lint: ModuleType, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        bp = bp_dir / "audit.yaml"
        sample = self._sample_blueprint()
        # Add a fixable deprecated key.
        sample["definition"]["nodes"] = [{"id": "d", "type": "delay", "config": {"duration": 1000}}]
        bp.write_text(yaml.safe_dump(sample))

        result = lint.main(["--fix", "--dry-run", str(bp)])
        assert result == 0
        # File should still contain the old key.
        text = bp.read_text()
        assert "duration: 1000" in text
        assert "delayMs" not in text

    def test_fix_writes_corrected_file(self, lint: ModuleType, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        bp = bp_dir / "audit.yaml"
        sample = self._sample_blueprint()
        sample["definition"]["nodes"] = [{"id": "d", "type": "delay", "config": {"duration": 3}}]
        bp.write_text(yaml.safe_dump(sample))

        result = lint.main(["--fix", str(bp)])
        assert result == 0
        text = bp.read_text()
        assert "delayMs: 3000" in text
        assert "duration" not in text
