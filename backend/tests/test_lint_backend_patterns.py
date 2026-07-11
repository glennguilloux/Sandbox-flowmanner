"""Self-test for the backend convention linter (``raise Exception`` gate).

Verifies both the positive path (bare ``raise Exception`` in
``app/services/`` is flagged) and the negative paths (MissionError-ish
subclasses, built-in ValueError/TypeError/KeyError, and test files are
NOT flagged).

These are pure unit tests over :func:`find_bare_exception_lines` plus one
end-to-end ``main()`` check, so they run with no backend dependencies.
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

# Ensure the backend root is importable so `scripts.lint_backend_patterns`
# resolves regardless of how pytest assembles sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lint_backend_patterns import (
    _in_services,
    _is_test_file,
    find_bare_exception_lines,
    main,
)

# --- fixtures: realistic source snippets --------------------------------


def _write(tmp_path, rel, content):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))
    return str(path)


SERVICE_BARE = """
    def send(self):
        if not self.conn:
            raise Exception("SMTP not connected")
        return self.conn.send()
"""

SERVICE_MISSION = """
    from app.services.mission_errors import MissionError

    def run(self):
        raise MissionError("boom")
"""

SERVICE_BUILTIN = """
    def validate(self, x):
        if x is None:
            raise ValueError("x required")
        if not isinstance(x, int):
            raise TypeError("x must be int")
        if x not in self.table:
            raise KeyError(x)
"""

COMMENTED = """
    # raise Exception("this is only a comment, not code")
    def noop(self):
        return None
"""

STRINGY = """
    def doc(self):
        msg = "do not raise Exception in a string"
        return msg
"""

NON_SERVICE_BARE = """
    def stuff(self):
        raise Exception("bare, but outside services -> allowed")
"""


# --- scope helpers -------------------------------------------------------


def test_is_test_file_variants():
    assert _is_test_file("/repo/backend/tests/test_foo.py")
    assert _is_test_file("/repo/backend/app/services/test_widget.py")
    assert _is_test_file("/repo/backend/tests/unit/test_foo.py")
    assert _is_test_file("/repo/backend/app/tests/conftest.py")
    assert _is_test_file("/repo/backend/tests/conftest.py")
    # negative
    assert not _is_test_file("/repo/backend/app/services/email_connector.py")
    assert not _is_test_file("/repo/backend/app/services/_internal.py")


def test_in_services_variant():
    assert _in_services("/repo/backend/app/services/connectors/email_connector.py")
    assert not _in_services("/repo/backend/app/api/_mission_cqrs/commands.py")
    assert not _in_services("/repo/backend/tests/test_foo.py")


# --- positive path: bare Exception in services is flagged ---------------


def test_flags_bare_exception_in_services(tmp_path):
    path = _write(tmp_path, "app/services/connectors/email_connector.py", SERVICE_BARE)
    lines = find_bare_exception_lines(path)
    assert lines == [4]  # 1-based line of the bare raise


def test_flags_multiple_sites(tmp_path):
    snippet = SERVICE_BARE + "\n" + SERVICE_BARE
    path = _write(tmp_path, "app/services/connectors/email_connector.py", snippet)
    lines = find_bare_exception_lines(path)
    assert lines == [4, 10]


# --- negative paths: allowed --------------------------------------------


def test_allows_mission_error_subclass(tmp_path):
    path = _write(tmp_path, "app/services/mission_executor.py", SERVICE_MISSION)
    assert find_bare_exception_lines(path) == []


def test_allows_builtin_validation_errors(tmp_path):
    path = _write(tmp_path, "app/services/widget_service.py", SERVICE_BUILTIN)
    assert find_bare_exception_lines(path) == []


def test_allows_commented_raise(tmp_path):
    path = _write(tmp_path, "app/services/foo.py", COMMENTED)
    assert find_bare_exception_lines(path) == []


def test_allows_string_containing_raise(tmp_path):
    path = _write(tmp_path, "app/services/foo.py", STRINGY)
    assert find_bare_exception_lines(path) == []


def test_allows_test_files_even_with_bare(tmp_path):
    path = _write(tmp_path, "tests/test_email_connector.py", SERVICE_BARE)
    assert find_bare_exception_lines(path) == []


def test_allows_files_outside_services(tmp_path):
    path = _write(tmp_path, "app/api/_mission_cqrs/commands.py", NON_SERVICE_BARE)
    assert find_bare_exception_lines(path) == []


# --- end-to-end main() ---------------------------------------------------


def test_main_exits_nonzero_on_flagged(tmp_path, capsys):
    path = _write(tmp_path, "app/services/connectors/email_connector.py", SERVICE_BARE)
    rc = main([path])
    assert rc == 1
    out = capsys.readouterr().out
    assert "FLAG" in out
    assert "email_connector.py:4" in out


def test_main_exits_zero_on_compliant(tmp_path, capsys):
    path = _write(tmp_path, "app/services/mission_executor.py", SERVICE_MISSION)
    rc = main([path])
    assert rc == 0
    assert "ok" in capsys.readouterr().out
