"""Unit tests for mission_code_sandbox — isolated sandboxed Python execution.

Tests are pure unit tests; no database, no FastAPI, no MissionExecutor.
Uses real subprocess for execute_python_in_sandbox integration tests.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from unittest.mock import patch

from app.services.mission_code_sandbox import (
    DANGEROUS_PATTERNS,
    DEFAULT_RESOURCE_LIMITS,
    _build_restricted_wrapper,
    _indent,
    execute_python_in_sandbox,
    scan_for_dangerous_patterns,
)

# ── _indent ───────────────────────────────────────────────────────────────────


class TestIndent:
    def test_single_line(self):
        assert _indent("hello", 4) == "    hello"

    def test_multiple_lines(self):
        result = _indent("line1\nline2\nline3", 2)
        assert result == "  line1\n  line2\n  line3"

    def test_preserves_blank_lines(self):
        result = _indent("line1\n\nline2", 4)
        assert result == "    line1\n\n    line2"

    def test_empty_string(self):
        assert _indent("", 4) == ""

    def test_zero_spaces(self):
        assert _indent("hello", 0) == "hello"

    def test_indent_python_code(self):
        code = "def foo():\n    return 42"
        result = _indent(code, 4)
        assert result == "    def foo():\n        return 42"


# ── scan_for_dangerous_patterns ──────────────────────────────────────────────


class TestScanForDangerousPatterns:
    def test_clean_code_returns_none(self):
        assert scan_for_dangerous_patterns("x = 1 + 2\nprint(x)") is None

    def test_clean_function_returns_none(self):
        assert (
            scan_for_dangerous_patterns(
                "def factorial(n):\n    return 1 if n <= 1 else n * factorial(n-1)"
            )
            is None
        )

    def test_clean_data_analysis_returns_none(self):
        assert (
            scan_for_dangerous_patterns(
                "import json\nimport csv\nprint(json.dumps([1,2,3]))"
            )
            is None
        )

    def test_detects_os_system(self):
        result = scan_for_dangerous_patterns("os.system('rm -rf /')")
        assert result == "os.system"

    def test_detects_subprocess_import(self):
        result = scan_for_dangerous_patterns("import subprocess\nsubprocess.run('ls')")
        assert result == "import subprocess"

    def test_detects_eval(self):
        result = scan_for_dangerous_patterns("eval('2+2')")
        assert result == "eval("

    def test_detects_exec(self):
        result = scan_for_dangerous_patterns("exec('print(42)')")
        assert result == "exec("

    def test_detects_open_call(self):
        result = scan_for_dangerous_patterns("open('/etc/passwd')")
        assert result == "open("

    def test_detects_globals(self):
        result = scan_for_dangerous_patterns("globals()['x'] = 1")
        assert result == "globals()"

    def test_detects_file_read(self):
        result = scan_for_dangerous_patterns("f.read()")
        assert result == ".read("

    def test_detects_sys_exit(self):
        result = scan_for_dangerous_patterns("sys.exit(1)")
        assert result == "sys.exit"

    def test_detects_passwd_path(self):
        # Use code that only contains /etc/passwd, not also open(
        result = scan_for_dangerous_patterns("path = '/etc/passwd'")
        assert result == "/etc/passwd"

    def test_case_insensitive(self):
        result = scan_for_dangerous_patterns("EVAL('hello')")
        assert result == "eval("

    def test_first_match_returned(self):
        result = scan_for_dangerous_patterns("import os\neval('x')")
        assert result == "import os"

    def test_empty_code(self):
        assert scan_for_dangerous_patterns("") is None

    def test_detects_breakpoint(self):
        result = scan_for_dangerous_patterns("breakpoint()")
        assert result == "breakpoint"

    def test_detects_shutil_rmtree(self):
        result = scan_for_dangerous_patterns("shutil.rmtree('/tmp/foo')")
        assert result == "shutil.rmtree"


# ── _build_restricted_wrapper ────────────────────────────────────────────────


class TestBuildRestrictedWrapper:
    def setup_method(self):
        self.workspace = "/tmp/test_ws"

    def test_contains_user_code_indented(self):
        code = "print('hello')"
        wrapper = _build_restricted_wrapper(code, self.workspace)
        assert "    print('hello')" in wrapper

    def test_contains_workspace_path(self):
        code = "pass"
        wrapper = _build_restricted_wrapper(code, self.workspace)
        assert repr(self.workspace) in wrapper

    def test_contains_safe_builtins(self):
        code = "pass"
        wrapper = _build_restricted_wrapper(code, self.workspace)
        assert "__builtins__ =" in wrapper
        # Verify key safe builtins are present in the wrapper
        assert "'print': print" in wrapper
        # At least one import is present (json or json+math)
        assert "import json" in wrapper or "import math" in wrapper

    def test_contains_try_except_guard(self):
        code = "pass"
        wrapper = _build_restricted_wrapper(code, self.workspace)
        assert "try:" in wrapper
        assert "except Exception" in wrapper
        assert "SANDBOX_ERROR" in wrapper

    def test_no_dangerous_builtins(self):
        code = "pass"
        wrapper = _build_restricted_wrapper(code, self.workspace)
        assert "'__import__'" not in wrapper

    def test_contains_restricted_open(self):
        code = "pass"
        wrapper = _build_restricted_wrapper(code, self.workspace)
        assert "def _restricted_open" in wrapper

    def test_multiline_code_preserved(self):
        code = "x = 1\ny = 2\nprint(x + y)"
        wrapper = _build_restricted_wrapper(code, self.workspace)
        assert "    x = 1" in wrapper
        assert "    y = 2" in wrapper
        assert "    print(x + y)" in wrapper


# ── execute_python_in_sandbox ────────────────────────────────────────────────


class TestExecutePythonInSandbox:

    def test_basic_print(self):
        result = execute_python_in_sandbox("print('hello world')")
        assert result["success"] is True
        assert "hello world" in result["output"]

    def test_arithmetic(self):
        result = execute_python_in_sandbox("print(2 + 3 * 4)")
        assert result["success"] is True
        assert "14" in result["output"]

    def test_json_output(self):
        code = (
            "import json\n"
            "data = {'key': 'value', 'numbers': [1, 2, 3]}\n"
            "print(json.dumps(data))"
        )
        result = execute_python_in_sandbox(code)
        assert result["success"] is True
        assert '"key"' in result["output"]
        assert '"value"' in result["output"]

    def test_math_import(self):
        code = "import math\nprint(math.sqrt(16))"
        result = execute_python_in_sandbox(code)
        assert result["success"] is True
        assert "4.0" in result["output"]

    def test_statistics_import(self):
        code = "import statistics\nprint(statistics.mean([1, 2, 3, 4, 5]))"
        result = execute_python_in_sandbox(code)
        assert result["success"] is True
        assert "3" in result["output"]

    def test_list_comprehension(self):
        code = "result = [x**2 for x in range(5)]\nprint(result)"
        result = execute_python_in_sandbox(code)
        assert result["success"] is True
        assert "[0, 1, 4, 9, 16]" in result["output"]

    def test_multiline_function(self):
        code = (
            "def fibonacci(n):\n"
            "    a, b = 0, 1\n"
            "    for _ in range(n):\n"
            "        a, b = b, a + b\n"
            "    return a\n"
            "print(fibonacci(10))"
        )
        result = execute_python_in_sandbox(code)
        assert result["success"] is True
        assert "55" in result["output"]

    def test_csv_import(self):
        code = (
            "import csv\n"
            "import io\n"
            "f = io.StringIO('a,b,c\\n1,2,3\\n4,5,6')\n"
            "reader = csv.reader(f)\n"
            "for row in reader:\n"
            "    print(row)"
        )
        result = execute_python_in_sandbox(code)
        assert result["success"] is True
        assert "['a', 'b', 'c']" in result["output"]

    # ── Blocked patterns ──────────────────────────────────────────────────

    def test_blocked_os_system(self):
        result = execute_python_in_sandbox("import os\nos.system('ls')")
        assert result["success"] is False
        assert "blocked pattern" in result["error"].lower()

    def test_blocked_subprocess(self):
        result = execute_python_in_sandbox("import subprocess\nsubprocess.run('ls')")
        assert result["success"] is False
        assert "blocked pattern" in result["error"].lower()

    def test_blocked_eval(self):
        result = execute_python_in_sandbox("eval('2+2')")
        assert result["success"] is False
        assert "blocked pattern" in result["error"].lower()

    def test_blocked_open(self):
        result = execute_python_in_sandbox("open('/etc/passwd')")
        assert result["success"] is False
        assert "blocked pattern" in result["error"].lower()

    def test_blocked_globals(self):
        result = execute_python_in_sandbox("globals().clear()")
        assert result["success"] is False
        assert "blocked pattern" in result["error"].lower()

    # ── Runtime errors in sandbox ─────────────────────────────────────────

    def test_syntax_error(self):
        result = execute_python_in_sandbox("print('unclosed string)")
        assert result["success"] is False
        assert len(result["error"]) > 0

    def test_name_error(self):
        result = execute_python_in_sandbox("print(undefined_variable)")
        assert result["success"] is False

    def test_zero_division(self):
        result = execute_python_in_sandbox("x = 1 / 0\nprint(x)")
        assert result["success"] is False

    # ── Resource limits ───────────────────────────────────────────────────

    def test_timeout(self):
        code = "import time\nwhile True:\n    time.sleep(10)\n"
        result = execute_python_in_sandbox(
            code,
            resource_limits={
                "cpu_seconds": 1,
                "memory_mb": 512,
                "output_size_bytes": 10000,
            },
        )
        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    def test_output_truncation(self):
        code = "for i in range(10000):\n    print('x' * 100)"
        result = execute_python_in_sandbox(
            code,
            resource_limits={
                "cpu_seconds": 10,
                "memory_mb": 512,
                "output_size_bytes": 100,
            },
        )
        assert result["success"] is True
        assert "[OUTPUT TRUNCATED]" in result["output"]

    # ── Workspace ─────────────────────────────────────────────────────────

    def test_custom_workspace(self):
        """Test sandbox executes with custom workspace and can verify it exists."""
        ws = tempfile.mkdtemp(prefix="test_sandbox_")
        try:
            # Write a file in workspace for verification
            test_file = os.path.join(ws, "data.txt")
            with open(test_file, "w") as f:
                f.write("secret data")

            # Verify the workspace dir exists and has the file.
            # Avoid "import os" which is blocked. Use the sandbox-provided
            # _os module import (already at top of wrapper) to check.
            code = (
                "import io\n"
                "import json\n"
                # Use the _os from the wrapper module scope
                f"entries = sorted([e for e in _os.listdir({ws!r}) if not e.startswith('.')])\n"
                "print('FOUND:' + ','.join(entries))\n"
            )
            result = execute_python_in_sandbox(code, workspace=ws)
            assert result["success"] is True, f"Sandbox failed: {result.get('error')}"
            assert "data.txt" in result["output"]
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_restricted_open_blocks_write(self):
        """Verify _restricted_open in the generated wrapper blocks write modes."""
        ws = "/tmp/test_ws"
        wrapper = _build_restricted_wrapper("pass", ws)
        # The generated wrapper must define _restricted_open with write-blocking logic
        assert "def _restricted_open" in wrapper
        assert "'w' in mode" in wrapper
        assert "'a' in mode" in wrapper
        assert "'x' in mode" in wrapper
        assert "'+' in mode" in wrapper
        assert "PermissionError" in wrapper
        assert "Write access denied" in wrapper

    # ── Edge cases ────────────────────────────────────────────────────────

    def test_empty_code(self):
        result = execute_python_in_sandbox("")
        assert result["success"] is True, f"Empty code failed: {result.get('error')}"

    def test_only_comments(self):
        result = execute_python_in_sandbox("# just a comment")
        assert result["success"] is True, f"Comment-only failed: {result.get('error')}"

    def test_whitespace_only(self):
        result = execute_python_in_sandbox("   \n  \n  ")
        assert (
            result["success"] is True
        ), f"Whitespace-only failed: {result.get('error')}"

    def test_large_code_output(self):
        code = "print('hello' * 1000)"
        result = execute_python_in_sandbox(code)
        assert result["success"] is True

    def test_unicode_output(self):
        code = 'print("héllo wørld \\U0001f389")'
        result = execute_python_in_sandbox(code)
        assert result["success"] is True
        assert "héllo wørld" in result["output"]

    # ── Subprocess failure simulation ─────────────────────────────────────

    def test_subprocess_run_exception(self):
        with patch("subprocess.run", side_effect=OSError("fake OS error")):
            result = execute_python_in_sandbox("print('test')")
        assert result["success"] is False
        assert "sandbox execution error" in result["error"].lower()


# ── Constants ─────────────────────────────────────────────────────────────────


class TestConstants:
    def test_dangerous_patterns_not_empty(self):
        assert len(DANGEROUS_PATTERNS) > 10

    def test_dangerous_patterns_all_lowercase(self):
        for pattern in DANGEROUS_PATTERNS:
            assert pattern == pattern.lower(), f"Pattern not lowercase: {pattern}"

    def test_default_resource_limits_have_required_keys(self):
        assert "cpu_seconds" in DEFAULT_RESOURCE_LIMITS
        assert "memory_mb" in DEFAULT_RESOURCE_LIMITS
        assert "output_size_bytes" in DEFAULT_RESOURCE_LIMITS
