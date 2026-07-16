#!/usr/bin/env python
"""CI regression guard: LLM router results must be failure-checked.

Background
----------
Every ``route_request`` / ``model_router.`` / ``llm_manager.`` call returns a
result that may represent *failure* (``success=False``) rather than empty
content. Historically several call sites read ``.get("response")`` directly and
silently swallowed the failure (or, on the object-returning router, raised
``AttributeError``). The correct pattern is to route the result through
``app.core.llm_result.normalize_llm_result`` (which raises ``LLMResultError``
on failure) or to check the ``success`` flag before reading content.

This script statically scans ``app/`` (excluding ``tests/``) and fails the
build if it finds a router result being read for *content* before it has been
guarded.

What counts as "guarded"
------------------------
A result variable ``r`` is considered guarded once, in the enclosing function,
any of these appear **before** the first content read::

    normalize_llm_result(r, ...)        # canonical guard (recommended)
    r.get("success")  /  r["success"]   # dict form
    r.success                          # object form
    if not r: ...                       # None guard

What counts as "content read" (the forbidden-until-guarded access)
---------------------------------------------------------------
    r.get("response") / r.get("content")
    r["response"] / r["content"]
    r.response / r.content
    json.loads(r)  when r is the bare router result

Usage
-----
    python scripts/guard_llm_success.py [paths ...]

Exit code 0 = clean, 1 = one or more violations.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Router call sites we care about. ONLY the LLM router entry point carries
# the success/error contract. (LangChain's model.ainvoke() returns a raw
# message with .content and no success flag, so it is intentionally excluded.)
ROUTER_CALL_ATTRS = {"route_request"}
# Bare attribute names whose direct call result must be guarded
# (e.g. ``model_router(...)`` / ``llm_manager(...)``) — rare, but covered.
ROUTER_VALUE_IDS = {"model_router", "llm_manager", "router", "llm_router"}

CONTENT_KEYS = {"response", "content", "choices", "message"}
GUARD_FUNCS = {"normalize_llm_result"}


class FunctionChecker(ast.NodeVisitor):
    """Per-function checker for unguarded router-result content reads."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []
        # name -> (guarded: bool)
        self.router_vars: dict[str, bool] = {}

    # ---- helpers -----------------------------------------------------------
    def _call_is_router(self, node: ast.Call) -> bool:
        func = node.func
        if isinstance(func, ast.Attribute):
            # model_router.route_request(...) / router.route_request(...)
            if func.attr in ROUTER_CALL_ATTRS:
                return True
            # model_router(...) / llm_manager(...)  (value is a bare id)
            return func.attr in ROUTER_VALUE_IDS
        return isinstance(func, ast.Name) and func.id in ROUTER_VALUE_IDS

    def _is_success_access(self, node: ast.AST, var: str) -> bool:
        # var.get("success") / var["success"] / var.success
        return (
            (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == var
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "success"
            )
            or (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == var
                and isinstance(node.slice, ast.Constant)
                and node.slice.value == "success"
            )
            or (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == var
                and node.attr == "success"
            )
        )

    def _accesses_var(self, node: ast.AST, var: str) -> bool:
        """True if *node* (or anything it contains) is the given router var."""
        return any(isinstance(sub, ast.Name) and sub.id == var for sub in ast.walk(node))

    def _is_content_access(self, node: ast.AST, var: str) -> bool:
        """True if *node* is a content read (response/content/...) on *var*."""
        # var.get("response" | "content" | ...)
        return (
            (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == var
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in CONTENT_KEYS
            )
            or (
                # var["response"] / var["content"]
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == var
                and isinstance(node.slice, ast.Constant)
                and node.slice.value in CONTENT_KEYS
            )
            or (
                # var.response / var.content  (bare attribute)
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == var
                and node.attr in CONTENT_KEYS
            )
        )

    def _is_guard_access(self, node: ast.AST, var: str) -> bool:
        """True if *node* is a success guard on *var*."""
        return self._is_success_access(node, var) or self._is_normalize_call(node, var)

    def _is_normalize_call(self, node: ast.AST, var: str) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in GUARD_FUNCS
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == var
        )

    # ---- visit -------------------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        # Detect:  var = await router.route_request(...)
        if (
            isinstance(node.value, ast.Await)
            and isinstance(node.value.value, ast.Call)
            and self._call_is_router(node.value.value)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            self.router_vars[node.targets[0].id] = False
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            isinstance(node.value, ast.Await)
            and isinstance(node.value.value, ast.Call)
            and self._call_is_router(node.value.value)
            and isinstance(node.target, ast.Name)
        ):
            self.router_vars[node.target.id] = False
        self.generic_visit(node)

    def _referenced_router_vars(self, node: ast.AST) -> list[str]:
        """Router-result vars directly referenced by *node* (as the value of a
        guard/content access)."""
        refs: list[str] = []
        for cand in (getattr(node, "func", None), getattr(node, "value", None)):
            if isinstance(cand, ast.Name) and cand.id in self.router_vars:
                refs.append(cand.id)
            elif (
                isinstance(cand, ast.Attribute)
                and isinstance(cand.value, ast.Name)
                and cand.value.id in self.router_vars
            ):
                refs.append(cand.value.id)
        return refs

    def visit_Call(self, node: ast.Call) -> None:
        for var in self._referenced_router_vars(node):
            if self._is_guard_access(node, var):
                self.router_vars[var] = True
            elif self._is_content_access(node, var) and not self.router_vars[var]:
                self.violations.append(
                    f"{self.filename}:{node.lineno}: router result "
                    f"'{var}' read for content before a success "
                    f"check / normalize_llm_result() guard"
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        for var in self._referenced_router_vars(node):
            if self._is_guard_access(node, var):
                self.router_vars[var] = True
            elif self._is_content_access(node, var) and not self.router_vars[var]:
                self.violations.append(
                    f"{self.filename}:{node.lineno}: router result "
                    f"'{var}' read for content before a success "
                    f"check / normalize_llm_result() guard"
                )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        for var in self._referenced_router_vars(node):
            if self._is_guard_access(node, var):
                self.router_vars[var] = True
            elif self._is_content_access(node, var) and not self.router_vars[var]:
                self.violations.append(
                    f"{self.filename}:{node.lineno}: router result "
                    f"'{var}' read for content before a success "
                    f"check / normalize_llm_result() guard"
                )
        self.generic_visit(node)


class ModuleChecker(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        checker = FunctionChecker(self.filename)
        checker.visit(node)
        self.violations.extend(checker.violations)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


def scan_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [f"{path}: syntax error: {exc}"]
    checker = ModuleChecker(str(path))
    checker.visit(tree)
    return checker.violations


def main(argv: list[str]) -> int:
    roots = [Path(p) for p in argv] if argv else [Path("app")]

    violations: list[str] = []
    files_scanned = 0
    for root in roots:
        if root.is_file():
            if root.suffix == ".py" and "tests" not in root.parts:
                files_scanned += 1
                violations.extend(scan_file(root))
        else:
            for path in sorted(root.rglob("*.py")):
                if "tests" in path.parts:
                    continue
                if path.name.startswith("."):
                    continue
                files_scanned += 1
                violations.extend(scan_file(path))

    if violations:
        print("❌ LLM failure-propagation guard FAILED:")
        for v in violations:
            print(f"  - {v}")
        print(
            f"\n{len(violations)} violation(s) across {files_scanned} file(s). "
            "Route router results through app.core.llm_result.normalize_llm_result() "
            "(or check .success) before reading content."
        )
        return 1

    print(f"✅ LLM failure-propagation guard passed ({files_scanned} file(s) scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
