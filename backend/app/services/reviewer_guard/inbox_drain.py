"""Q6-F — drain ReviewerGuard escalations into the HITL inbox.

This module is the single production *caller* of the ReviewerGuard engine
(Q6-A..E).  Everything else in ``reviewer_guard/`` is pure logic with zero
production callers; this is the wire that makes the trust firewall actually
protect a run.

Design (follows the orchestrator's own docstring contract):

* ``ReviewerGuard`` verifies a batch of claims against a transcript and
  returns escalate-only decisions (``VerificationBatch.escalations``).
* We build the run's *grounding corpus* from the workflow brief
  (``description``) plus every executed node's output.  Each node output is
  then verified (lexical-only, Q6-A) against the corpus **excluding its own
  span** — i.e. a node's output must be supported by something else in the
  run (the brief or a sibling's output), not by restating itself.  This is
  the auditable / replayable "groundedness verdict" meeting the run object —
  the North-Star puzzle linchpin.
* Every escalation is drained into the existing ``/api/inbox`` sink via
  ``HITLService.create_interrupt`` with ``interrupt_type=ESCALATION``.  The
  inbox already exists and is frontend-consumed, so we reuse it verbatim.
* We run **lexical-only** by default (no cross-family ``SecondPassVerifier``
  is injected) → $0 added token cost.  Escalate-only → the guard can never
  mutate or corrupt run data; the worst case is a spurious inbox item.

This module is best-effort and never raises: a failure to verify or to
create an inbox item is logged and swallowed so substrate execution is never
blocked by the guard.  That matches the escalate-only + non-blocking
invariant.

No DB writes here beyond the inbox item (owned by the caller's transaction);
no LLM calls here (lexical-only).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.reviewer_guard.calibration import CalibrationMap
from app.services.reviewer_guard.groundedness import (
    Claim,
    TranscriptSpan,
)
from app.services.reviewer_guard.orchestrator import ReviewerGuard
from app.services.reviewer_guard.verifier import (
    SecondPassVerifier,
    different_family,
)

logger = logging.getLogger(__name__)

# span_id for the workflow brief (description) grounding span.
_BRIEF_SPAN_ID = "brief"


@dataclass
class _RunContext:
    """Normalised view of a completed substrate run for the guard."""

    run_id: str
    mission_id: str | None
    user_id: str | None
    workspace_id: str | None
    # The full grounding corpus: brief + every node output.
    spans: list[TranscriptSpan] = field(default_factory=list)
    # (node_id, claim_id, content) for every node output we want verified.
    claims: list[Claim] = field(default_factory=list)


def _node_output_text(node_output: Any) -> str:
    """Best-effort extract a textual claim from a node's ``output_data``.

    LLM nodes produce ``{"text": "..."}``; other nodes may carry a string or
    a JSON-able blob.  We normalise to a single string so the guard has
    something to ground.
    """
    if node_output is None:
        return ""
    if isinstance(node_output, str):
        return node_output
    if isinstance(node_output, dict):
        text = node_output.get("text")
        if isinstance(text, str) and text.strip():
            return text
        # Fall back to a compact JSON rendering of the whole payload.
        try:
            rendered = json.dumps(node_output, default=str)
        except Exception:
            rendered = str(node_output)
        return rendered
    return str(node_output)


def build_run_context(
    *,
    run_id: str,
    mission_id: str | None,
    nodes: list[Any],
    user_id: str | None = None,
    workspace_id: str | None = None,
    brief: str | None = None,
) -> _RunContext:
    """Build the grounding corpus + claims for a run from its node outputs.

    Args:
        run_id: the substrate run id.
        mission_id: the mission / workflow id (used as the inbox mission link)
        nodes: the workflow nodes (need ``.id`` and ``.output_data``).  Their
            completed outputs become both grounding spans and the claims to
            verify.  Each claim is verified against the corpus *excluding its
            own node span*, so a node must be supported by the brief or a
            sibling's output, not by restating itself.
        user_id / workspace_id: run scoping (from the workflow / mission).
        brief: an optional grounding text (e.g. the workflow description) that
            every claim may restate.  When None we try ``nodes``' parent
            workflow description upstream; the caller passes it in.

    Returns:
        A :class:`_RunContext` with ``spans`` (grounding corpus, excluding
        nothing yet) and ``claims`` (node outputs to verify).  When there is
        nothing to verify (no node outputs), ``claims`` is empty and the
        caller should skip verification.
    """
    spans: list[TranscriptSpan] = []
    if brief and brief.strip():
        spans.append(
            TranscriptSpan(
                span_id=_BRIEF_SPAN_ID,
                text=brief,
                meta={"role": "brief"},
            )
        )

    for node in nodes:
        text = _node_output_text(getattr(node, "output_data", None))
        if text and text.strip():
            node_id = getattr(node, "id", f"node_{len(spans)}")
            spans.append(
                TranscriptSpan(
                    span_id=f"node:{node_id}",
                    text=text,
                    meta={"node_id": node_id, "role": "output"},
                )
            )

    claims: list[Claim] = []
    for node in nodes:
        text = _node_output_text(getattr(node, "output_data", None))
        if text and text.strip():
            node_id = getattr(node, "id", f"node_{len(claims)}")
            claims.append(
                Claim(
                    claim_id=f"run:{run_id}:node:{node_id}",
                    content=text,
                    stated_confidence=1.0,
                )
            )

    return _RunContext(
        run_id=run_id,
        mission_id=mission_id,
        user_id=user_id,
        workspace_id=workspace_id,
        spans=spans,
        claims=claims,
    )


def _transcript_for_claim(ctx: _RunContext, claim: Claim) -> list[TranscriptSpan]:
    """Grounding corpus for a single claim: everything except the claim's own node span."""
    node_id = claim.claim_id.split("node:")[-1] if "node:" in claim.claim_id else None
    own_span_id = f"node:{node_id}" if node_id else None
    return [s for s in ctx.spans if s.span_id != own_span_id]


def _select_verifier_model(reviewer_model: str) -> tuple[str | None, str | None]:
    """Resolve a cross-family verifier model from the catalog (Comment 9).

    Returns ``(model_id, degradation_reason)``.  The model must:
      * be enabled in the catalog,
      * advertise the ``verifier`` use case,
      * be from a *different* family than ``reviewer_model`` (decorrelation),
      * not be a premium model unless premium models are enabled.

    If nothing qualifies we return ``(None, reason)`` — the caller degrades
    to lexical-only and records ``reason`` rather than silently skipping.
    """
    from app.config import settings
    from app.services.model_catalog import (
        ModelTier,
        get_model_catalog,
    )

    if not getattr(settings, "REVIEWER_GUARD_SECOND_PASS_ENABLED", False):
        return None, "second_pass_disabled"

    try:
        catalog = get_model_catalog()
    except Exception as exc:  # pragma: no cover - catalog load failure
        logger.warning("reviewer_guard.verifier.catalog_unavailable: %s", exc)
        return None, "catalog_unavailable"

    exclude_families = []
    fam = reviewer_model.split("/", 1)[0]
    if "/" not in reviewer_model:
        fam = reviewer_model.split("-", 1)[0]
    if fam:
        exclude_families.append(fam)

    include_premium = bool(getattr(settings, "ENABLE_PREMIUM_MODELS", False))
    candidates = catalog.select_for_use_case(
        "verifier",
        include_local=True,
        include_cloud=True,
        include_premium=include_premium,
        exclude_families=exclude_families,
    )
    if not candidates:
        return None, f"no_different_family_verifier:{fam}"
    # Deterministic pick: prefer the cheapest paid/cloud verifier; fall back
    # to any enabled candidate.  Local models cost $0 so they rank first.
    candidates.sort(key=lambda c: (c.input_per_1m + c.output_per_1m, not c.local))
    chosen = candidates[0]
    return chosen.model_id, None


async def drain_run_to_inbox(
    db: Any,
    ctx: _RunContext,
    *,
    reviewer_model: str = "deepseek-v4-flash",
    calibration: Any = None,
    run_verifier: bool | None = None,
) -> int:
    """Verify a run's node outputs and drain escalations into the HITL inbox.

    Pure escalate-only: a node output that cannot be supported by the brief or
    any sibling node output (lexical groundedness, Q6-A) is surfaced as an
    ``ESCALATION`` inbox item.  Lexical-only → no LLM call → $0 added cost.

    Args:
        db: an open :class:`AsyncSession` (the caller's transaction).
        ctx: a :class:`_RunContext` built by :func:`build_run_context`.
        reviewer_model: the run's primary model id (for decorrelation).
        calibration: optional fitted :class:`CalibrationMap`; when None a
            cold-start (conservative shrink) map is used.

    Returns:
        The number of escalations drained into the inbox.

    Best-effort: any exception is logged and ``0`` returned — the guard never
    aborts or corrupts a run.
    """
    # Nothing to verify (e.g. a run with no node outputs) → no escalations.
    if not ctx.claims:
        return 0
    # No grounding corpus at all (no brief, no sibling outputs) → every claim
    # would be ungrounded and escalate; that is noise, so skip rather than
    # flood the inbox with vacuous escalations.
    if not ctx.spans:
        return 0

    # Comment 9: resolve a cross-family verifier model from the catalog.
    # verifier_model is None when second-pass is disabled or no different-family
    # verifier exists → we degrade to lexical-only and record the reason.
    if run_verifier is None:
        run_verifier = getattr(
            __import__("app.config", fromlist=["settings"]).settings,
            "REVIEWER_GUARD_SECOND_PASS_ENABLED",
            False,
        )
    verifier_model_id, degrade_reason = (None, "second_pass_disabled")
    if run_verifier:
        verifier_model_id, degrade_reason = _select_verifier_model(reviewer_model)
    if verifier_model_id is not None:
        logger.info(
            "reviewer_guard.second_pass_enabled run=%s reviewer=%s verifier=%s",
            ctx.run_id,
            reviewer_model,
            verifier_model_id,
        )
    else:
        logger.info(
            "reviewer_guard.second_pass_disabled run=%s reviewer=%s reason=%s",
            ctx.run_id,
            reviewer_model,
            degrade_reason,
        )

    try:
        from app.models.hitl_models import HumanInterruptType
        from app.services.hitl_service import HITLService

        service = HITLService(db)
        cal = calibration or CalibrationMap(method="isotonic")
        drained = 0
        for claim in ctx.claims:
            corpus = _transcript_for_claim(ctx, claim)
            # Single-claim guard: lexical-only by default.  When a verifier
            # model was resolved from the catalog we inject a SecondPassVerifier
            # (cross-family semantic check); otherwise lexical-only with the
            # degradation reason recorded below.
            guard_kwargs: dict[str, Any] = dict(calibration=cal, reviewer_model=reviewer_model)
            verifier: SecondPassVerifier | None = None
            if verifier_model_id is not None:
                verifier = SecondPassVerifier(model_id=verifier_model_id)
                guard_kwargs["verifier"] = verifier
            guard = ReviewerGuard(corpus, **guard_kwargs)
            transcript_text = "\n".join(f"[{s.span_id}] {s.text}" for s in corpus)
            vresult = None
            if verifier is not None:
                # Async cross-family second pass (Comment 9): run it once and
                # hand the result to the orchestrator so we never double-call
                # the LLM or re-enter a live event loop via the thread bridge.
                vresult = await verifier.averify(
                    transcript_text=transcript_text,
                    claim_id=claim.claim_id,
                    claim_content=claim.content,
                )
            decision = guard.verify_batch(
                [claim],
                run_verifier=(vresult is not None),
                transcript_text=transcript_text,
                verifier_results={claim.claim_id: vresult} if vresult is not None else None,
            ).decisions[0]
            if not decision.escalate:
                continue
            if ctx.user_id is None:
                # No user to notify → unresolvable inbox item.  Skip rather
                # than raise; the verdict is still logged below.
                continue
            node_id = claim.claim_id.split("node:")[-1] if "node:" in claim.claim_id else None
            # GOLD t_002875da: carry a depth-policy decision on the inbox item so
            # the HITL inbox UI can render the reasoning that motivated the
            # escalation.  A ReviewerGuard escalation is by definition a
            # high-risk, low-grounding situation → force deep + HITL.
            from decimal import Decimal

            from app.services.hitl_service import HITLService

            depth_decision = HITLService.build_depth_decision(
                risk="high",
                uncertainty=max(0.0, min(1.0, 1.0 - float(decision.calibrated_trust))),
                budget_remaining_usd=Decimal("10.0"),
                prior_failures=0,
                tool_requires_approval=True,
                retry_count=0,
                policy_override=False,
            )
            await service.create_interrupt(
                mission_id=ctx.mission_id,
                user_id=_coerce_user_id(ctx.user_id),
                interrupt_type=HumanInterruptType.ESCALATION,
                title=f"ReviewerGuard: ungrounded output on run {ctx.run_id}",
                description=decision.reason,
                proposed_action={
                    "claim_id": decision.claim_id,
                    "grounded": decision.grounded,
                    "calibrated_trust": round(decision.calibrated_trust, 3),
                    "evidence": decision.evidence,
                },
                context={
                    "origin": "reviewer_guard",
                    "run_id": ctx.run_id,
                    "verdict": decision.action,
                    "grounded": decision.grounded,
                    "calibrated_trust": round(decision.calibrated_trust, 3),
                    "second_pass": ("enabled" if verifier_model_id is not None else "lexical_only"),
                    "verifier_model": verifier_model_id,
                    "verifier_degradation": (None if verifier_model_id is not None else degrade_reason),
                },
                depth_decision=depth_decision,
                task_id=node_id,
                node_id=node_id,
                run_id=ctx.run_id,
                workspace_id=ctx.workspace_id,
            )
            drained += 1
        return drained
    except Exception as exc:
        logger.warning(
            "ReviewerGuard inbox drain failed for run=%s: %s",
            ctx.run_id,
            exc,
        )
        return 0


def _coerce_user_id(user_id: Any) -> int:
    """HITLService requires an ``int`` user_id; coerce defensively."""
    if isinstance(user_id, int):
        return user_id
    try:
        return int(user_id)
    except (TypeError, ValueError):
        # Cannot be resolved to an int → the inbox item can't be scoped to a
        # user.  The caller skips when user_id is None; this is a safety net
        # for non-int but non-None values.
        raise ValueError(f"unsupported user_id type: {type(user_id)!r}")
