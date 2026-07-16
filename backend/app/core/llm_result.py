"""Shared normalization for LLM router results.

The backend has **two** different `route_request` implementations with two
different return shapes:

* ``app.services.model_router.ModelRouter.route_request`` -> ``dict`` with
  keys ``success`` / ``response`` / ``error``.
* ``app.services.llm_router.ModelRouter.route_request`` -> an
  ``LLMRouteResult`` **dataclass** when the router holds a DB session, or a
  plain ``dict`` when it does not.

Historically several call sites read ``response.get("response")`` directly and
silently swallowed a ``success=False`` (the LLM "succeeded" but returned an
error payload). Others broke entirely on the object-returning router because
the dataclass has no ``.get()``.

This module is the single choke point that:
  * accepts **both** return shapes (dict or object with ``success``/
    ``content``/``response``/``error`` attributes),
  * raises :class:`LLMResultError` when the call failed, and
  * returns the content string otherwise.

Callers should do::

    resp = await router.route_request(...)
    content = normalize_llm_result(resp)   # raises LLMResultError on failure
    # ... now safe to parse `content`

This keeps the failure-propagation contract uniform regardless of which
router a service happens to use.
"""

from __future__ import annotations

from typing import Any


class LLMResultError(Exception):
    """Raised when an LLM router call returns success=False.

    Carries the underlying router error message so call sites can log/surface
    it instead of silently returning empty output.
    """

    def __init__(self, message: str = "llm call failed", *, error: str | None = None) -> None:
        self.llm_error = error or message
        super().__init__(self.llm_error)


def _has_attr(obj: Any, name: str) -> bool:
    return hasattr(obj, name) and getattr(obj, name) is not None


def llm_result_ok(result: Any) -> bool:
    """Return True if *result* represents a successful LLM call (any shape)."""
    if result is None:
        return False
    if isinstance(result, dict):
        return bool(result.get("success", False))
    # Object form (LLMRouteResult): prefer the ``success`` attribute.
    if _has_attr(result, "success"):
        return bool(result.success)
    # Tolerate a dict-like object that only exposes ``content``.
    return bool(_has_attr(result, "content"))


def llm_result_error(result: Any) -> str:
    """Return the error message from a failed LLM result (any shape)."""
    if isinstance(result, dict):
        return result.get("error") or "llm call failed"
    if _has_attr(result, "error"):
        return result.error or "llm call failed"
    return "llm call failed"


def llm_result_content(result: Any) -> str:
    """Return the content string from an LLM result (any shape)."""
    if isinstance(result, dict):
        return result.get("response") or result.get("content") or ""
    if _has_attr(result, "content"):
        return result.content or ""
    if _has_attr(result, "response"):
        return result.response or ""
    return ""


def normalize_llm_result(result: Any, *, context: str = "") -> str:
    """Normalize an LLM router result and return its content string.

    Raises:
        LLMResultError: if *result* indicates failure or is ``None``.

    Works for both the dict-returning and object-returning routers, so a
    caller never has to special-case the shape or risk an AttributeError on a
    ``success=False`` payload.
    """
    if result is None:
        raise LLMResultError("llm call returned no result")

    if not llm_result_ok(result):
        msg = llm_result_error(result)
        prefix = f"{context}: " if context else ""
        raise LLMResultError(f"{prefix}{msg}")

    return llm_result_content(result)
