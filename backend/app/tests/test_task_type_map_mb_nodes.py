"""Wave-0 mapping assertions for Mission Builder node types.

These four palette node types have a real backend handler that was previously
absent from ``_TASK_TYPE_MAP`` and silently collapsed to ``NodeType.LLM_CALL``.
The map entries are correct; see the closing handoff for the FE config-shape
findings that are intentionally OUT OF SCOPE for Wave 0.
"""

from __future__ import annotations

from app.services.substrate.adapters import _TASK_TYPE_MAP
from app.services.substrate.workflow_models import NodeType


class TestMbNodesWave0Mapping:
    def test_prompt_maps_to_llm_call(self):
        assert _TASK_TYPE_MAP["prompt"] is NodeType.LLM_CALL

    def test_code_transform_maps_to_code_execution(self):
        assert _TASK_TYPE_MAP["code_transform"] is NodeType.CODE_EXECUTION

    def test_search_retrieve_maps_to_rag_query(self):
        assert _TASK_TYPE_MAP["search_retrieve"] is NodeType.RAG_QUERY

    def test_subflow_maps_to_sub_workflow(self):
        assert _TASK_TYPE_MAP["subflow"] is NodeType.SUB_WORKFLOW
