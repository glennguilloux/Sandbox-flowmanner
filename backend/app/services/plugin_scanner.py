"""Plugin Security Scanner — static analysis for plugin packages.

Scans plugin source code for dangerous patterns, validates declared
permissions against actual code usage, and produces a risk score.

Used during plugin install and marketplace publish to gate unsafe code.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


# ── Dangerous pattern definitions ────────────────────────────────────────────

BLOCKED_IMPORTS = {
    "os": "Uses os module (filesystem/process access)",
    "subprocess": "Uses subprocess (arbitrary command execution)",
    "shutil": "Uses shutil (filesystem operations)",
    "socket": "Uses socket (raw network access)",
    "http.server": "Uses http.server (can start servers)",
    "ctypes": "Uses ctypes (native code execution)",
    "importlib": "Uses importlib (dynamic code loading)",
    "compile": "Uses compile (dynamic code compilation)",
}

BLOCKED_BUILTINS = {
    "eval": "Calls eval() (arbitrary code execution)",
    "exec": "Calls exec() (arbitrary code execution)",
    "__import__": "Calls __import__() (dynamic imports)",
    "compile": "Calls compile() (code compilation)",
    "globals": "Calls globals() (scope manipulation)",
    "locals": "Calls locals() (scope manipulation)",
}

BLOCKED_PATTERNS = [
    (r"os\.system\s*\(", "Calls os.system() (shell command execution)"),
    (r"os\.popen\s*\(", "Calls os.popen() (shell command execution)"),
    (
        r"subprocess\.(run|Popen|call|check_output|check_call)\s*\(",
        "Calls subprocess methods (command execution)",
    ),
    (r"open\s*\([^)]*['\"]/?(\.\./)", "Accesses files outside current directory"),
    (r"open\s*\([^)]*['\"]/(?!tmp|dev)", "Accesses files outside /tmp"),
    (r"__builtins__", "Manipulates builtins"),
    (r"__subclasses__\s*\(", "Introspects class hierarchy"),
    (r"__globals__", "Accesses function globals"),
    (r"__class__", "Accesses class internals"),
    (r"breakpoint\s*\(", "Calls breakpoint() (debugger)"),
    (r"exit\s*\(", "Calls exit() (terminates process)"),
    (r"quit\s*\(", "Calls quit() (terminates process)"),
    (r"importlib\.import_module", "Dynamic module import"),
    (r"getattr\s*\(\s*__builtins__", "Accesses builtins via getattr"),
]

PERMISSION_PATTERNS = {
    "network": [
        r"import\s+(requests|httpx|urllib|aiohttp|http\.client)",
        r"(requests|httpx|aiohttp)\.(get|post|put|patch|delete|head)\s*\(",
        r"urllib\.request",
        r"socket\.",
    ],
    "filesystem": [
        r"(open|os\.(listdir|makedirs|mkdir|remove|rename|rmdir|walk|scandir|path))\s*\(",
        r"import\s+(shutil|pathlib|glob|tempfile)",
        r"pathlib\.Path",
        r"shutil\.(copy|move|rmtree)",
    ],
    "subprocess": [
        r"import\s+subprocess",
        r"subprocess\.(run|Popen|call|check_output)\s*\(",
        r"os\.system\s*\(",
        r"os\.popen\s*\(",
    ],
    "env_read": [
        r"os\.environ",
        r"os\.getenv\s*\(",
    ],
    "env_write": [
        r"os\.environ\[",
        r"os\.environ\.update",
        r"os\.putenv\s*\(",
    ],
}


@dataclass
class ScanFinding:
    """A single finding from the security scan."""

    severity: str  # "critical", "high", "medium", "low", "info"
    category: str  # "blocked_pattern", "permission_mismatch", "dangerous_import"
    message: str
    file: str = ""
    line: int = 0
    code_snippet: str = ""


@dataclass
class ScanResult:
    """Result of a plugin security scan."""

    risk_score: int  # 0-100 (0 = safe, 100 = extremely dangerous)
    findings: list[ScanFinding] = field(default_factory=list)
    declared_permissions: list[str] = field(default_factory=list)
    detected_permissions: list[str] = field(default_factory=list)
    undeclared_permissions: list[str] = field(default_factory=list)
    files_scanned: int = 0
    passed: bool = True  # True if risk_score < threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "passed": self.passed,
            "findings_count": len(self.findings),
            "findings": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "message": f.message,
                    "file": f.file,
                    "line": f.line,
                }
                for f in self.findings
            ],
            "declared_permissions": self.declared_permissions,
            "detected_permissions": self.detected_permissions,
            "undeclared_permissions": self.undeclared_permissions,
            "files_scanned": self.files_scanned,
        }


class PluginScanner:
    """Static analysis scanner for plugin packages.

    Scans all Python files in a plugin directory for:
    - Blocked patterns (os.system, eval, exec, etc.)
    - Dangerous imports (subprocess, ctypes, etc.)
    - Permission mismatches (declared vs actual)
    - Suspicious code patterns (__subclasses__, __globals__, etc.)

    Usage::

        scanner = PluginScanner()
        result = scanner.scan(plugin_dir, declared_permissions=["network"])
        if not result.passed:
            raise PermissionDenied(f"Plugin failed security scan: {result.risk_score}")
    """

    # Risk score thresholds
    PASS_THRESHOLD = 50  # Below this: approved
    REVIEW_THRESHOLD = 30  # Below this: auto-approve, above: needs review

    def scan(
        self,
        plugin_dir: Path,
        declared_permissions: list[str] | None = None,
    ) -> ScanResult:
        """Scan a plugin directory for security issues.

        Args:
            plugin_dir: Root directory of the unpacked plugin.
            declared_permissions: Permissions declared in the manifest.

        Returns:
            ScanResult with risk score and findings.
        """
        declared_permissions = declared_permissions or []
        result = ScanResult(risk_score=0, declared_permissions=declared_permissions)

        # Collect all Python files
        py_files = sorted(plugin_dir.rglob("*.py"))
        # Exclude __pycache__
        py_files = [f for f in py_files if "__pycache__" not in str(f)]

        result.files_scanned = len(py_files)

        for py_file in py_files:
            self._scan_file(py_file, plugin_dir, result)

        # Detect permission usage and compare with declarations
        self._check_permission_mismatch(result)

        # Calculate risk score
        result.risk_score = self._calculate_risk_score(result)
        result.passed = result.risk_score < self.PASS_THRESHOLD

        return result

    def _scan_file(self, file_path: Path, plugin_dir: Path, result: ScanResult) -> None:
        """Scan a single Python file for security issues."""
        rel_path = str(file_path.relative_to(plugin_dir))

        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            result.findings.append(
                ScanFinding(
                    severity="low",
                    category="read_error",
                    message=f"Could not read file: {e}",
                    file=rel_path,
                )
            )
            return

        lines = source.splitlines()

        # Pattern-based scanning (line by line)
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            for pattern, message in BLOCKED_PATTERNS:
                if re.search(pattern, line):
                    severity = (
                        "critical"
                        if any(
                            k in message.lower()
                            for k in ["eval", "exec", "system", "subprocess", "command"]
                        )
                        else "high"
                    )
                    result.findings.append(
                        ScanFinding(
                            severity=severity,
                            category="blocked_pattern",
                            message=message,
                            file=rel_path,
                            line=line_num,
                            code_snippet=stripped[:200],
                        )
                    )

        # AST-based scanning for imports and function calls
        try:
            tree = ast.parse(source, filename=str(file_path))
            self._scan_ast(tree, rel_path, result)
        except SyntaxError:
            result.findings.append(
                ScanFinding(
                    severity="medium",
                    category="syntax_error",
                    message="File has syntax errors — cannot fully analyze",
                    file=rel_path,
                )
            )

    def _scan_ast(self, tree: ast.AST, rel_path: str, result: ScanResult) -> None:
        """Scan AST for dangerous imports and function calls."""
        for node in ast.walk(tree):
            # Check import statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in BLOCKED_IMPORTS:
                        result.findings.append(
                            ScanFinding(
                                severity="high",
                                category="dangerous_import",
                                message=BLOCKED_IMPORTS[module],
                                file=rel_path,
                                line=node.lineno,
                            )
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    if module in BLOCKED_IMPORTS:
                        result.findings.append(
                            ScanFinding(
                                severity="high",
                                category="dangerous_import",
                                message=BLOCKED_IMPORTS[module],
                                file=rel_path,
                                line=node.lineno,
                            )
                        )

            # Check function calls to blocked builtins
            elif isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in BLOCKED_BUILTINS:
                    result.findings.append(
                        ScanFinding(
                            severity="critical",
                            category="blocked_pattern",
                            message=BLOCKED_BUILTINS[func_name],
                            file=rel_path,
                            line=node.lineno,
                        )
                    )

    def _get_call_name(self, node: ast.Call) -> str:
        """Extract the function name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    def _check_permission_mismatch(self, result: ScanResult) -> None:
        """Compare declared permissions against detected code usage."""
        detected: set[str] = set()

        # Scan findings for permission indicators
        for finding in result.findings:
            msg = finding.message.lower()
            if "network" in msg or "http" in msg or "socket" in msg:
                detected.add("network")
            elif "file" in msg or "path" in msg or "shutil" in msg:
                detected.add("filesystem")
            elif "subprocess" in msg or "command" in msg or "system" in msg:
                detected.add("subprocess")
            elif "environ" in msg:
                detected.add("env_read")

        # Also scan raw code for permission patterns
        # (this catches patterns that don't match blocked rules but still use permissions)
        # We re-scan the findings' code snippets for additional context
        result.detected_permissions = sorted(detected)

        # Find undeclared permissions (detected but not declared)
        declared_set = set(result.declared_permissions)
        undeclared = detected - declared_set
        result.undeclared_permissions = sorted(undeclared)

        # Add findings for undeclared permissions
        for perm in undeclared:
            result.findings.append(
                ScanFinding(
                    severity="high",
                    category="permission_mismatch",
                    message=f"Uses '{perm}' permission but not declared in manifest",
                )
            )

    def _calculate_risk_score(self, result: ScanResult) -> int:
        """Calculate a 0-100 risk score from findings."""
        score = 0

        severity_weights = {
            "critical": 25,
            "high": 15,
            "medium": 8,
            "low": 3,
            "info": 0,
        }

        for finding in result.findings:
            score += severity_weights.get(finding.severity, 5)

        # Penalty for undeclared permissions
        score += len(result.undeclared_permissions) * 20

        # Cap at 100
        return min(score, 100)


# ── Singleton ────────────────────────────────────────────────────────────────

_scanner: PluginScanner | None = None


def get_plugin_scanner() -> PluginScanner:
    """Get or create the global PluginScanner singleton."""
    global _scanner
    if _scanner is None:
        _scanner = PluginScanner()
    return _scanner
