"""Q6-B — Second-pass verifier (cross-model-family independent check).

Q6-A is a *lexical* groundedness check: cheap, deterministic, no LLM.  It
catches the common case (claim text appears verbatim in the transcript)
but it cannot judge *semantic* support — e.g. a claim that paraphrases or
infers from the transcript.  That is exactly where an over-confident
reviewer hallucinates.

Q6-B adds a **second-pass verifier** with two properties that make it a
strong independent check:

* **Different model family** than the primary reviewer, so their failure
  modes are *decorrelated*.  A ``deepseek`` reviewer's confident
  hallucination is far less likely to be mirrored by an ``anthropic`` or
  local-model verifier (and vice-versa).  We take the verifier's model
  from a *different* family than the reviewer's model id.
* **Narrow task**: given ``(transcript, claim)`` it answers a single
  binary question — *"does the transcript support this claim? yes/no"* —
  plus an evidence span quote.  Narrow tasks are reliably solvable by
  cheap models, so this is *cheaper* than a second expensive reviewer and
  statistically independent of the first pass.

The verifier returns a :class:`VerificationResult`.  Q6-E composes Q6-A
(lexical) and Q6-B (semantic): a claim passes only if it is *both* grounded
(lexically or via the verifier) *and* not contradicted by the verifier.

Like Q6-A, this module is pure logic: it defines the prompt + the result
shape and a *callable* injection point for the LLM.  It does NOT call the
LLM directly — the orchestrator (Q6-E) or a test injects a
``call_llm(messages) -> str`` callable (mirroring the critic's
``get_budget_enforcer`` late-binding pattern).  That keeps the guard
testable without network access and lets the production path route through
``BudgetEnforcer`` (project rule: the LLM path goes through the enforcer,
never ``httpx`` directly).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _run_coroutine(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    """Bridge a coroutine to this synchronous caller, loop-safe.

    The BudgetEnforcer LLM path is ``async`` while the guard's ``verify``
    path is intentionally synchronous (and tested synchronously with an
    injected fake).  Run the coroutine to completion whether or not an
    event loop is already active on the calling thread — a fresh loop in a
    worker thread is used when one is already running (e.g. inside a
    FastAPI request handler) so we never re-enter a live loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


# A claim is "supported" when the verifier answers YES and supplies a
# non-empty evidence span, OR when it answers YES-but-no-quote and the
# lexical check (Q6-A) already confirmed grounding.
VERIFIER_SYSTEM_PROMPT = (
    "You are a strict, literal verification oracle. You will be given a "
    "SOURCE TRANSCRIPT and a CLAIM. Your ONLY job is to decide whether the "
    "transcript textually or factually supports the claim. Answer only "
    'with a JSON object: {"supports": true|false, "evidence": "<verbatim '
    'quote from the transcript, or empty string if none>", "reason": '
    '"<one sentence>"}. Do not infer, fill gaps, or be helpful. If the '
    "claim goes beyond what the transcript states, answer false."
)

# Default verifier model — a *different family* from the primary reviewer
# default (deepseek-v4-flash) so errors decorrelate.  Override per-instance.
VERIFIER_DEFAULT_MODEL = "anthropic/claude-3-5-haiku"
VERIFIER_DEFAULT_TEMPERATURE = 0.0  # fully deterministic binary judgment
VERIFIER_DEFAULT_MAX_TOKENS = 400


@dataclass
class VerificationResult:
    """Outcome of the Q6-B second-pass verifier for one claim."""

    claim_id: str
    # True when the verifier judges the transcript supports the claim.
    supports: bool
    # Verbatim evidence quote from the transcript (may be empty).
    evidence: str
    # One-line rationale from the verifier (audit trail).
    reason: str
    # The model family that actually produced this verdict (for Q6-D
    # per-family disagreement tracking).
    model_id: str
    # True when the LLM call failed / returned unparseable output.  On a
    # soft failure we DEFAULT TO distrust (supports=False) — never let a
    # verifier error let a claim through.
    degraded: bool = False


# A ``call_llm`` injectable: takes the message list, returns the raw
# string.  Mirrors ``BudgetEnforcer.call``'s contract surface we care
# about (content string); tests pass a fake.
LLMCaller = Callable[[list[dict[str, str]]], str]


def _evidence_prompt(transcript_text: str, claim_content: str) -> list[dict[str, str]]:
    user = (
        'SOURCE TRANSCRIPT:\n"""\n' + transcript_text + '\n"""\n\n'
        'CLAIM:\n"""\n' + claim_content + '\n"""\n\n'
        "Does the transcript support the claim? Respond ONLY with JSON."
    )
    return [
        {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _parse_verifier_response(content: str) -> dict[str, Any]:
    """Extract the {supports, evidence, reason} JSON, tolerant of prose."""
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        # Fall through to brace extraction.
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
            except (json.JSONDecodeError, ValueError):
                parsed = {}
        else:
            parsed = {}
    supports = bool(parsed.get("supports", False))
    evidence = str(parsed.get("evidence", "") or "")
    reason = str(parsed.get("reason", "") or "")
    return {"supports": supports, "evidence": evidence, "reason": reason}


class SecondPassVerifier:
    """Narrow cross-family LLM verifier: does the transcript support this?"""

    def __init__(
        self,
        *,
        model_id: str = VERIFIER_DEFAULT_MODEL,
        temperature: float = VERIFIER_DEFAULT_TEMPERATURE,
        max_tokens: int = VERIFIER_DEFAULT_MAX_TOKENS,
        # Late-binding LLM caller (mirrors critic.get_budget_enforcer).
        call_llm: LLMCaller | None = None,
    ) -> None:
        self.model_id = model_id
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self._call_llm_override = call_llm

    def _call(self, messages: list[dict[str, str]]) -> str:
        if self._call_llm_override is not None:
            return self._call_llm_override(messages)
        # Production path: route through BudgetEnforcer (project rule).
        # Imported lazily so the module is importable without a live
        # enforcer (tests inject a fake instead).
        from decimal import Decimal

        from app.models.capability_models import Budget
        from app.services.budget_enforcer import get_budget_enforcer

        enforcer = get_budget_enforcer()
        # ``Budget.max_cost_usd`` is a Decimal; .call is async, so we bridge
        # to the synchronous guard path with a loop-safe runner.
        coro = enforcer.call(
            budget=Budget(max_cost_usd=Decimal("0.05"), max_wall_time_seconds=60, max_iterations=1),
            model_id=self.model_id,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        result = _run_coroutine(coro)
        if not result.get("success", False):
            return ""
        return str(result.get("response") or result.get("content") or "")

    async def _acall(self, messages: list[dict[str, str]]) -> str:
        """Async LLM path (Comment 9): used by :meth:`averify`."""
        if self._call_llm_override is not None:
            # Allow an async override too.
            ov = self._call_llm_override
            if hasattr(ov, "__await__"):
                return await ov(messages)
            return ov(messages)
        from decimal import Decimal

        from app.models.capability_models import Budget
        from app.services.budget_enforcer import get_budget_enforcer

        enforcer = get_budget_enforcer()
        result = await enforcer.call(
            budget=Budget(max_cost_usd=Decimal("0.05"), max_wall_time_seconds=60, max_iterations=1),
            model_id=self.model_id,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if not result.get("success", False):
            return ""
        return str(result.get("response") or result.get("content") or "")

    def verify(self, *, transcript_text: str, claim_id: str, claim_content: str) -> VerificationResult:
        """Run the second-pass check for one claim (synchronous caller).

        On any LLM soft-failure we return ``supports=False`` with
        ``degraded=True`` — the safe default (distrust on uncertainty).
        """
        messages = _evidence_prompt(transcript_text, claim_content)
        try:
            content = self._call(messages)
        except Exception:  # BudgetExhausted, network, etc.
            logger.exception("verifier.llm_failure claim_id=%s", claim_id)
            return VerificationResult(
                claim_id=claim_id,
                supports=False,
                evidence="",
                reason="verifier LLM call failed",
                model_id=self.model_id,
                degraded=True,
            )
        if not content:
            return VerificationResult(
                claim_id=claim_id,
                supports=False,
                evidence="",
                reason="verifier returned empty output",
                model_id=self.model_id,
                degraded=True,
            )
        parsed = _parse_verifier_response(content)
        return VerificationResult(
            claim_id=claim_id,
            supports=bool(parsed["supports"]),
            evidence=str(parsed["evidence"]),
            reason=str(parsed["reason"]),
            model_id=self.model_id,
        )

    async def averify(self, *, transcript_text: str, claim_id: str, claim_content: str) -> VerificationResult:
        """Async second-pass check (Comment 9).

        Mirrors :meth:`verify` but awaits the LLM path directly instead of
        bridging through a worker thread, so it can be called from the async
        inbox-drain orchestrator without re-entering a live event loop.

        On any LLM soft-failure we return ``supports=False`` with
        ``degraded=True`` — the safe default (distrust on uncertainty).
        """
        messages = _evidence_prompt(transcript_text, claim_content)
        try:
            content = await self._acall(messages)
        except Exception:  # BudgetExhausted, network, etc.
            logger.exception("verifier.llm_failure claim_id=%s", claim_id)
            return VerificationResult(
                claim_id=claim_id,
                supports=False,
                evidence="",
                reason="verifier LLM call failed",
                model_id=self.model_id,
                degraded=True,
            )
        if not content:
            return VerificationResult(
                claim_id=claim_id,
                supports=False,
                evidence="",
                reason="verifier returned empty output",
                model_id=self.model_id,
                degraded=True,
            )
        parsed = _parse_verifier_response(content)
        return VerificationResult(
            claim_id=claim_id,
            supports=bool(parsed["supports"]),
            evidence=str(parsed["evidence"]),
            reason=str(parsed["reason"]),
            model_id=self.model_id,
        )


def different_family(reviewer_model: str, verifier_model: str) -> bool:
    """True when verifier_model is from a *different* provider family than
    reviewer_model (so their errors decorrelate).

    Family is the provider prefix before the first ``/`` (e.g.
    ``deepseek/...`` -> ``deepseek``).  Bare model ids with no ``/``
    (e.g. the critic default ``deepseek-v4-flash``) take their family
    from the leading token before the first ``-`` so they still resolve
    to a provider (``deepseek``), keeping a same-provider verifier from
    being wrongly treated as decorrelated.
    """

    def _fam(m: str) -> str:
        m = m.strip().lower()
        if "/" in m:
            return m.split("/", 1)[0]
        # Bare id: leading token before '-' (deepseek-v4-flash -> deepseek).
        return m.split("-", 1)[0]

    return _fam(reviewer_model) != _fam(verifier_model)
