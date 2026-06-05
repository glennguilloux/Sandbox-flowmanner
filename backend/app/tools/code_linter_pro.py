"""
Code Execution & Development Tools — Code Linter Pro.

code_linter_pro → Automatically detect and fix syntax errors in generated
    code snippets with language-specific linting and suggestions.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile

from pydantic import Field

from app.tools._rlimits import make_preexec_fn
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Resource limits for subprocess lint tools ─────────────────────

LINTER_MEMORY_MB = int(os.getenv("LINTER_MEMORY_MB", "128"))
LINTER_MAX_PROCS = int(os.getenv("LINTER_MAX_PROCS", "0"))  # 0 = block fork

# ── Input ─────────────────────────────────────────────────────────────

class CodeLinterProInput(ToolInput):
    code: str = Field(
        ...,
        min_length=1,
        description="Source code to lint and analyze",
    )
    language: str = Field(
        "python",
        description="Programming language: 'python', 'javascript', 'typescript', 'bash', 'sql', 'html', 'css'",
    )
    fix: bool = Field(
        False,
        description="Attempt to auto-fix common issues",
    )


# ── Tool ──────────────────────────────────────────────────────────────

class CodeLinterProTool(BaseTool):
    """Multi-language code linter with auto-fix suggestions."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="code_linter_pro",
            name="Code Linter Pro",
            description=(
                "Automatically detect and fix syntax errors in generated code "
                "snippets. Supports Python, JavaScript, TypeScript, Bash, SQL, "
                "HTML, and CSS."
            ),
            category="code-execution-and-development",
            input_schema=CodeLinterProInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["code", "linting", "syntax", "fix", "differentiator"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = CodeLinterProInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        lang = validated.language.lower()
        code = validated.code
        do_fix = validated.fix

        try:
            if lang in ("python", "py"):
                issues, score, fixed_code, summary = await self._lint_python(code, do_fix)
            elif lang in ("javascript", "js"):
                issues, score, fixed_code, summary = await self._lint_javascript(code, do_fix)
            elif lang in ("typescript", "ts"):
                issues, score, fixed_code, summary = await self._lint_typescript(code, do_fix)
            elif lang in ("bash", "sh", "shell"):
                issues, score, fixed_code, summary = await self._lint_bash(code, do_fix)
            elif lang in ("sql"):
                issues, score, fixed_code, summary = await self._lint_sql(code, do_fix)
            elif lang in ("html"):
                issues, score, fixed_code, summary = await self._lint_html(code, do_fix)
            elif lang in ("css"):
                issues, score, fixed_code, summary = await self._lint_css(code, do_fix)
            else:
                # Generic: try all basic checks
                issues, score, fixed_code, summary = await self._lint_generic(code, lang, do_fix)

            result = {
                "language": lang,
                "issues": issues,
                "issue_count": len(issues),
                "score": score,
                "summary": summary,
            }
            if do_fix:
                result["fixed_code"] = fixed_code
                result["changes_made"] = fixed_code != code

            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("code_linter_pro failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── Python linter ────────────────────────────────────────────

    async def _lint_python(self, code: str, fix: bool) -> tuple[list, int, str, str]:
        """Lint Python code using ast and basic heuristics."""
        issues = []
        fixed_code = code

        # Check syntax via ast.parse
        try:
            import ast
            ast.parse(code)
        except SyntaxError as e:
            issues.append({
                "line": e.lineno or 1,
                "column": e.offset or 0,
                "severity": "error",
                "message": f"Syntax error: {e.msg}",
                "code_snippet": (e.text or "").strip() if e.text else "",
                "suggestion": self._python_syntax_suggestion(e),
                "fixable": False,
            })

        # Check indentation consistency (mixed tabs/spaces)
        if "\t" in code and "    " in code:
            issues.append({
                "line": 1,
                "column": 0,
                "severity": "warning",
                "message": "Mixed tabs and spaces — use only spaces (PEP 8)",
                "code_snippet": "",
                "suggestion": "Replace all tabs with 4 spaces",
                "fixable": True,
            })
            if fix:
                fixed_code = fixed_code.replace("\t", "    ")

        # Check line length (PEP 8)
        long_lines = [
            (i + 1, line) for i, line in enumerate(code.splitlines())
            if len(line) > 100
        ]
        if long_lines:
            for lineno, line in long_lines[:5]:
                issues.append({
                    "line": lineno,
                    "column": 100,
                    "severity": "info",
                    "message": f"Line too long ({len(line)} > 100 chars)",
                    "code_snippet": line[:80] + "...",
                    "suggestion": "Break into multiple lines",
                    "fixable": False,
                })
            if len(long_lines) > 5:
                issues.append({
                    "line": 0,
                    "column": 0,
                    "severity": "info",
                    "message": f"... and {len(long_lines) - 5} more long lines",
                    "code_snippet": "",
                    "suggestion": "",
                    "fixable": False,
                })

        # Check trailing whitespace
        trailing_lines = [
            i + 1 for i, line in enumerate(code.splitlines())
            if line.rstrip() != line
        ]
        if trailing_lines:
            issues.append({
                "line": trailing_lines[0],
                "column": 0,
                "severity": "info",
                "message": f"Trailing whitespace on {len(trailing_lines)} line(s)",
                "code_snippet": "",
                "suggestion": "Remove trailing whitespace",
                "fixable": True,
            })
            if fix:
                fixed_code = "\n".join(line.rstrip() for line in fixed_code.splitlines())

        # Check missing newline at end of file
        if code and not code.endswith("\n"):
            issues.append({
                "line": len(code.splitlines()),
                "column": 0,
                "severity": "info",
                "message": "Missing newline at end of file (PEP 8)",
                "code_snippet": "",
                "suggestion": "Add a newline at end of file",
                "fixable": True,
            })
            if fix:
                fixed_code += "\n"

        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score, "Python")
        return issues, score, fixed_code, summary

    def _python_syntax_suggestion(self, e: SyntaxError) -> str:
        """Generate a human-readable suggestion for common Python syntax errors."""
        msg = str(e.msg).lower()
        if "unexpected eof" in msg or "unexpected end" in msg:
            return "Check for missing closing parenthesis, bracket, or quote"
        if "invalid syntax" in msg:
            return "Check for missing colon (:), incorrect indentation, or unmatched brackets"
        if "indentation" in msg:
            return "Ensure consistent indentation (4 spaces per level)"
        return "Review the syntax at the indicated line"

    # ── JavaScript linter ────────────────────────────────────────

    async def _lint_javascript(self, code: str, fix: bool) -> tuple[list, int, str, str]:
        """Lint JavaScript code using syntax check via Node.js."""
        issues = []

        # Try Node.js syntax check
        fixed_code = code
        try:
            result = subprocess.run(
                ["node", "--check", "-"],
                input=code,
                capture_output=True,
                text=True,
                timeout=10,
                preexec_fn=make_preexec_fn(
                    memory_mb=LINTER_MEMORY_MB,
                    max_procs=LINTER_MAX_PROCS,
                    cpu_seconds=10,
                ),
            )
            if result.returncode != 0:
                issues.append({
                    "line": 1,
                    "column": 0,
                    "severity": "error",
                    "message": f"Syntax error: {result.stderr.strip()}",
                    "code_snippet": "",
                    "suggestion": "Fix the reported syntax error",
                    "fixable": False,
                })
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # Node.js not available — skip syntax check

        # Common JS patterns
        issues.extend(self._generic_checks(code, "javascript"))
        if fix:
            fixed_code = self._fix_generic(code, "javascript")

        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score, "JavaScript")
        return issues, score, fixed_code, summary

    # ── TypeScript linter ────────────────────────────────────────

    async def _lint_typescript(self, code: str, fix: bool) -> tuple[list, int, str, str]:
        """Lint TypeScript code."""
        issues = []
        fixed_code = code

        # Basic TS rules: check for common mistakes
        issues.extend(self._generic_checks(code, "typescript"))

        if fix:
            fixed_code = self._fix_generic(code, "typescript")

        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score, "TypeScript")
        return issues, score, fixed_code, summary

    # ── Bash linter ──────────────────────────────────────────────

    async def _lint_bash(self, code: str, fix: bool) -> tuple[list, int, str, str]:
        """Lint Bash code."""
        issues = []
        fixed_code = code

        # ShellCheck if available
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(code)
            result = subprocess.run(
                ["shellcheck", "--format=json", tmp_path],
                capture_output=True,
                text=True,
                timeout=10,
                preexec_fn=make_preexec_fn(
                    memory_mb=LINTER_MEMORY_MB,
                    max_procs=LINTER_MAX_PROCS,
                    cpu_seconds=10,
                ),
            )
            if result.returncode == 0 and result.stdout.strip():
                shell_issues = json.loads(result.stdout)
                for si in shell_issues:
                    issues.append({
                        "line": si.get("line", 1),
                        "column": si.get("column", 0),
                        "severity": si.get("level", "warning"),
                        "message": si.get("message", ""),
                        "code_snippet": "",
                        "suggestion": si.get("fix", {}).get("replacements", [{}])[0].get("replacement", "") if si.get("fix") else "",
                        "fixable": bool(si.get("fix")),
                    })
            os.unlink(tmp_path)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # shellcheck not available

        # Basic checks
        issues.extend(self._generic_checks(code, "bash"))
        if fix:
            fixed_code = self._fix_generic(code, "bash")

        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score, "Bash")
        return issues, score, fixed_code, summary

    # ── SQL linter ───────────────────────────────────────────────

    async def _lint_sql(self, code: str, fix: bool) -> tuple[list, int, str, str]:
        """Lint SQL code."""
        issues = []
        fixed_code = code

        # Keyword casing — flag lowercase keywords
        sql_keywords = [
            "select", "from", "where", "insert", "update", "delete",
            "create", "alter", "drop", "join", "left", "right", "inner",
            "outer", "on", "and", "or", "not", "in", "like", "between",
            "group by", "order by", "having", "limit", "offset",
            "set", "values", "into", "table", "index", "view",
        ]
        for kw in sql_keywords:
            if re.search(rf'\b{kw}\b', code):
                issues.append({
                    "line": 1,
                    "column": 0,
                    "severity": "style",
                    "message": f"Use uppercase for SQL keyword: {kw.upper()}",
                    "code_snippet": "",
                    "suggestion": f"Change '{kw}' to '{kw.upper()}'",
                    "fixable": True,
                })
                if fix:
                    fixed_code = re.sub(
                        rf'\b{kw}\b', kw.upper(), fixed_code, flags=re.IGNORECASE,
                    )

        issues.extend(self._generic_checks(code, "sql"))
        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score, "SQL")
        return issues, score, fixed_code, summary

    # ── HTML linter ──────────────────────────────────────────────

    async def _lint_html(self, code: str, fix: bool) -> tuple[list, int, str, str]:
        """Lint HTML code for common issues."""
        issues = []
        fixed_code = code

        # Check for unclosed tags
        tags = re.findall(r'</?(\w+)', code)
        tag_counts: dict[str, int] = {}
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Count opens vs closes
        open_counts: dict[str, int] = {}
        close_counts: dict[str, int] = {}
        for m in re.finditer(r'<(\w+)', code):
            open_counts[m.group(1)] = open_counts.get(m.group(1), 0) + 1
        for m in re.finditer(r'</(\w+)', code):
            close_counts[m.group(1)] = close_counts.get(m.group(1), 0) + 1

        void_elements = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
        for tag_name, count in open_counts.items():
            if tag_name in void_elements:
                continue
            closes = close_counts.get(tag_name, 0)
            if count > closes:
                issues.append({
                    "line": 1, "column": 0,
                    "severity": "warning",
                    "message": f"Unclosed <{tag_name}> tag ({count} open, {closes} close)",
                    "code_snippet": "",
                    "suggestion": f"Add closing </{tag_name}> tag(s)",
                    "fixable": False,
                })

        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score, "HTML")
        return issues, score, fixed_code, summary

    # ── CSS linter ───────────────────────────────────────────────

    async def _lint_css(self, code: str, fix: bool) -> tuple[list, int, str, str]:
        """Lint CSS code."""
        issues = []
        fixed_code = code

        # Check for missing semicolons
        lines = code.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped and not stripped.endswith("{") and not stripped.endswith("}") and not stripped.endswith(";") and not stripped.endswith(","):
                if ":" in stripped and not stripped.startswith("@"):
                    issues.append({
                        "line": i, "column": len(stripped),
                        "severity": "warning",
                        "message": "Missing semicolon after property",
                        "code_snippet": stripped[:80],
                        "suggestion": f"Add ';' at end: {stripped};",
                        "fixable": True,
                    })
                    if fix:
                        lines[i - 1] = line.rstrip() + ";"

        if fix:
            fixed_code = "\n".join(lines)

        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score, "CSS")
        return issues, score, fixed_code, summary

    # ── Generic linter ───────────────────────────────────────────

    async def _lint_generic(self, code: str, lang: str, fix: bool) -> tuple[list, int, str, str]:
        """Generic linting for unrecognized languages."""
        issues = self._generic_checks(code, lang)
        fixed_code = self._fix_generic(code, lang) if fix else code
        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score, lang)
        return issues, score, fixed_code, summary

    def _generic_checks(self, code: str, lang: str) -> list[dict]:
        """Run generic code quality checks applicable to any language."""
        issues = []

        # Count brackets/parens
        brackets = {"(": ")", "[": "]", "{": "}"}
        for opening, closing in brackets.items():
            open_count = code.count(opening)
            close_count = code.count(closing)
            if open_count != close_count:
                issues.append({
                    "line": 1, "column": 0,
                    "severity": "warning",
                    "message": f"Unmatched {opening}{closing}: {open_count} open, {close_count} close",
                    "code_snippet": "",
                    "suggestion": f"Check for missing {closing} or {opening}",
                    "fixable": False,
                })

        # Check for empty file
        if not code.strip():
            issues.append({
                "line": 1, "column": 0,
                "severity": "info",
                "message": "File is empty",
                "code_snippet": "",
                "suggestion": "",
                "fixable": False,
            })

        return issues

    def _fix_generic(self, code: str, lang: str) -> str:
        """Apply generic fixes."""
        fixed = code

        # Ensure newline at end of file
        if fixed and not fixed.endswith("\n"):
            fixed += "\n"

        return fixed

    # ── Scoring ──────────────────────────────────────────────────

    def _calculate_score(self, issues: list[dict]) -> float:
        """Calculate a 0-100 code quality score from issues."""
        if not issues:
            return 100.0

        severity_weights = {
            "error": 15,
            "warning": 5,
            "style": 2,
            "info": 1,
        }

        penalty = sum(
            severity_weights.get(issue.get("severity", "info"), 1)
            for issue in issues
        )
        return max(0.0, round(100.0 - penalty, 1))

    def _build_summary(self, issues: list[dict], score: float, lang: str) -> str:
        """Build a human-readable lint summary."""
        error_count = sum(1 for i in issues if i["severity"] == "error")
        warn_count = sum(1 for i in issues if i["severity"] == "warning")
        info_count = len(issues) - error_count - warn_count

        parts = [f"{lang} lint score: {score}/100"]
        if error_count:
            parts.append(f"{error_count} error(s)")
        if warn_count:
            parts.append(f"{warn_count} warning(s)")
        if info_count:
            parts.append(f"{info_count} info(s)")

        if not issues:
            parts.append("— no issues found")

        return ", ".join(parts)


# ── Register ──────────────────────────────────────────────────────────

register_tool(CodeLinterProTool())
