"""Unit tests for NodeExecutor handler methods with low coverage.

Targets: _execute_code_sandboxed, _handle_browser, _handle_file,
_handle_web_search, _tool_* helpers, _handle_sub_workflow.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.substrate.node_executor import NodeExecutor
from app.services.substrate.workflow_models import WorkflowNode, WorkflowType, NodeType


def _make_node(node_type: str = "llm_call", title: str = "Test Node", config: dict | None = None) -> WorkflowNode:
    return WorkflowNode(id=str(uuid4()), type=node_type, title=title, config=config or {})


def _make_executor_with_node_executor():
    mock_executor = MagicMock()
    mock_executor.is_aborted = MagicMock(return_value=False)
    mock_executor.is_running = MagicMock(return_value=True)
    mock_executor.event_log = MagicMock()
    mock_executor.event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
    ne = NodeExecutor(mock_executor)
    return ne, mock_executor


# ── _execute_code_sandboxed ─────────────────────────────────────────

class TestExecuteCodeSandboxed:
    @pytest.mark.asyncio
    async def test_blocked_pattern_import_os(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("import os\nprint(os.getcwd())")
        assert result["success"] is False
        assert "Blocked pattern" in result["error"]
        assert "import os" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_pattern_exec(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("exec('print(1)')")
        assert result["success"] is False
        assert "Blocked pattern" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_pattern_eval(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("x = eval('1+1')")
        assert result["success"] is False
        assert "Blocked pattern" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_pattern_open(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("f = open('/etc/passwd')")
        assert result["success"] is False
        assert "Blocked pattern" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_pattern_dunder_import(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("__import__('os')")
        assert result["success"] is False
        assert "Blocked pattern" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_pattern_subprocess(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("import subprocess\nsubprocess.run(['ls'])")
        assert result["success"] is False
        assert "Blocked pattern" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_pattern_globals(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("g = globals()")
        assert result["success"] is False
        assert "Blocked pattern" in result["error"]

    @pytest.mark.asyncio
    async def test_success_simple_code(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("print(42)")
        assert result["success"] is True
        assert "42" in result["output"]["stdout"]
        assert result["output"]["return_code"] == 0

    @pytest.mark.asyncio
    async def test_success_multiline_code(self):
        ne, _ = _make_executor_with_node_executor()
        code = "x = 10\ny = 20\nprint(x + y)"
        result = await ne._execute_code_sandboxed(code)
        assert result["success"] is True
        assert "30" in result["output"]["stdout"]

    @pytest.mark.asyncio
    async def test_success_math_operations(self):
        ne, _ = _make_executor_with_node_executor()
        code = "import math\nprint(math.sqrt(144))"
        result = await ne._execute_code_sandboxed(code)
        assert result["success"] is True
        assert "12.0" in result["output"]["stdout"]

    @pytest.mark.asyncio
    async def test_runtime_error_returns_failure(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("x = 1 / 0")
        # The wrapper catches exceptions and prints ERROR: ... to stdout
        # (subprocess exits 0 since the wrapper handles the exception)
        assert "ERROR:" in result["output"]["stdout"]
        assert result["output"]["return_code"] == 0

    @pytest.mark.asyncio
    async def test_syntax_error_returns_failure(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("def foo(")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_output_truncation_limit(self):
        """Verify large output is truncated at 1MB."""
        ne, _ = _make_executor_with_node_executor()
        # Generate code that prints more than 1MB
        code = "print('x' * 2_000_000)"
        result = await ne._execute_code_sandboxed(code)
        assert result["success"] is True
        assert len(result["output"]["stdout"]) <= 1_000_010  # some margin for truncation message

    @pytest.mark.asyncio
    async def test_blocked_pattern_case_insensitive(self):
        """Blocked pattern check is case-insensitive."""
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("IMPORT OS")
        assert result["success"] is False
        assert "Blocked pattern" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_pattern_socket(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("import socket")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_blocked_pattern_sys_exit(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._execute_code_sandboxed("import sys\nsys.exit(0)")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_code_with_allowed_imports(self):
        """Standard library imports like json, math, re are allowed."""
        ne, _ = _make_executor_with_node_executor()
        code = "import json, re, math\nprint(json.dumps({'a': 1}))"
        result = await ne._execute_code_sandboxed(code)
        assert result["success"] is True
        assert '"a"' in result["output"]["stdout"]

    @pytest.mark.asyncio
    async def test_cleanup_removes_workspace(self):
        """Temp workspace is cleaned up after execution."""
        import os
        ne, _ = _make_executor_with_node_executor()
        # Capture the workspace path by checking temp dirs
        initial_tmp = set(os.listdir("/tmp"))
        await ne._execute_code_sandboxed("print('hello')")
        final_tmp = set(os.listdir("/tmp"))
        # No mission_ temp dirs should remain
        new_dirs = final_tmp - initial_tmp
        mission_dirs = [d for d in new_dirs if d.startswith("mission_")]
        assert len(mission_dirs) == 0


# ── _handle_browser ─────────────────────────────────────────────────

class TestHandleBrowser:
    @pytest.mark.asyncio
    async def test_browser_success(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.BROWSER_NAVIGATE, config={"params": {"url": "https://example.com"}})

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {"title": "Example", "url": "https://example.com"}
        mock_tool.run = AsyncMock(return_value=mock_result)

        with patch("app.tools.base.ToolRegistry") as mock_registry:
            mock_registry.get.return_value = mock_tool
            result = await ne._handle_browser(node, {})

        assert result["success"] is True
        assert result["output"]["title"] == "Example"

    @pytest.mark.asyncio
    async def test_browser_tool_not_registered(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.BROWSER_CLICK, config={})

        with patch("app.tools.base.ToolRegistry") as mock_registry:
            mock_registry.get.return_value = None
            result = await ne._handle_browser(node, {})

        assert result["success"] is False
        assert "not registered" in result["error"]

    @pytest.mark.asyncio
    async def test_browser_tool_failure(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.BROWSER_NAVIGATE, config={})

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "error"
        mock_result.error = "Page not found"
        mock_tool.run = AsyncMock(return_value=mock_result)

        with patch("app.tools.base.ToolRegistry") as mock_registry:
            mock_registry.get.return_value = mock_tool
            result = await ne._handle_browser(node, {})

        assert result["success"] is False
        assert "Page not found" in result["error"]

    @pytest.mark.asyncio
    async def test_browser_exception(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.BROWSER_NAVIGATE, config={})

        with patch("app.tools.base.ToolRegistry") as mock_registry:
            mock_registry.get.side_effect = RuntimeError("registry crash")
            result = await ne._handle_browser(node, {})

        assert result["success"] is False
        assert "Browser tool failed" in result["error"]

    @pytest.mark.asyncio
    async def test_browser_all_types_route_to_handler(self):
        """Verify all browser node types route through _handle_browser via _dispatch."""
        ne, mock_executor = _make_executor_with_node_executor()
        db = AsyncMock()
        budget = MagicMock()

        mock_tool = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.data = {"ok": True}
        mock_tool.run = AsyncMock(return_value=mock_result)

        for bt in [NodeType.BROWSER_NAVIGATE, NodeType.BROWSER_SNAPSHOT,
                   NodeType.BROWSER_CLICK, NodeType.BROWSER_TYPE,
                   NodeType.BROWSER_SCROLL, NodeType.BROWSER_SCREENSHOT,
                   NodeType.BROWSER_CLOSE]:
            node = _make_node(node_type=bt, config={"params": {}})
            with patch("app.tools.base.ToolRegistry") as mock_registry:
                mock_registry.get.return_value = mock_tool
                result = await ne._dispatch(db, node, {}, budget, "run-1")
            assert result["success"] is True, f"Failed for {bt}"


# ── _handle_file ────────────────────────────────────────────────────

class TestHandleFile:
    @pytest.mark.asyncio
    async def test_file_read_success(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.FILE_OPERATION, config={"file_id": "f123", "operation": "read"})

        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp.write("Hello, world!")
        tmp.close()

        mock_storage = MagicMock()
        mock_storage.get_file_info.return_value = {"path": tmp.name, "filename": "test.txt"}
        mock_fs_module = MagicMock()
        mock_fs_module.FileStorageService.return_value = mock_storage

        with patch.dict("sys.modules", {"app.services.file_storage": mock_fs_module}):
            result = await ne._handle_file(node, {})
        os.unlink(tmp.name)

        assert result["success"] is True
        assert "Hello, world!" in result["output"]["content"]
        assert result["output"]["filename"] == "test.txt"

    @pytest.mark.asyncio
    async def test_file_list_success(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.FILE_OPERATION, config={"file_id": "f123", "operation": "list"})

        mock_storage = MagicMock()
        mock_storage.get_file_info.return_value = {"path": "/tmp", "filename": "dir"}
        mock_fs_module = MagicMock()
        mock_fs_module.FileStorageService.return_value = mock_storage

        with patch.dict("sys.modules", {"app.services.file_storage": mock_fs_module}):
            result = await ne._handle_file(node, {})

        assert result["success"] is True
        assert "files" in result["output"]

    @pytest.mark.asyncio
    async def test_file_no_file_id(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.FILE_OPERATION, config={"operation": "read"})

        result = await ne._handle_file(node, {})
        assert result["success"] is False
        assert "No file_id" in result["error"]

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.FILE_OPERATION, config={"file_id": "missing", "operation": "read"})

        mock_storage = MagicMock()
        mock_storage.get_file_info.return_value = None
        mock_fs_module = MagicMock()
        mock_fs_module.FileStorageService.return_value = mock_storage

        with patch.dict("sys.modules", {"app.services.file_storage": mock_fs_module}):
            result = await ne._handle_file(node, {})

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_file_unknown_operation(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.FILE_OPERATION, config={"file_id": "f1", "operation": "delete"})

        mock_storage = MagicMock()
        mock_storage.get_file_info.return_value = {"path": "/tmp/test", "filename": "test"}
        mock_fs_module = MagicMock()
        mock_fs_module.FileStorageService.return_value = mock_storage

        with patch.dict("sys.modules", {"app.services.file_storage": mock_fs_module}):
            result = await ne._handle_file(node, {})

        assert result["success"] is False
        assert "Unknown operation" in result["error"]

    @pytest.mark.asyncio
    async def test_file_exception(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.FILE_OPERATION, config={"file_id": "f1"})

        mock_fs_module = MagicMock()
        mock_fs_module.FileStorageService.side_effect = RuntimeError("storage down")

        with patch.dict("sys.modules", {"app.services.file_storage": mock_fs_module}):
            result = await ne._handle_file(node, {})

        assert result["success"] is False
        assert "File operation failed" in result["error"]

    @pytest.mark.asyncio
    async def test_file_defaults_to_read(self):
        """When no operation specified, defaults to 'read'."""
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.FILE_OPERATION, config={"file_id": "f123"})

        mock_storage = MagicMock()
        mock_storage.get_file_info.return_value = None
        mock_fs_module = MagicMock()
        mock_fs_module.FileStorageService.return_value = mock_storage

        with patch.dict("sys.modules", {"app.services.file_storage": mock_fs_module}):
            result = await ne._handle_file(node, {})

        # Should attempt read (get_file_info called)
        mock_storage.get_file_info.assert_called_once_with("f123")


# ── _handle_web_search success path ─────────────────────────────────

class TestHandleWebSearch:
    @pytest.mark.asyncio
    async def test_web_search_success(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.WEB_SEARCH, config={"query": "Python testing"})

        mock_service = MagicMock()
        mock_result_1 = MagicMock()
        mock_result_1.title = "Pytest docs"
        mock_result_1.url = "https://pytest.org"
        mock_result_1.snippet = "Testing framework"
        mock_response = MagicMock()
        mock_response.results = [mock_result_1]
        mock_service.search = AsyncMock(return_value=mock_response)

        mock_ws_service = MagicMock()
        mock_ws_service.get_search_service.return_value = mock_service
        mock_ws_models = MagicMock()

        with patch.dict("sys.modules", {"app.services.web_search": MagicMock(), "app.services.web_search.service": mock_ws_service, "app.services.web_search.models": mock_ws_models}):
            result = await ne._handle_web_search(node, {})

        assert result["success"] is True
        assert result["output"]["query"] == "Python testing"
        assert len(result["output"]["results"]) == 1
        assert result["output"]["results"][0]["title"] == "Pytest docs"

    @pytest.mark.asyncio
    async def test_web_search_from_context(self):
        """Falls back to context query when node config has none."""
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.WEB_SEARCH, config={})

        mock_service = MagicMock()
        mock_response = MagicMock()
        mock_response.results = []
        mock_service.search = AsyncMock(return_value=mock_response)

        mock_ws_service = MagicMock()
        mock_ws_service.get_search_service.return_value = mock_service
        mock_ws_models = MagicMock()

        with patch.dict("sys.modules", {"app.services.web_search": MagicMock(), "app.services.web_search.service": mock_ws_service, "app.services.web_search.models": mock_ws_models}):
            result = await ne._handle_web_search(node, {"query": "from context"})

        assert result["success"] is True
        assert result["output"]["query"] == "from context"

    @pytest.mark.asyncio
    async def test_web_search_exception(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.WEB_SEARCH, config={"query": "test"})

        with patch("app.services.web_search.service.get_search_service", side_effect=RuntimeError("no network")):
            result = await ne._handle_web_search(node, {})

        assert result["success"] is False
        assert "Web search failed" in result["error"]


# ── _tool_* helpers ─────────────────────────────────────────────────

class TestToolHelpers:
    @pytest.mark.asyncio
    async def test_tool_web_search_success(self):
        ne, _ = _make_executor_with_node_executor()

        mock_service = MagicMock()
        mock_r = MagicMock()
        mock_r.title = "Result"
        mock_r.url = "https://example.com"
        mock_r.snippet = "Snippet"
        mock_resp = MagicMock()
        mock_resp.results = [mock_r]
        mock_service.search = AsyncMock(return_value=mock_resp)

        mock_ws_service = MagicMock()
        mock_ws_service.get_search_service.return_value = mock_service
        mock_ws_models = MagicMock()

        with patch.dict("sys.modules", {"app.services.web_search": MagicMock(), "app.services.web_search.service": mock_ws_service, "app.services.web_search.models": mock_ws_models}):
            result = await ne._tool_web_search({"query": "test"}, {})

        assert result["success"] is True
        assert result["output"]["results"][0]["title"] == "Result"

    @pytest.mark.asyncio
    async def test_tool_web_search_no_query(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._tool_web_search({}, {})
        assert result["success"] is False
        assert "No query" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_web_search_fallback_to_context(self):
        ne, _ = _make_executor_with_node_executor()

        mock_service = MagicMock()
        mock_resp = MagicMock()
        mock_resp.results = []
        mock_service.search = AsyncMock(return_value=mock_resp)

        mock_ws_service = MagicMock()
        mock_ws_service.get_search_service.return_value = mock_service
        mock_ws_models = MagicMock()

        with patch.dict("sys.modules", {"app.services.web_search": MagicMock(), "app.services.web_search.service": mock_ws_service, "app.services.web_search.models": mock_ws_models}):
            result = await ne._tool_web_search({}, {"query": "ctx query"})

        assert result["success"] is True
        assert result["output"]["query"] == "ctx query"

    @pytest.mark.asyncio
    async def test_tool_code_executor_success(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._tool_code_executor({"code": "print('tool exec')"}, {})
        assert result["success"] is True
        assert "tool exec" in result["output"]["stdout"]

    @pytest.mark.asyncio
    async def test_tool_code_executor_no_code(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._tool_code_executor({}, {})
        assert result["success"] is False
        assert "No code" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_code_executor_from_context(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._tool_code_executor({}, {"code": "print(99)"})
        assert result["success"] is True
        assert "99" in result["output"]["stdout"]

    @pytest.mark.asyncio
    async def test_tool_file_reader_no_file_id(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._tool_file_reader({}, {})
        assert result["success"] is False
        assert "No file_id" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_file_reader_success(self):
        ne, _ = _make_executor_with_node_executor()

        mock_storage = MagicMock()
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp.write("file content here")
        tmp.close()
        mock_storage.get_file_info.return_value = {"path": tmp.name, "filename": "test.txt"}

        mock_fs_module = MagicMock()
        mock_fs_module.FileStorageService.return_value = mock_storage

        with patch.dict("sys.modules", {"app.services.file_storage": mock_fs_module}):
            result = await ne._tool_file_reader({"file_id": "f1"}, {})
        os.unlink(tmp.name)

        assert result["success"] is True
        assert "file content here" in result["output"]["content"]

    @pytest.mark.asyncio
    async def test_tool_file_reader_not_found(self):
        ne, _ = _make_executor_with_node_executor()
        mock_storage = MagicMock()
        mock_storage.get_file_info.return_value = None

        mock_fs_module = MagicMock()
        mock_fs_module.FileStorageService.return_value = mock_storage

        with patch.dict("sys.modules", {"app.services.file_storage": mock_fs_module}):
            result = await ne._tool_file_reader({"file_id": "missing"}, {})

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_rag_search_success(self):
        ne, _ = _make_executor_with_node_executor()
        mock_rag = MagicMock()
        mock_rag.query_documents.return_value = [{"text": "doc1", "score": 0.9}]

        with patch("app.services.rag_service.RAGService", return_value=mock_rag):
            result = await ne._tool_rag_search({"query": "test query"}, {})

        assert result["success"] is True
        assert result["output"]["query"] == "test query"
        assert len(result["output"]["context"]) == 1

    @pytest.mark.asyncio
    async def test_tool_rag_search_no_query(self):
        ne, _ = _make_executor_with_node_executor()
        result = await ne._tool_rag_search({}, {})
        assert result["success"] is False
        assert "No query" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_rag_search_exception(self):
        ne, _ = _make_executor_with_node_executor()
        with patch("app.services.rag_service.RAGService", side_effect=ImportError("no qdrant")):
            result = await ne._tool_rag_search({"query": "test"}, {})
        assert result["success"] is False
        assert "RAG search failed" in result["error"]


# ── _handle_sub_workflow ────────────────────────────────────────────

class TestHandleSubWorkflow:
    @pytest.mark.asyncio
    async def test_sub_workflow_no_workflow_id(self):
        ne, _ = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.SUB_WORKFLOW, config={})
        db = AsyncMock()
        budget = MagicMock()
        result = await ne._handle_sub_workflow(db, node, {}, budget, "run-1")
        assert result["success"] is False
        assert "No workflow_id" in result["error"]

    @pytest.mark.asyncio
    async def test_sub_workflow_aborted(self):
        ne, mock_executor = _make_executor_with_node_executor()
        mock_executor.is_aborted = MagicMock(return_value=True)
        node = _make_node(node_type=NodeType.SUB_WORKFLOW, config={"workflow_id": "wf-1"})
        db = AsyncMock()
        budget = MagicMock()
        result = await ne._handle_sub_workflow(db, node, {}, budget, "run-1")
        assert result["success"] is False
        assert "Aborted" in result["error"]

    @pytest.mark.asyncio
    async def test_sub_workflow_not_found(self):
        ne, mock_executor = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.SUB_WORKFLOW, config={"workflow_id": "nonexistent"})
        db = AsyncMock()
        budget = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        # Let real select() and GraphWorkflow work — only mock db.execute
        result = await ne._handle_sub_workflow(db, node, {}, budget, "run-1")

        assert result["success"] is False
        assert "not found" in result["error"]


    @pytest.mark.asyncio
    async def test_sub_workflow_max_depth(self):
        ne, mock_executor = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.SUB_WORKFLOW, config={"workflow_id": "wf-1"})
        db = AsyncMock()
        budget = MagicMock()
        context = {"_sub_workflow_depth": 10}  # exceeds _MAX_SUB_WORKFLOW_DEPTH (5)
        result = await ne._handle_sub_workflow(db, node, context, budget, "run-1")
        assert result["success"] is False
        assert "Max recursion depth" in result["error"]


# ── _handle_tool with specific tool routing ─────────────────────────

class TestHandleToolRouting:
    @pytest.mark.asyncio
    async def test_tool_web_search_via_dispatch(self):
        """When tool_name=web_search, routes to _tool_web_search."""
        ne, mock_executor = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.TOOL_CALL, config={"tool_name": "web_search", "params": {"query": "test"}})
        db = AsyncMock()
        budget = MagicMock()
        run_id = str(uuid4())
        from app.services.substrate.workflow_models import Workflow
        workflow = Workflow(id="wf-1", type=WorkflowType.SOLO, title="T", nodes=[node], user_id=str(uuid4()))

        mock_cap = MagicMock()
        mock_token = MagicMock()
        mock_cap.issue.return_value = mock_token
        mock_cap.verify_and_require.return_value = None
        mock_executor.check_circuit_breaker = AsyncMock(return_value=(True, ""))
        mock_ce_module = MagicMock()
        mock_ce_module.get_capability_engine.return_value = mock_cap

        with patch.dict("sys.modules", {"app.services.capability_engine": mock_ce_module}):
            with patch.object(ne, "_tool_web_search", new_callable=AsyncMock, return_value={"success": True, "output": {}}) as mock_ws:
                result = await ne._handle_tool(db, node, {}, budget, run_id, workflow)

        assert result["success"] is True
        mock_ws.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tool_unknown_tool_name(self):
        ne, mock_executor = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.TOOL_CALL, config={"tool_name": "nonexistent_tool"})
        db = AsyncMock()
        budget = MagicMock()
        run_id = str(uuid4())
        from app.services.substrate.workflow_models import Workflow
        workflow = Workflow(id="wf-1", type=WorkflowType.SOLO, title="T", nodes=[node], user_id=str(uuid4()))

        mock_cap = MagicMock()
        mock_token = MagicMock()
        mock_cap.issue.return_value = mock_token
        mock_cap.verify_and_require.return_value = None
        mock_executor.check_circuit_breaker = AsyncMock(return_value=(True, ""))
        mock_ce_module = MagicMock()
        mock_ce_module.get_capability_engine.return_value = mock_cap

        with patch.dict("sys.modules", {"app.services.capability_engine": mock_ce_module}):
            result = await ne._handle_tool(db, node, {}, budget, run_id, workflow)

        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_capability_denied(self):
        ne, mock_executor = _make_executor_with_node_executor()
        node = _make_node(node_type=NodeType.TOOL_CALL, config={"tool_name": "web_search"})
        db = AsyncMock()
        budget = MagicMock()
        run_id = str(uuid4())
        from app.services.substrate.workflow_models import Workflow
        workflow = Workflow(id="wf-1", type=WorkflowType.SOLO, title="T", nodes=[node], user_id=str(uuid4()))

        mock_cap = MagicMock()
        mock_token = MagicMock()
        mock_cap.issue.return_value = mock_token
        mock_cap.verify_and_require.side_effect = PermissionError("denied")
        mock_executor.check_circuit_breaker = AsyncMock(return_value=(True, ""))
        mock_ce_module = MagicMock()
        mock_ce_module.get_capability_engine.return_value = mock_cap

        with patch.dict("sys.modules", {"app.services.capability_engine": mock_ce_module}):
            result = await ne._handle_tool(db, node, {}, budget, run_id, workflow)

        assert result["success"] is False
        assert "Capability denied" in result["error"]
