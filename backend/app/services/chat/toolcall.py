# ─────────────────────────────────────────────────────────────────────────
# Auto-decomposed from app/services/chat_service.py (CARD 3 refactor).
# Part of the `chat` package. Sibling cross-references and original imports
# are preserved so behavior/signatures stay byte-for-byte identical.
# ─────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from decimal import Decimal
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from sqlalchemy import func, select

from app.config import settings
from app.models.capability_models import Budget, BudgetExhausted
from app.models.chat import ChatBranch, ChatFile, ChatMessage, ChatThread
from app.services.background_task_manager import background_task_manager
from app.services.chat_context import _inject_memory_context, _prune_messages_to_budget
from app.services.llm_providers import (
    _LLM_API_BASE,
    _LLM_API_KEY,
    _LLM_MODEL,
    OPENAI_PROVIDER_FAMILIES,
    PROVIDER_MAP,
    _detect_provider_from_key,
    _get_base_url_for_provider,
    _get_provider_for_model,
    _get_upstream_model_name,
    _normalize_provider,
    _providers_compatible,
    _resolve_provider,
)
from app.services.personal_memory_extractor import (
    PersonalMemoryExtractor,
    RegexPersonalMemoryExtractor,
)

from .byok import _MAX_TOOL_ROUNDS, _SANDBOXD_SYSTEM_GUIDANCE, _lookup_stored_byok_key, _validate_byok_key_matches_model
from .messages import _process_attachments, create_chat_message, create_chat_message_fresh_session
from .prompts import _get_active_prompt_content, _inject_web_search
from .threads import get_chat_thread

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from .streaming import _get_client, _safe_effective_base_url  # noqa: TC004

logger = logging.getLogger(__name__)

__all__ = [
    "_HARD_TOOL_CALL_CAP_S",
    "_build_chat_messages",
    "_execute_tool_call",
    "_get_chat_openai_tools",
    "_maybe_extract_memory_claims",
    "_record_tool_cost_fire_and_forget",
    "generate_thread_title",
    "send_message_to_llm",
]

_HARD_TOOL_CALL_CAP_S = 120.0


async def _build_chat_messages(
    db: AsyncSession,
    thread_id: int,
    max_history: int = 20,
) -> list[dict]:
    # Build the messages array for the LLM including conversation history.
    # Fetches the last max_history messages from the thread and includes them
    # in the prompt. Uses the thread custom system prompt if available.
    #
    # Phase 6: prompt version lookup chain:
    #   1. If thread has a workspace_id, try prompt_versions table first
    #   2. Fall back to thread.metadata_.get("system_prompt")
    #   3. Final fallback: "You are a helpful assistant."
    thread = await get_chat_thread(db, thread_id)

    system_prompt: str | None = None

    # Phase 6: try prompt_versions first (workspace-scoped)
    if thread and thread.workspace_id:
        # Check if thread has a specific prompt_version_id stored
        prompt_name = "Default Assistant"
        if thread.metadata_ and isinstance(thread.metadata_, dict):
            prompt_name = thread.metadata_.get("prompt_name", "Default Assistant")
        system_prompt = await _get_active_prompt_content(db, thread.workspace_id, name=prompt_name)

    # Fallback: inline system prompt from thread metadata
    if not system_prompt and thread and thread.metadata_ and isinstance(thread.metadata_, dict):
        custom = thread.metadata_.get("system_prompt", "")
        if custom and custom.strip():
            system_prompt = custom

    if not system_prompt:
        system_prompt = "You are a helpful assistant."

    # Append sandboxd preview guidance when sandboxd is enabled
    if settings.SANDBOXD_ENABLED:
        system_prompt += _SANDBOXD_SYSTEM_GUIDANCE

    messages = [{"role": "system", "content": system_prompt}]

    history_stmt = (
        select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.id.desc()).limit(max_history)
    )
    history_result = await db.execute(history_stmt)
    recent_messages = list(reversed(history_result.scalars().all()))

    messages.extend(
        {"role": msg.role, "content": msg.content} for msg in recent_messages if msg.role in ("user", "assistant")
    )

    # Phase 2.1: token-budget pruning (keeps first+last, replaces middle)
    if settings.CHAT_CONTEXT_PRUNING_ENABLED:
        messages = _prune_messages_to_budget(messages, settings.CHAT_CONTEXT_TOKEN_BUDGET)

    return messages


async def _maybe_extract_memory_claims(
    *,
    db: AsyncSession | None = None,
    thread_id: int,
    user_id: int,
    user_message: str,
    assistant_response: str,
) -> None:
    """Fire-and-forget: extract personal-memory claims from a chat exchange.

    Called after the assistant response is persisted.  Opens a *fresh*
    DB session so it can run independently of the caller's session
    lifecycle (the caller's session is typically closed before the
    LLM call to avoid idle-in-transaction timeout).

    Guardrails:
    * Gated by ``FLOWMANNER_CROSS_MISSION_MEMORY`` feature flag.
    * Skipped when the conversation is paused.
    * Defensive filter drops sensitive/restricted/private claims.
    * Capped at 5 claims per exchange.
    * Errors are swallowed — never breaks the chat.
    """
    if not settings.FLOWMANNER_CROSS_MISSION_MEMORY:
        return

    try:
        from app.database import fresh_session

        async with fresh_session() as fresh_db:
            # Need workspace_id from the thread.
            thread = await get_chat_thread(fresh_db, thread_id)
            if thread is None or not thread.workspace_id:
                return

            workspace_id = thread.workspace_id

            # ── Check pause toggle ──────────────────────────────────
            from app.services.memory_extraction_pause_service import (
                MemoryExtractionPauseService,
            )

            pause_svc = MemoryExtractionPauseService(fresh_db)
            if await pause_svc.is_paused(
                user_id=user_id,
                workspace_id=workspace_id,
                conversation_id=str(thread_id),
            ):
                logger.info(
                    "memory_extraction: skipped for thread %s (paused)",
                    thread_id,
                )
                return

            # ── Run extractor ───────────────────────────────────────
            # Attempt LLM-based extraction first (via ModelRouter +
            # PersonalMemoryExtractor) with a 5-second timeout.  If the
            # LLM is unavailable, slow, or returns garbage, fall back
            # to the deterministic regex extractor.
            combined_text = f"User: {user_message}\n\nAssistant: {assistant_response}"

            regex_fallback = RegexPersonalMemoryExtractor()
            claims: list = []
            _extraction_source = "empty"
            try:
                from app.services.model_router import get_model_router

                llm_extractor = PersonalMemoryExtractor(
                    get_model_router=get_model_router,
                )
                claims, source = await asyncio.wait_for(
                    llm_extractor.extract_with_fallback(
                        user_id=user_id,
                        workspace_id=workspace_id,
                        text=combined_text,
                        max_claims=5,
                    ),
                    timeout=5.0,
                )
                if claims:
                    _extraction_source = "llm"
                    logger.info(
                        "memory_extraction: LLM extractor returned %d claims (source=%s) for thread %s",
                        len(claims),
                        source,
                        thread_id,
                    )
                else:
                    # LLM succeeded but produced nothing — try regex
                    claims = regex_fallback.extract(combined_text)
                    _extraction_source = "regex_fallback_empty"
                    if claims:
                        logger.info(
                            "memory_extraction: LLM returned 0 claims; regex fallback found %d for thread %s",
                            len(claims),
                            thread_id,
                        )
            except TimeoutError:
                logger.info(
                    "memory_extraction: LLM extraction timed out for thread %s; falling back to regex",
                    thread_id,
                )
                claims = regex_fallback.extract(combined_text)
                _extraction_source = "regex_fallback_timeout"
            except Exception as llm_err:
                logger.info(
                    "memory_extraction: LLM extraction failed for thread %s (%s); falling back to regex",
                    thread_id,
                    llm_err,
                )
                claims = regex_fallback.extract(combined_text)
                _extraction_source = "regex_fallback_error"

            if not claims:
                logger.debug(
                    "memory_extraction: no claims extracted for thread %s",
                    thread_id,
                )
                return

            # ── Defensive filter ────────────────────────────────────
            # Drop sensitive/restricted claims and private-scope claims.
            # CandidateClaim has no ``sensitivity`` field (it is a
            # lightweight DTO), so we fall back to ``claim_type`` as a
            # belt-and-suspenders check.
            _EXCLUDED_SENSITIVITIES = frozenset({"sensitive", "restricted"})
            _EXCLUDED_SCOPES = frozenset({"private"})

            safe_claims = [
                c
                for c in claims
                if getattr(c, "sensitivity", "normal") not in _EXCLUDED_SENSITIVITIES
                and c.claim_type not in _EXCLUDED_SENSITIVITIES
                and c.scope not in _EXCLUDED_SCOPES
            ]

            # GOV-1.5 (C5): persist *why* claims were dropped. The
            # defensive filter previously dropped claims silently, so the
            # 0.85 confidence gate could never be calibrated from real
            # data. Log every defensively-dropped claim with its score
            # and reason so a later pass can quantify the drop rate.
            dropped_defensive = len(claims) - len(safe_claims)
            if dropped_defensive:
                _dropped_below: list[float] = []
                for c in claims:
                    if c not in safe_claims:
                        _dropped_below.append(float(getattr(c, "confidence", 0.0)))
                        logger.info(
                            "memory_extraction: dropped (defensive filter) "
                            "thread=%s claim_type=%s scope=%s confidence=%.2f "
                            "subject=%s predicate=%s",
                            thread_id,
                            getattr(c, "claim_type", "?"),
                            getattr(c, "scope", "?"),
                            float(getattr(c, "confidence", 0.0)),
                            getattr(c, "subject", "?"),
                            getattr(c, "predicate", "?"),
                        )
                logger.info(
                    "memory_extraction: defensive filter dropped %d/%d claims for thread %s (scores=%s)",
                    dropped_defensive,
                    len(claims),
                    thread_id,
                    _dropped_below,
                )

            if not safe_claims:
                logger.info(
                    "memory_extraction: all %d claims filtered for thread %s",
                    len(claims),
                    thread_id,
                )
                return

            # ── Persist claims ──────────────────────────────────────
            # Solo workspaces → direct write (no approval needed).
            # Team workspaces (multi-member, >30 days) → stage for
            # user approval via BackgroundReviewService.
            from app.models.workspace_models import Workspace
            from app.services.memory.background_review_service import (
                BackgroundReviewService,
                compute_write_approval,
            )
            from app.services.personal_memory_service import PersonalMemoryService

            # Fetch workspace to determine approval path.
            ws_row = (
                await fresh_db.execute(select(Workspace).where(Workspace.id == workspace_id))
            ).scalar_one_or_none()
            needs_approval = compute_write_approval(ws_row)

            from app.services.memory.extraction_thresholds import (
                MEMORY_EXTRACTION_MIN_CONFIDENCE,
                is_trusted_direct_write,
                passes_confidence_gate,
            )
            from app.services.memory.provenance_approval import (
                requires_provenance_approval,
            )

            pm_service = PersonalMemoryService(fresh_db)
            review_service = BackgroundReviewService()
            persisted = 0
            staged = 0
            for claim in safe_claims:
                # GOV-1.2 provenance gate (deterministic, no confidence
                # bypass). The chat extractor infers every claim here with
                # source_type="conversation" (never user_explicit), so the
                # gate routes ALL extracted claims to human approval —
                # unless the workspace/approval decision already forces
                # staging. Only a literally user-authored source_type
                # ("user_explicit") may bypass to a direct write.
                # This is the reliable control; 1.3a scan / 1.3b scrub are
                # NOT allowed to de-escalate it.
                claim_source_type = getattr(claim, "source_type", None) or "conversation"
                provenance_requires_approval = requires_provenance_approval(claim_source_type)
                try:
                    if needs_approval or provenance_requires_approval:
                        # Stage for user approval
                        content_str = f"{claim.subject} {claim.predicate}: {json.dumps(claim.object, default=str)}"
                        pw_id = await review_service.stage_pending_write(
                            fresh_db,
                            workspace_id=workspace_id,
                            user_id=user_id,
                            mission_id=None,
                            action="add",
                            content=content_str,
                            metadata={"source_type": claim_source_type},
                        )
                        if pw_id:
                            staged += 1
                    else:
                        # Direct write — only reachable for a user_explicit
                        # source_type (see requires_provenance_approval).
                        # GOV-1.5 (calibration): even trusted direct writes
                        # are held for approval when their extractor
                        # confidence is below the calibrated floor. This
                        # gate applies ONLY to the trusted path — untrusted
                        # source_types never reach this branch, so the
                        # confidence gate can never de-escalate a
                        # provenance-mandated approval (GOV-1.2 invariant).
                        if is_trusted_direct_write(claim_source_type) and not passes_confidence_gate(claim.confidence):
                            logger.info(
                                "memory_extraction: trusted claim held for "
                                "approval below confidence gate (%.2f < %.2f) "
                                "thread=%s subject=%s predicate=%s",
                                claim.confidence,
                                MEMORY_EXTRACTION_MIN_CONFIDENCE,
                                thread_id,
                                claim.subject,
                                claim.predicate,
                            )
                            content_str = f"{claim.subject} {claim.predicate}: {json.dumps(claim.object, default=str)}"
                            pw_id = await review_service.stage_pending_write(
                                fresh_db,
                                workspace_id=workspace_id,
                                user_id=user_id,
                                mission_id=None,
                                action="add",
                                content=content_str,
                                metadata={
                                    "source_type": claim_source_type,
                                    "held_reason": "confidence_below_gate",
                                    "confidence": claim.confidence,
                                },
                            )
                            if pw_id:
                                staged += 1
                            continue
                        await pm_service.create(
                            user_id=user_id,
                            workspace_id=workspace_id,
                            subject=claim.subject,
                            predicate=claim.predicate,
                            object=claim.object,
                            claim_type=claim.claim_type,
                            scope=claim.scope,
                            source_type=claim_source_type,
                            confidence=claim.confidence,
                            # Direct trusted writes are human-authored → NULL
                            # agent_id (highest trust, Q5-A).
                            agent_id=None,
                        )
                        persisted += 1
                except Exception as create_err:
                    logger.warning(
                        "memory_extraction: claim persist failed: %s",
                        create_err,
                    )

            # fresh_session() commits on successful exit

            # ── Record extraction metrics ───────────────────────────
            from app.core.metrics import record_memory_extraction

            record_memory_extraction(
                source=_extraction_source,
                claims_extracted=len(claims),
                claims_persisted=persisted,
                claims_staged=staged,
                claims_dropped=dropped_defensive,
            )

            logger.info(
                "memory_extraction: persisted=%d staged=%d/%d raw=%d "
                "claims for thread %s (needs_approval=%s source=%s)",
                persisted,
                staged,
                len(safe_claims),
                len(claims),
                thread_id,
                needs_approval,
                _extraction_source,
            )

            # ── GOV-1.6 (C5): persist dropped candidates durably ───────
            # GOV-1.5 made drops observable (logs + metrics), but the
            # dropped candidates were not durable or Inspector-visible —
            # the GOV-1.6 (C5) gap. Write one ``drop`` MemoryCorrectionEvent
            # per defensively-dropped candidate so the drop rate the 0.85
            # gate calibrates against becomes a queryable signal in the same
            # privacy trail. claim_id is NULL (the candidate never became a
            # PersonalMemoryClaim); its shape is carried in details.
            # No-fail: an audit-sink outage must never break memory capture.
            if dropped_defensive:
                try:
                    from app.services.memory_correction_service import (
                        ALL_EVENT_TYPES,
                        MemoryCorrectionService,
                    )

                    if "drop" in ALL_EVENT_TYPES:
                        drop_svc = MemoryCorrectionService(fresh_db)
                        for c in claims:
                            if c in safe_claims:
                                continue
                            await drop_svc.record_event(
                                user_id=user_id,
                                workspace_id=workspace_id,
                                event_type="drop",
                                claim_id=None,
                                actor="system",
                                source="memory_extraction",
                                details={
                                    "reason": "defensive_filter",
                                    "claim_type": getattr(c, "claim_type", None),
                                    "scope": getattr(c, "scope", None),
                                    "confidence": float(getattr(c, "confidence", 0.0)),
                                    "subject": getattr(c, "subject", None),
                                    "predicate": getattr(c, "predicate", None),
                                },
                            )
                except Exception as drop_err:  # pragma: no cover - no-fail sink
                    logger.warning(
                        "memory_extraction: durable drop audit failed for thread %s: %s",
                        thread_id,
                        drop_err,
                    )
    except Exception as exc:
        logger.warning(
            "memory_extraction: hook failed for thread %s (non-fatal): %s",
            thread_id,
            exc,
        )


def _record_tool_cost_fire_and_forget(
    user_id: int,
    tool_name: str,
    duration_ms: float,
    workspace_id: str | None = None,
) -> None:
    """Fire-and-forget: record tool call cost using a fresh DB session.

    Opens its own ``AsyncSessionLocal`` so the recording is independent of the
    tracking must never break the chat.
    """

    async def _run() -> None:
        try:
            from app.database import fresh_session
            from app.services.cost_tracker import get_cost_tracker

            async with fresh_session() as fresh_db:
                await get_cost_tracker().record_tool_call_cost(
                    db=fresh_db,
                    user_id=user_id,
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    workspace_id=workspace_id,
                )
                # fresh_session() commits on successful exit
        except Exception as e:
            logger.debug("tool_cost_tracking_failed tool=%s error=%s", tool_name, e)

    from app.services.background_task_manager import background_task_manager

    background_task_manager.spawn(_run(), label="tool_cost_recording")


async def send_message_to_llm(
    db: AsyncSession,
    thread_id: int,
    content: str,
    user_id: int,
    model_preference: str | None = None,
    user_api_key: str | None = None,
    user_base_url: str | None = None,
    model_id: str | None = None,
    attachments: list | None = None,
    web_search: bool | None = None,
    # Comment 4: explicit budget policy required for the chat generation path.
    budget: Budget | None = None,
) -> dict:
    """Send a message to the LLM and get a non-streaming response.

    If user_api_key is provided, a per-request AsyncOpenAI client is created
    using that key (BYOK path). The key is used only for this call and discarded.
    If model_id is provided it overrides model_preference and the env default.
    If user_base_url is provided, it overrides the resolved base_url for custom providers.
    For llamacpp/* models, any BYOK key is ignored (llama.cpp doesn't use API keys).
    """
    # Lazy import: breaks the streaming<->toolcall circular import at module load.
    from .streaming import _get_client, _safe_effective_base_url

    # --- Pre-LLM setup: resolve provider, BYOK lookup, build messages ---
    # All DB work happens BEFORE saving/committing the user message so the
    # session can be closed immediately after commit, preventing PostgreSQL's
    # idle_in_transaction_session_timeout from killing the connection during
    # the potentially multi-minute LLM call.
    raw_model = model_id or model_preference or _LLM_MODEL
    base_url, api_key, model = _resolve_provider(raw_model)

    mismatch_error = _validate_byok_key_matches_model(user_api_key, raw_model)
    if mismatch_error:
        return {
            "success": False,
            "content": mismatch_error,
            "tokens": 0,
            "model": model,
        }

    # --- Stored-key fallback: if no per-request key, look up user's stored key ---
    effective_user_key = user_api_key
    effective_base_url = user_base_url
    if not effective_user_key and db is not None:
        model_provider = _get_provider_for_model(raw_model)
        stored_key, stored_base = await _lookup_stored_byok_key(db, user_id, provider_hint=model_provider)
        if stored_key:
            effective_user_key = stored_key
            effective_base_url = stored_base

    if raw_model and raw_model.startswith("llamacpp/"):
        effective_user_key = None

    # Comment 4: chat generation requires an explicit budget. See the
    # `_stream_message_to_llm_body` twin above for rationale — `enforce_budget_before_llm`
    # rejects a `None` budget, so we declare a per-message budget here.
    budget = Budget(
        max_cost_usd=Decimal("2.00"),
        max_wall_time_seconds=300,
        max_iterations=5,
        max_depth=1,
    )

    if effective_user_key:
        effective_base = effective_base_url or base_url
        # SSRF guard: never hand a user/stored base_url to the outbound client
        # without validating it resolves to a PUBLIC address (mirrors
        # _is_safe_outbound_url in app/api/v1/api_keys.py). Fall back to the
        # provider/platform default on any doubt.
        effective_base = await _safe_effective_base_url(effective_base, base_url)
        client = AsyncOpenAI(api_key=effective_user_key, base_url=effective_base)
    elif base_url != _LLM_API_BASE or api_key != _LLM_API_KEY:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    else:
        client = _get_client()

    # Circuit breaker protection
    from app.core.circuit_breaker import CircuitOpenError, get_circuit_breaker
    from app.core.metrics import record_llm_request

    provider_name = _get_provider_for_model(raw_model) or "deepseek"
    breaker = get_circuit_breaker(provider_name)
    llm_start = time.time()

    # Build messages and process all DB-dependent setup BEFORE saving user message.
    messages_for_llm = await _build_chat_messages(db, thread_id)
    # Append the new user message — it isn't in DB history yet
    messages_for_llm.append({"role": "user", "content": content})

    # ── Phase 5: resolve workspace_id for allowlist filtering ────────
    _thread_obj = await get_chat_thread(db, thread_id)
    _workspace_id = _thread_obj.workspace_id if _thread_obj else None

    # Phase 5: async tool list with workspace allowlist
    openai_tools = await _get_chat_openai_tools(db=db, workspace_id=_workspace_id)

    # ── Phase 2: pre-compute user scopes for tool authorization ──────
    _cached_user_scopes: set[str] | None = None
    _cached_user_role: str | None = None
    try:
        from app.models.user import User as UserModel

        _urow = (await db.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one_or_none()
        if _urow is not None:
            _cached_user_scopes = set(getattr(_urow, "scopes", []) or [])
            _cached_user_role = getattr(_urow, "role", None)
    except Exception:
        logger.debug("send_message_to_llm: scope pre-fetch failed (non-fatal)", exc_info=True)

    if attachments:
        messages_for_llm = await _process_attachments(db, messages_for_llm, attachments, raw_model)

    if web_search:
        messages_for_llm = await _inject_web_search(messages_for_llm, content)

    # Save user message, commit, and immediately close the session to prevent
    # idle-in-transaction timeout during the LLM call
    await create_chat_message(db, thread_id, "user", content, user_id=user_id)
    await db.commit()
    await db.close()

    try:
        async with breaker.protect():
            # ── Tool-calling loop (non-streaming) ───────────────────
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_total_tokens = 0
            executed_tools: list[dict] = []  # P0-2: track tool calls for REST response

            for _round in range(_MAX_TOOL_ROUNDS):
                create_kwargs: dict = {
                    "model": model,
                    "messages": messages_for_llm,
                }
                if openai_tools:
                    create_kwargs["tools"] = openai_tools

                response = await client.chat.completions.create(**create_kwargs)
                assistant_message = response.choices[0].message

                # Accumulate token usage across all rounds
                if response.usage:
                    total_prompt_tokens += response.usage.prompt_tokens or 0
                    total_completion_tokens += response.usage.completion_tokens or 0
                    total_total_tokens += response.usage.total_tokens or 0

                # Check for tool calls
                if assistant_message.tool_calls:
                    # Add assistant message with tool_calls to history
                    messages_for_llm.append(
                        {
                            "role": "assistant",
                            "content": assistant_message.content,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in assistant_message.tool_calls
                            ],
                        }
                    )

                    # Execute each tool and add results
                    for tc in assistant_message.tool_calls:
                        _tool_t0 = time.time()
                        tool_result = await _execute_tool_call(
                            tc.function.name,
                            tc.function.arguments,
                            user_id=user_id,
                            _user_scopes=_cached_user_scopes,
                            _user_role=_cached_user_role,
                        )
                        _record_tool_cost_fire_and_forget(
                            user_id=user_id,
                            tool_name=tc.function.name,
                            duration_ms=(time.time() - _tool_t0) * 1000.0,
                            workspace_id=_workspace_id,
                        )
                        # P0-2: track executed tool for REST response
                        executed_tools.append(
                            {
                                "tool": tc.function.name,
                                "call_id": tc.id,
                                "arguments": tc.function.arguments,
                                "result": tool_result,
                            }
                        )
                        messages_for_llm.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": tool_result,
                            }
                        )

                    continue  # Loop for next LLM call

                # No tool calls — final text response
                break
            else:
                # Loop exhausted — all rounds were tool calls
                assistant_message.content = (
                    assistant_message.content
                    or "I reached the maximum number of tool calls "
                    f"({_MAX_TOOL_ROUNDS}) without producing a final response."
                )

            # Fallback: retry without tools if the response is empty
            # (some models don't support function calling)
            if not (assistant_message.content or "").strip() and openai_tools:
                logger.info(
                    "send_message_to_llm: empty response with tools for %s, retrying without tools",
                    raw_model,
                )
                no_tools_response = await client.chat.completions.create(model=model, messages=messages_for_llm)  # type: ignore[arg-type]
                if no_tools_response.choices:
                    assistant_message = no_tools_response.choices[0].message
                    response = no_tools_response

        assistant_content = assistant_message.content

        llm_duration = time.time() - llm_start
        record_llm_request(
            provider=provider_name,
            duration_seconds=llm_duration,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            success=True,
        )

        # Session was closed before LLM call to prevent idle-in-transaction timeout.
        # Always use fresh session for saving.
        try:
            await create_chat_message_fresh_session(thread_id, "assistant", assistant_content)
        except Exception as save_err:
            logger.warning("Assistant message save failed (non-fatal): %s", save_err)

        try:
            from app.services.usage_service import get_usage_service

            get_usage_service().record_usage(
                user_id=str(user_id),
                model_id=model,
                provider="byok" if effective_user_key else "system",
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                cost=total_total_tokens * 0.000002,
            )
        except Exception as ue:
            logger.warning("Usage recording failed (non-fatal): %s", ue)

        # ── P0-1: durable memory extraction via Celery ────────────────
        try:
            from app.tasks.memory_extraction_tasks import extract_memory_claims_task

            extract_memory_claims_task.delay(
                thread_id=thread_id,
                user_id=user_id,
                user_message=content,
                assistant_response=assistant_content,
            )
        except Exception:
            logger.debug("memory_extraction Celery dispatch failed (non-fatal)", exc_info=True)

        return {
            "success": True,
            "content": assistant_content,
            "tokens": total_total_tokens,
            "model": model,
            "tool_calls": executed_tools,
        }
    except CircuitOpenError as e:
        llm_duration = time.time() - llm_start
        record_llm_request(provider=provider_name, duration_seconds=llm_duration, success=False)
        logger.warning("Circuit breaker open for %s: %s", provider_name, e)
        return {
            "success": False,
            "content": f"Service temporarily unavailable ({provider_name}). Please try again later.",
            "tokens": 0,
            "model": model,
        }
    except Exception as e:
        llm_duration = time.time() - llm_start
        record_llm_request(provider=provider_name, duration_seconds=llm_duration, success=False)
        logger.error("send_message_to_llm failed: %s", e)
        return {"success": False, "content": str(e), "tokens": 0, "model": model}


async def _get_chat_openai_tools(
    db: AsyncSession | None = None,
    workspace_id: str | None = None,
) -> list[dict] | None:
    """Return chat-safe tools in OpenAI function-calling format, or None if none available.

    ADR-001: Computed Allowlist (Task 3.2 + P0-3)
    -----------------------------------------------
    The exposed tool set is computed as the intersection of 3 gates:

    1. **Visibility gate** (curation):  ``tool.metadata.visibility != "hidden"``
       Each tool declares visibility in its own ``ToolMetadata``:
       - ``default_on``: always exposed (Phase 1 core + sandboxd tools)
       - ``opt_in``:   exposed when available (Phase 2/3 read-only tools)
       - ``hidden``:   never exposed in chat (write ops, deferred tools)
    2. **Workspace gate** (existing):   workspace allowlist intersects
    3. **Scope gate** (existing, enforced in ``_execute_tool_call``):
       ``tool.metadata.required_scopes`` checked against user scopes

    Visibility tags are curation, NOT security.  ``required_scopes`` is
    the security boundary.  Adding a tool means tagging it in-file,
    not editing a central set.
    """
    try:
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()

        # sandboxd tools gated by feature flag
        _SANDBOXD_IDS = frozenset(
            {
                "sandboxd_preview",
                "sandboxd_exec",
                "sandboxd_file_write",
                "sandboxd_file_read",
                "sandboxd_file_list",
                "sandboxd_serve",
                "browser_sandbox",
            }
        )

        # ── Compute exposed set ──────────────────────────────────────
        # P0-3: visibility now read from each tool's ToolMetadata.visibility
        # (set in-file). Default for untagged tools is "hidden" (the
        # ToolMetadata field default — see app/tools/base.py), so tools
        # not explicitly tagged are never exposed.
        exposed: list = []
        for tool in registry.list_all():
            vis = getattr(tool.metadata, "visibility", "hidden") or "hidden"
            if vis == "hidden":
                continue
            # Gate 1b: sandboxd tools require feature flag
            if tool.tool_id in _SANDBOXD_IDS and not settings.SANDBOXD_ENABLED:
                continue
            exposed.append(tool)

        # Gate 2: workspace allowlist intersection
        if db is not None and workspace_id:
            from app.models.workspace_models import get_workspace_tool_allowlist

            workspace_allowed = await get_workspace_tool_allowlist(db, workspace_id)
            if workspace_allowed is not None:
                exposed = [t for t in exposed if t.tool_id in workspace_allowed]

        # Gate 3 (required_scopes) is enforced in _execute_tool_call,
        # not here — we expose the tool schema so the LLM can call it,
        # and the scope check happens at execution time.

        tools = [t.to_openai_schema() for t in exposed]
        return tools or None
    except Exception:
        logger.debug("Failed to get chat tools from registry", exc_info=True)
        return None


async def _execute_tool_call(
    tool_name: str,
    arguments_json: str,
    user_id: int | None = None,
    workspace_id: str | None = None,
    _user_scopes: set[str] | None = None,
    _user_role: str | None = None,
) -> str:
    """Execute a single tool call via the registry and return the result as JSON.

    Phase 1: adds scope-based authorization check before ``tool.execute()``.
    If the tool declares ``required_scopes``, verify the caller holds them.
    Tools with no required_scopes are unrestricted.

    Uses a direct scope check (same pattern as v2/tools.py ``_user_has_scopes``)
    rather than issuing-then-verifying a fresh capability token, which would
    always pass and provide no real authorization.
    """
    try:
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get(tool_name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        # Phase 2: scope-based authorization check with cached user scopes.
        # If ``_user_scopes`` is provided (resolved once before the tool loop
        # in stream_message_to_llm), use it for proper scope resolution.
        # If not provided, fall back to admin-role bypass or blanket deny.
        if tool.metadata.required_scopes and user_id is not None:
            from app.core.auth_constants import ADMIN_ROLES

            # Admin/owner roles bypass scope checks
            if _user_role and _user_role in ADMIN_ROLES:
                pass  # full access
            elif _user_scopes is not None:
                missing = [s for s in tool.metadata.required_scopes if s not in _user_scopes]
                if missing:
                    logger.warning(
                        "Tool %s requires scopes %s — user missing %s",
                        tool_name,
                        tool.metadata.required_scopes,
                        missing,
                    )
                    return json.dumps(
                        {
                            "error": f"capability denied: tool '{tool_name}' requires scopes {tool.metadata.required_scopes} "
                            f"(missing: {missing})"
                        }
                    )
            else:
                # No cached scopes available — deny as defense-in-depth
                logger.warning(
                    "Tool %s requires scopes %s — denying (no cached scopes).",
                    tool_name,
                    tool.metadata.required_scopes,
                )
                return json.dumps(
                    {"error": f"capability denied: tool '{tool_name}' requires scopes {tool.metadata.required_scopes}"}
                )

        args = json.loads(arguments_json) if arguments_json else {}
        try:
            result = await asyncio.wait_for(tool.execute(args), timeout=_HARD_TOOL_CALL_CAP_S)
        except TimeoutError:
            logger.error(
                "Tool %s exceeded hard cap of %.0fs — returning clean error so the stream does not hang",
                tool_name,
                _HARD_TOOL_CALL_CAP_S,
            )
            return json.dumps(
                {
                    "error": (
                        f"Tool '{tool_name}' timed out after {int(_HARD_TOOL_CALL_CAP_S)}s "
                        f"and was cancelled. The model may retry with a simpler request."
                    )
                }
            )
        if result.success:
            return json.dumps(result.result)
        return json.dumps({"error": result.error})
    except json.JSONDecodeError:
        return json.dumps({"error": f"Invalid JSON arguments: {arguments_json}"})
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return json.dumps({"error": str(e)})


async def generate_thread_title(
    db: AsyncSession,
    thread_id: int,
    # Comment 4: explicit budget policy required for title generation.
    budget: Budget | None = None,
) -> str | None:
    """Generate a 3-5 word title for a thread based on its first exchange.

    Uses the first user message and first assistant response to prompt a fast/cheap
    model for a concise title. Does NOT store any messages in the thread — this is
    a read-only operation that only updates the thread title.

    Returns the generated title or None if the thread has < 2 messages.
    """
    thread = await get_chat_thread(db, thread_id)
    if thread is None:
        return None

    # Fetch the first two messages (first user prompt + first assistant response)
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.id.asc()).limit(2)
    )
    first_messages = result.scalars().all()

    if len(first_messages) < 2:
        return None

    user_msg = first_messages[0]
    assistant_msg = first_messages[1]

    # Build a minimal prompt for title generation
    title_prompt = (
        "Generate a very short, descriptive title (3-5 words max) for a conversation "
        "that starts with the following exchange. Return ONLY the title, no quotes, "
        "no punctuation at the end, no explanation.\n\n"
        f"User: {user_msg.content[:300]}\n\n"
        f"Assistant: {assistant_msg.content[:300]}"
    )

    # Use the default client with the fastest/cheapest model available.
    # Set LLM_FAST_MODEL env var to override (e.g. "deepseek/deepseek-v4-flash").
    # Falls back to _LLM_MODEL (default: deepseek/deepseek-v4-flash).
    try:
        model_name = os.getenv("LLM_FAST_MODEL", _LLM_MODEL)
        # Strip provider prefix if present
        if "/" in model_name:
            model_name = model_name.split("/", 1)[1]

        # Comment 4: enforce the budget BEFORE the provider call.
        from app.services.budget_enforcer import enforce_budget_before_llm

        # Title generation is a cheap, internal, read-only call. When no
        # explicit budget is supplied (the common case — the chat auto-title
        # path), fall back to a default Budget rather than crashing
        # (enforce_budget_before_llm rejects a None budget by design, so a
        # missing budget must not 500 the title endpoint).
        enforce_budget_before_llm(budget or Budget(), model_id=model_name, estimated_completion_tokens=20)
        response = await _get_client().chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": title_prompt}],
            max_tokens=20,
            temperature=0.3,
        )

        title = response.choices[0].message.content
        if title:
            # Clean up: strip quotes, newlines, extra whitespace
            title = title.strip().strip("\"'").strip()
            # Take first line only
            title = title.split("\n")[0].strip()
            # Strip common model prefixes like "Title:", "Subject:", or markdown bold
            import re

            title = re.sub(r"^(Title|Subject|Topic):?\s*", "", title, flags=re.IGNORECASE)
            title = title.strip("*").strip()
            # Truncate to reasonable length
            if len(title) > 100:
                title = title[:97] + "..."

            if title:
                # Update the thread title
                thread.title = title
                await db.flush()
                logger.info("Auto-titled thread %d: %s", thread_id, title)
                return title

    except BudgetExhausted:
        # Comment 4: a budget gate failure is a hard stop, not a "titling
        # failed, carry on" condition. Propagate so callers can react.
        raise
    except Exception as e:
        logger.warning("Auto-titling failed for thread %d: %s", thread_id, e)

    return None
