"""Tests for the Python sandbox bypassability guard (audit B23).

These assert the defense-in-depth pre-scan (added in B23) blocks known
denylist-bypass primitives that an import-level denylist alone misses:
   - ctypes / importlib / __import__ / compile( / __loader__
   - sys.modules probing for already-loaded escape modules
"""

import pytest

from app.tools.python_sandbox import (
    SecurityError,
    _is_code_allowed,
    _security_prescan,
)

# ── _security_prescan blocks bypass primitives ──────────────────────


class TestSecurityPrescanBlocksBypass:
    """_security_prescan must raise SecurityError on escape primitives."""

    @pytest.mark.parametrize(
        "payload",
        [
            "import ctypes",
            "ctypes.CDLL('libc.so.6')",
            "import importlib; importlib.import_module('os')",
            "__import__('os').system('id')",
            "compile('import os')",
            "x = __loader__",
            "import sys; sys.modules['subprocess'].Popen('id')",
            "sys.modules['os'].system('id')",
            "m = sys . modules['socket']",
        ],
        ids=[
            "import-ctypes",
            "ctypes-use",
            "import-importlib",
            "dunder-import-os",
            "compile-use",
            "loader-dunder",
            "sys-modules-subprocess",
            "sys-modules-os",
            "sys-spaced-modules",
        ],
    )
    def test_prescan_refuses_bypass_primitives(self, payload):
        with pytest.raises(SecurityError):
            _security_prescan(payload)

    @pytest.mark.parametrize(
        "safe_code",
        [
            "print('hello world')",
            "import math\nprint(math.sqrt(2))",
            "from os import path\nprint(path.join('a', 'b'))",
            "x = [i for i in range(10)]\nprint(sum(x))",
            "import json\nprint(json.dumps({'a': 1}))",
        ],
        ids=["print", "math", "os-path", "listcomp", "json"],
    )
    def test_prescan_allows_safe_code(self, safe_code):
        # Must not raise.
        _security_prescan(safe_code)


# ── end-to-end execute() surfaces the guard as a tool error ─────────


class TestExecuteSurfacesGuard:
    """The execute() entrypoint must refuse ctypes/__import__('os') bypass."""

    @pytest.mark.asyncio
    async def test_execute_blocks_ctypes_bypass(self):
        from app.tools.python_sandbox import PythonSandboxTool

        tool = PythonSandboxTool()
        result = await tool.execute({"code": "__import__('os').system('id')"})

        assert result.success is False
        # Blocked either by the existing denylist pattern (__import__() is a
        # blocked pattern) or by the B23 security pre-scan — both satisfy the
        # requirement that the ctypes/__import__('os') bypass is refused.
        assert "not allowed" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_execute_blocks_sys_modules_probe(self):
        from app.tools.python_sandbox import PythonSandboxTool

        tool = PythonSandboxTool()
        result = await tool.execute({"code": "import sys; sys.modules['ctypes']"})

        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_blocks_loader_dunder_prescan(self):
        # __loader__ is NOT on the original denylist, so this proves the new
        # B23 pre-scan layer (not just the denylist) is what blocks it.
        from app.tools.python_sandbox import PythonSandboxTool

        tool = PythonSandboxTool()
        result = await tool.execute({"code": "loader = __loader__\nprint(loader)"})

        assert result.success is False
        assert "security pre-scan" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_execute_allows_benign_code(self):
        from app.tools.python_sandbox import PythonSandboxTool

        tool = PythonSandboxTool()
        result = await tool.execute({"code": "print(2 + 2)"})

        # Benign code is allowed (success depends on subprocess availability,
        # but it must not be blocked by the security prescan).
        assert "security pre-scan" not in (result.error or "").lower()


# ── existing denylist still enforced (regression guard) ────────────


class TestDenylistStillEnforced:
    """B23 must not remove the existing denylist — confirm it remains."""

    def test_denylist_blocks_subprocess_import(self):
        allowed, reason = _is_code_allowed("import subprocess")
        assert allowed is False
        assert "subprocess" in reason

    def test_denylist_blocks_compile_call(self):
        # compile( is a blocked function pattern even though `open(` is not.
        allowed, _reason = _is_code_allowed("compile('x = 1')")
        assert allowed is False
