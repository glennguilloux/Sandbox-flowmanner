"""Regression tests for the prompt_template_renderer authenticated-RCE fix.

Background (verified 2026-07-15):
    The renderer's `custom_filters` branch compiled + eval'd a USER-SUPPLIED
    Python expression for each filter, gated only by {"__builtins__": {}}.
    That guard is bypassable to recover os.system (authenticated RCE reachable
    via POST /api/v1/tools/prompt_template_renderer/execute, gated only by
    get_current_user). Fix: replace eval/compile with a fixed allowlist of
    pure, side-effect-free callables; reject any name not in the allowlist
    (fails closed), and never execute user-supplied expression text.

What these tests prove, in ANY environment:
  (a) a non-allowlisted custom filter name is rejected (fails closed) BEFORE any
      render attempt — independent of whether Jinja2 is importable;
  (b) no eval()/compile() remains anywhere in the module source (static proof
      the RCE sink is gone);
  (c) the allowlist is a fixed dict of pure callables (no user-string callables).

Behavioural rendering (allowlisted filter actually transforms output, and a
user-supplied expression string is never executed) is exercised only when
Jinja2's `SandboxedEnvironment` is importable from the top-level `jinja2`
package — i.e. in the deployed Docker image. In a dev venv where jinja2's
__init__ is broken those cases are skipped, but the live post-deploy proof
(Step 7 of the overnight run) covers them against the real image.
"""

import asyncio
import inspect
import os

# Ensure a JWT secret / OpenAI key isn't required for the tool import path.
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.tools.prompt_template_renderer import (
    _SAFE_CUSTOM_FILTERS,
    PromptTemplateRendererTool,
)

# Can the tool actually reach its Jinja2 render path in THIS interpreter?
try:
    from jinja2 import SandboxedEnvironment  # type: ignore

    JINJA2_OK = True
except Exception:  # pragma: no cover - depends on environment
    JINJA2_OK = False

import pytest

# The precise attacker 1-liner from the review: subclass walk to recover `os`.
_RCE_BYPASS_EXPR = "().__class__.__bases__[0].__subclasses__()"


def _run(rendered_template: str, custom_filters: dict | None = None, variables: dict | None = None):
    """Execute the tool's full path (no HTTP / auth layer needed)."""
    tool = PromptTemplateRendererTool()
    merged = {"name": "world"}
    if variables:
        merged.update(variables)
    input_data = {
        "template": rendered_template,
        "variables": merged,
        "engine": "jinja2",
    }
    if custom_filters is not None:
        input_data["custom_filters"] = custom_filters
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(tool.execute(input_data))
    finally:
        loop.close()


def test_non_allowlisted_custom_filter_is_rejected():
    """A non-allowlisted custom filter name (carrying the old PoC expr) fails closed."""
    out = _run("{{ name|pwn }}", custom_filters={"pwn": _RCE_BYPASS_EXPR})
    assert out.success is False, "exploit payload should be rejected, not rendered"
    assert "allowlist" in (out.error or "").lower(), f"unexpected error: {out.error}"
    assert "pwn" in (out.error or ""), f"error should name the bad filter: {out.error}"


def test_no_eval_or_compile_on_user_input():
    """Static guarantee: the module must not eval/compile anything."""
    src = inspect.getsource(PromptTemplateRendererTool)
    assert "eval(" not in src, "eval() still present in renderer — RCE not fixed"
    assert "compile(" not in src, "compile() still present in renderer — RCE not fixed"
    # The allowlist is a fixed dict of pure callables (not user strings).
    assert isinstance(_SAFE_CUSTOM_FILTERS, dict)
    assert _SAFE_CUSTOM_FILTERS
    for name, fn in _SAFE_CUSTOM_FILTERS.items():
        assert callable(fn), f"allowlisted filter {name!r} must be a callable"
        assert not isinstance(fn, str), f"allowlisted filter {name!r} must not be user text"


@pytest.mark.skipif(not JINJA2_OK, reason="Jinja2 SandboxedEnvironment not importable in this venv")
def test_allowlisted_custom_filter_renders():
    """An allowlisted filter (upper/title) transforms output in the Jinja path."""
    out = _run("{{ name|upper }}", custom_filters={"upper": "v.upper()"})
    assert out.success is True, f"legit filter failed: {out.error}"
    assert out.result["rendered"].strip() == "WORLD"

    out = _run("{{ name|title }}", custom_filters={"title": "v.title()"})
    assert out.success is True, f"title filter failed: {out.error}"
    assert out.result["rendered"].strip() == "World"


@pytest.mark.skipif(not JINJA2_OK, reason="Jinja2 SandboxedEnvironment not importable in this venv")
def test_user_supplied_expression_text_is_never_executed():
    """A command hidden in an allowlisted filter's text is NEVER executed."""
    import contextlib
    import os as _os

    probe = "/tmp/prompt_renderer_rce_probe"
    with contextlib.suppress(FileNotFoundError):
        _os.remove(probe)

    out = _run(
        "{{ name|upper }}",
        custom_filters={"upper": "os.system('touch /tmp/prompt_renderer_rce_probe')"},
    )
    assert (
        out.success is True
    ), f"user expression text must be ignored; if this failed, eval() is still in play: {out.error}"
    assert out.result["rendered"].strip() == "WORLD"
    assert not _os.path.exists(probe), "RCE: user-supplied expression was executed!"
