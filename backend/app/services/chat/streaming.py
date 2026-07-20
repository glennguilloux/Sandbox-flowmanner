# ─────────────────────────────────────────────────────────────────────────
# Auto-decomposed from app/services/chat_service.py (CARD 3 refactor).
# Part of the `chat` package. Sibling cross-references and original imports
# are preserved so behavior/signatures stay byte-for-byte identical.
# ─────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import socket
import time
from asyncio import timeout as _stream_timeout
from decimal import Decimal
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse

from openai import AsyncOpenAI
from sqlalchemy import func, select

from app.config import settings
from app.models.capability_models import Budget, BudgetExhausted
from app.models.chat import ChatBranch, ChatFile, ChatMessage, ChatThread  # noqa: TC001
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
from app.services.memory_citation_service import (
    build_citation_event,
    build_recall_used_event,
)
from app.services.sse_protocol import _CANVAS_UPDATE_TOOLS, _build_canvas_update

from .byok import _MAX_TOOL_ROUNDS, _lookup_stored_byok_key, _validate_byok_key_matches_model
from .messages import _prepare_step_inject, _process_attachments, create_chat_message, create_chat_message_fresh_session
from .prompts import _inject_web_search
from .threads import get_chat_thread
from .toolcall import (
    _build_chat_messages,
    _execute_tool_call,
    _get_chat_openai_tools,
    _record_tool_cost_fire_and_forget,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.requests import Request

    from app.models.personal_memory_models import PersonalMemoryClaim

logger = logging.getLogger(__name__)

__all__ = [
    "TURN_HARD_CAP_S",
    "_SSE_KEEPALIVE_INTERVAL",
    "_SSE_KEEPALIVE_PING",
    "_STREAM_READ_TIMEOUT",
    "_get_client",
    "_safe_effective_base_url",
    "_safe_fire_and_forget",
    "_sse_keepalive_merge",
    "_sse_keepalive_spawn",
    "_sse_keepalive_timer",
    "_stream_message_to_llm_body",
    "stream_message_to_llm",
]


async def _safe_fire_and_forget(coro, *, label: str) -> None:
    """Wrap a fire-and-forget coroutine so exceptions are logged, not silently dropped."""
    try:
        await coro
    except Exception:
        logger.exception("fire-and-forget task failed: %s", label)


async def _safe_effective_base_url(
    effective_base: str | None,
    default_base_url: str | None,
) -> str | None:
    """SSRF-gate a user/stored ``base_url`` before it reaches AsyncOpenAI.

    Mirrors the validation contract of ``_is_safe_outbound_url`` in
    ``app/api/v1/api_keys.py`` (http/https only; resolved IP must be PUBLIC —
    rejects loopback 127.0.0.0/8, link-local 169.254.0.0/16, reserved,
    multicast, private RFC1918; DNS-rebinding guarded by validating the
    resolved IP, not the literal host). Default-deny: on ANY doubt we fall
    back to the provider/platform ``default_base_url`` and warn — never pass
    an unvalidated, user-controlled URL to an outbound client.

    Returns the URL to actually use (validated ``effective_base`` if safe,
    else ``default_base_url``).
    """
    if not effective_base:
        # No custom URL requested — use the platform default unchanged.
        return default_base_url

    try:
        parsed = urlparse(effective_base)
    except ValueError:
        logger.warning("chat SSRF: base_url %r failed to parse; using platform default", effective_base)
        return default_base_url

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        logger.warning(
            "chat SSRF: base_url scheme %r:// is not allowed; using platform default",
            scheme,
        )
        return default_base_url

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        logger.warning("chat SSRF: base_url %r has no valid hostname; using platform default", effective_base)
        return default_base_url

    # Reject a literal private/loopback/link-local/reserved/multicast IP.
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # Not a literal IP — resolve it below.
        pass
    else:
        if not addr.is_global or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            logger.warning(
                "chat SSRF: base_url host %r is not a public address; using platform default",
                hostname,
            )
            return default_base_url
        return effective_base

    # Hostname: resolve and reject names pointing at non-public ranges.
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError):
        logger.warning(
            "chat SSRF: base_url host %r could not be resolved; using platform default",
            hostname,
        )
        return default_base_url

    if not infos:
        logger.warning(
            "chat SSRF: base_url host %r resolved to no addresses; using platform default",
            hostname,
        )
        return default_base_url

    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            resolved = ipaddress.ip_address(ip_str)
        except ValueError:
            logger.warning(
                "chat SSRF: base_url host %r resolved to invalid address %r; using platform default",
                hostname,
                ip_str,
            )
            return default_base_url
        if (
            not resolved.is_global
            or resolved.is_loopback
            or resolved.is_link_local
            or resolved.is_reserved
            or resolved.is_multicast
        ):
            logger.warning(
                "chat SSRF: base_url host %r resolves to a non-public address %r; using platform default",
                hostname,
                ip_str,
            )
            return default_base_url

    return effective_base


_SSE_KEEPALIVE_INTERVAL = 15  # seconds


_STREAM_READ_TIMEOUT = 90  # seconds without a chunk before we give up


TURN_HARD_CAP_S = 180.0


_SSE_KEEPALIVE_PING = ": ping\n\n"


async def _sse_keepalive_timer(queue: asyncio.Queue, stop_event: asyncio.Event) -> None:
    """Emit `: ping` comments every ``_SSE_KEEPALIVE_INTERVAL`` seconds.

    Runs as a ``BackgroundTaskManager`` task. Pumps ``_SSE_KEEPALIVE_PING``
    into ``queue`` on a fixed cadence until ``stop_event`` is set or cancelled.
    Pure timer — never depends on LLM token cadence.
    """
    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_SSE_KEEPALIVE_INTERVAL)
            except TimeoutError:
                # Interval elapsed without cancellation — emit a keepalive.
                await queue.put(_SSE_KEEPALIVE_PING)
            else:
                # stop_event was set during the wait — exit cleanly.
                break
    except asyncio.CancelledError:
        # Expected on stream teardown; swallow so the manager logs nothing.
        raise


async def _sse_keepalive_merge(
    body: AsyncGenerator[str, None],
    queue: asyncio.Queue,
    stop_event: asyncio.Event,
) -> AsyncGenerator[str, None]:
    """Merge the LLM ``body`` stream with the timer-driven keepalive queue.

    Yields events from ``body`` as they arrive (record = "real activity" →
    reset the keepalive clock), and interleaves ``_SSE_KEEPALIVE_PING`` entries
    from ``queue`` that arrive while the body is idle. The keepalive timer is
    live for the whole stream, so a multi-second tool round still gets pings.
    """
    body_iter = body.__aiter__()
    # One in-flight anext coroutine at a time. Creating a fresh __anext__()
    # while the previous is pending raises "async generator is already running",
    # so we hold the future and only advance after consuming it.
    body_task = asyncio.ensure_future(body_iter.__anext__())
    while True:
        # Wait for the next body event, but wake at least every interval so
        # idle gaps still surface timer pings.
        done, _pending = await asyncio.wait({body_task}, timeout=_SSE_KEEPALIVE_INTERVAL)
        if body_task in done:
            try:
                event = body_task.result()
            except StopAsyncIteration:
                # Body is exhausted. Any ping the timer queued during the final
                # idle gap must NOT be appended after the real last body event,
                # so we break here without draining the queue. The timer is
                # cancelled on generator close.
                break
            # Advance to the next body event for the next iteration.
            body_task = asyncio.ensure_future(body_iter.__anext__())
            yield event
            continue

        # No body event within the interval → this is a genuine idle gap.
        # Surface exactly one queued ping (the timer self-rate-limits to one
        # per interval, but the queue may hold a straggler from a previous gap).
        # We only drain the queue in this branch, so pings never leak after the
        # real last body event.
        try:
            ping = queue.get_nowait()
        except asyncio.QueueEmpty:
            # Timer hasn't fired yet (scheduler jitter); emit the ping directly
            # so the idle gap is still covered even if the queue was drained.
            ping = _SSE_KEEPALIVE_PING
        yield ping


def _sse_keepalive_spawn(queue: asyncio.Queue, stop_event: asyncio.Event) -> asyncio.Task:
    """Spawn the timer-driven SSE keepalive task via ``BackgroundTaskManager``.

    Fires ``: ping`` comments every ``_SSE_KEEPALIVE_INTERVAL`` seconds,
    independent of LLM token cadence (see ``_sse_keepalive_timer``). Returns the
    fire-and-forget ``asyncio.Task`` handle the caller cancels on teardown.

    Extracted as a standalone unit so it can be tested in isolation with a
    mocked ``BackgroundTaskManager``.
    """
    return background_task_manager.spawn(
        _sse_keepalive_timer(queue, stop_event),
        label="sse_keepalive",
    )


async def stream_message_to_llm(
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
    request: Request | None = None,
) -> AsyncGenerator[str, None]:
    """Send a message to the LLM and stream the response via SSE.

    The returned generator drives its own timer-driven keepalive (every 15s,
    independent of token cadence) by spawning a ``BackgroundTaskManager`` task
    and merging its pings with the LLM event stream. The keepalive task is
    cancelled and awaited on generator close so no orphan task leaks.

    If user_api_key is provided, a per-request AsyncOpenAI client is created
    using that key (BYOK path). The key is used only for this call and discarded.
    If model_id is provided it overrides model_preference and the env default.
    If user_base_url is provided, it overrides the resolved base_url for custom providers.
    For llamacpp/* models, any BYOK key is ignored (llama.cpp doesn't use API keys).
    """
    # Lazy import: breaks the streaming<->toolcall circular import at module load.
    from .toolcall import (
        _build_chat_messages,
        _execute_tool_call,
        _get_chat_openai_tools,
        _record_tool_cost_fire_and_forget,
    )

    _keepalive_queue: asyncio.Queue = asyncio.Queue()
    _keepalive_stop = asyncio.Event()
    _keepalive_task = _sse_keepalive_spawn(_keepalive_queue, _keepalive_stop)
    raw_model = model_id or model_preference or _LLM_MODEL
    try:
        try:
            async with asyncio.timeout(TURN_HARD_CAP_S):
                async for event in _sse_keepalive_merge(
                    cast(
                        "AsyncGenerator[str, None]",
                        _stream_message_to_llm_body(
                            db,
                            thread_id,
                            content,
                            user_id,
                            model_preference,
                            user_api_key,
                            user_base_url,
                            model_id,
                            attachments,
                            web_search,
                            request,
                        ),
                    ),
                    _keepalive_queue,
                    _keepalive_stop,
                ):
                    yield event
        except TimeoutError:
            logger.warning(
                "stream_message_to_llm: turn exceeded TURN_HARD_CAP_S=%.0fs for %s",
                TURN_HARD_CAP_S,
                raw_model,
            )
            yield json.dumps(
                {
                    "type": "error",
                    "error": "Response timed out. The model took too long to respond; please try again or pick a faster model.",
                }
            )
    finally:
        _keepalive_stop.set()
        _keepalive_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await _keepalive_task


async def _stream_message_to_llm_body(
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
    request: Request | None = None,
):
    """Send a message to the LLM and stream the response via SSE.

    If user_api_key is provided, a per-request AsyncOpenAI client is created
    using that key (BYOK path). The key is used only for this call and discarded.
    If model_id is provided it overrides model_preference and the env default.
    If user_base_url is provided, it overrides the resolved base_url for custom providers.
    For llamacpp/* models, any BYOK key is ignored (llama.cpp doesn't use API keys).
    """
    # --- Pre-LLM setup: resolve provider, BYOK lookup, build messages ---
    collected_chunks = []
    raw_model = model_id or model_preference or _LLM_MODEL
    base_url, api_key, model = _resolve_provider(raw_model)

    mismatch_error = _validate_byok_key_matches_model(user_api_key, raw_model)
    if mismatch_error:
        yield json.dumps({"type": "error", "error": mismatch_error})
        return

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

    # Comment 4: chat generation requires an explicit budget. The
    # `enforce_budget_before_llm` gate (below) rejects a `None` budget, so we
    # must declare one here rather than pass an undefined/`None` name. Chat is a
    # local, single-call generation path — a generous per-message budget is
    # appropriate; multi-minute/offline mission runs have their own budgets.
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
    # Resolve once before the tool loop so _execute_tool_call doesn't
    # need a DB lookup per tool invocation.
    _cached_user_scopes: set[str] | None = None
    _cached_user_role: str | None = None
    try:
        from app.models.user import User as UserModel

        _urow = (await db.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one_or_none()
        if _urow is not None:
            _cached_user_scopes = set(getattr(_urow, "scopes", []) or [])
            _cached_user_role = getattr(_urow, "role", None)
    except Exception:
        logger.debug("stream_message_to_llm: scope pre-fetch failed (non-fatal)", exc_info=True)

    # ── T33 Stage 1: pre-LLM memory recall + injection ──────
    # Epic 2.2: freeze one recall_for_chat result per session (thread_id)
    # via the snapshot seam, instead of re-calling recall per message.
    # Cache miss -> exactly ONE recall_for_chat (seed query "") + store.
    # Cache hit -> reuse the frozen claims. Write-invalidation / TTL are
    # handled inside the seam. Injection shape below is unchanged.
    memory_recall_claims: list[PersonalMemoryClaim] = []
    if settings.CHAT_MEMORY_CITATIONS_ENABLED:
        thread_for_recall = await get_chat_thread(db, thread_id)
        if thread_for_recall and thread_for_recall.workspace_id:
            try:
                from app.services.memory_snapshot_service import (
                    get_or_capture_snapshot,
                )

                memory_recall_claims = await get_or_capture_snapshot(
                    db,
                    thread_id=thread_id,
                    user_id=user_id,
                    workspace_id=thread_for_recall.workspace_id,
                    # Human chat path → full shared pool (agent_id=None).
                    # Each reviewing agent passes its own id for its restricted
                    # view (Q5-D); the human always gets the complete pool.
                    agent_id=None,
                )
                # Q2-A/Q2-C: resolve the token-bounded, E23-B-ranked set.
                # Tier-0 constraints are protected; Tier-1 competitive claims
                # are dropped lowest-rank-first on overflow. Deterministic
                # (pure function) so the frozen snapshot stays reproducible.
                if memory_recall_claims:
                    from app.services.personal_memory_service import (
                        rank_and_budget_claims,
                    )

                    resolved, _dropped = rank_and_budget_claims(
                        memory_recall_claims,
                        token_budget=settings.CHAT_MEMORY_INJECTION_TOKEN_BUDGET,
                        # Human chat path → no author down-rank (full pool).
                        consumer_agent_id=None,
                    )
                    if _dropped:
                        logger.info(
                            "stream_message_to_llm: memory budget dropped %d claim(s) (kept %d) for thread %s",
                            len(_dropped),
                            len(resolved),
                            thread_id,
                        )
                    memory_recall_claims = resolved
                    if memory_recall_claims:
                        logger.info(
                            "stream_message_to_llm: froze %d memory claims for thread %s",
                            len(memory_recall_claims),
                            thread_id,
                        )
            except Exception as recall_err:
                logger.warning(
                    "stream_message_to_llm: memory recall failed for thread %s, continuing without context: %s",
                    thread_id,
                    recall_err,
                )
                memory_recall_claims = []
        else:
            logger.info(
                "stream_message_to_llm: skipping memory recall for thread %s (workspace_id is null)",
                thread_id,
            )

    if attachments:
        messages_for_llm = await _process_attachments(db, messages_for_llm, attachments, raw_model)

    _prepare_step_injected_events: list[dict] = []
    if getattr(settings, "CHAT_PREPARE_STEP_HOOK_ENABLED", False):
        # Route context injection through the ordered prepareStep closure
        # (mirrors trigger.dev chat.agent prepareStep). Today this runs once
        # pre-LLM (single-shot chat, steps=None). The future re-entrant turn loop
        # will call it at each step boundary with a non-empty steps list +
        # shouldInject gate, matching trigger.dev's step-boundary injection model.
        messages_for_llm, _prepare_step_injected_events = await _prepare_step_inject(
            messages_for_llm,
            memory_claims=memory_recall_claims,
            web_search=bool(web_search),
            content=content,
        )
    else:
        # Legacy inline injection — unchanged behavior when the spike flag is off.
        if memory_recall_claims:
            messages_for_llm = _inject_memory_context(messages_for_llm, memory_recall_claims)
        if web_search:
            messages_for_llm = await _inject_web_search(messages_for_llm, content)

    # Save user message, commit, and immediately close the session to prevent
    # idle-in-transaction timeout during the LLM call
    await create_chat_message(db, thread_id, "user", content, user_id=user_id)
    await db.commit()
    await db.close()

    # Emit injection-receipt events so the frontend can reconcile
    # injected-vs-queued context (only when the prepareStep hook is enabled).
    for _ev in _prepare_step_injected_events:
        yield json.dumps(_ev)

    try:
        async with breaker.protect():
            full_response = ""
            accumulated_prompt_tokens = 0
            accumulated_completion_tokens = 0

            # ── Tool-calling loop ───────────────────────────────────
            for _round in range(_MAX_TOOL_ROUNDS):
                if request is not None and await request.is_disconnected():
                    yield json.dumps({"type": "error", "error": "Client disconnected"})
                    break
                create_kwargs: dict = {
                    "model": model,
                    "messages": messages_for_llm,
                    "stream": True,
                }
                if openai_tools:
                    create_kwargs["tools"] = openai_tools

                # Bound a single LLM turn so weak BYOK models (e.g. tencent-hy3)
                # cannot emit unbounded verbose prose when they narrate a tool
                # call instead of calling it. CHAT_MAX_TOKENS is not defined in
                # settings, so we fall back to 2000.
                create_kwargs["max_tokens"] = getattr(settings, "CHAT_MAX_TOKENS", 2000) or 2000

                # Comment 4: enforce the budget BEFORE the provider call so chat
                # generation cannot blow past the budget silently.
                from app.services.budget_enforcer import enforce_budget_before_llm

                enforce_budget_before_llm(
                    budget,
                    model_id=model,
                    estimated_prompt_tokens=len(messages_for_llm),
                    estimated_completion_tokens=settings.CHAT_MAX_TOKENS
                    if hasattr(settings, "CHAT_MAX_TOKENS")
                    else 2000,
                )
                try:
                    response = await client.chat.completions.create(**create_kwargs)
                    try:
                        # Accumulate streaming chunks — we need to detect both
                        # content tokens AND tool_call deltas in the same stream.
                        round_content_chunks: list[str] = []
                        # tool_calls_by_index tracks partial tool call arguments
                        tool_calls_by_index: dict[int, dict] = {}

                        async with _stream_timeout(_STREAM_READ_TIMEOUT):
                            async for chunk in response:
                                if request is not None and await request.is_disconnected():
                                    yield json.dumps({"type": "error", "error": "Client disconnected"})
                                    break

                                choice = chunk.choices[0] if chunk.choices else None
                                if not choice:
                                    continue

                            delta = choice.delta

                            # Stream text content to the frontend
                            if delta.content:
                                round_content_chunks.append(delta.content)
                                collected_chunks.append(delta.content)
                                yield json.dumps({"type": "token", "content": delta.content})

                            # Accumulate tool calls from streaming deltas
                            if delta.tool_calls:
                                for tc_delta in delta.tool_calls:
                                    idx = tc_delta.index
                                    if idx not in tool_calls_by_index:
                                        tool_calls_by_index[idx] = {
                                            "id": "",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    tc = tool_calls_by_index[idx]
                                    if tc_delta.id:
                                        tc["id"] = tc_delta.id
                                    if tc_delta.function:
                                        if tc_delta.function.name:
                                            tc["function"]["name"] = tc_delta.function.name
                                        if tc_delta.function.arguments:
                                            tc["function"]["arguments"] += tc_delta.function.arguments

                            # Capture usage from streaming chunks (if provider includes it)
                            chunk_usage = getattr(chunk, "usage", None)
                            if chunk_usage and isinstance(getattr(chunk_usage, "prompt_tokens", None), int):
                                accumulated_prompt_tokens += chunk_usage.prompt_tokens or 0
                                accumulated_completion_tokens += chunk_usage.completion_tokens or 0

                            # Detect finish_reason
                            if choice.finish_reason == "tool_calls":
                                break
                    finally:
                        # Release the provider httpx connection on every exit
                        # (normal finish, disconnect, timeout, error) so the
                        # socket is not leaked.
                        with contextlib.suppress(Exception):
                            await response.aclose()
                except TimeoutError:
                    # Provider went silent mid-stream. Surface a clean error so the
                    # client terminates (emits [DONE] via _sse_stream) instead of
                    # hanging on an open connection with an unresolved running step.
                    yield json.dumps(
                        {
                            "type": "error",
                            "error": "The model provider stopped responding mid-response. Please try again.",
                        }
                    )
                    break
                except Exception as _prov_err:  # provider auth/quota/transport failures
                    # A hard provider error (e.g. 401/403 "plan does not include
                    # this model", 429 quota) must become a clean error event + [DONE],
                    # never an unhandled generator crash that leaves the SSE open.
                    _msg = getattr(_prov_err, "message", None) or str(_prov_err)
                    if not isinstance(_msg, str):
                        _msg = str(_prov_err)
                    yield json.dumps(
                        {
                            "type": "error",
                            "error": f"Model provider error: {_msg[:400]}",
                        }
                    )
                    break

                # ── Process tool calls ──────────────────────────────
                if tool_calls_by_index:
                    # Build the assistant message with tool_calls for the history
                    assistant_tool_calls = []
                    for idx in sorted(tool_calls_by_index.keys()):
                        tc = tool_calls_by_index[idx]
                        assistant_tool_calls.append(
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["function"]["name"],
                                    "arguments": tc["function"]["arguments"],
                                },
                            }
                        )

                    # Add assistant message with tool_calls to history
                    messages_for_llm.append(
                        {
                            "role": "assistant",
                            "content": "".join(round_content_chunks) or None,
                            "tool_calls": assistant_tool_calls,
                        }
                    )

                    # Execute each tool and add results to history
                    for tc in assistant_tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = tc["function"]["arguments"]
                        call_id = tc["id"]

                        yield json.dumps(
                            {
                                "type": "tool_call_start",
                                "tool": tool_name,
                                "arguments": tool_args,
                                "call_id": call_id,
                            }
                        )

                        _tool_t0 = time.time()
                        tool_result = await _execute_tool_call(
                            tool_name,
                            tool_args,
                            user_id=user_id,
                            _user_scopes=_cached_user_scopes,
                            _user_role=_cached_user_role,
                        )
                        _record_tool_cost_fire_and_forget(
                            user_id=user_id,
                            tool_name=tool_name,
                            duration_ms=(time.time() - _tool_t0) * 1000.0,
                            workspace_id=_workspace_id,
                        )

                        yield json.dumps(
                            {
                                "type": "tool_call_result",
                                "tool": tool_name,
                                "result": tool_result,
                                "call_id": call_id,
                            }
                        )

                        # ── Phase 4: canvas_update for agent-driven tile orchestration ──
                        # When a tool produces a result that should open a canvas tile
                        # (e.g. browser_sandbox launch), emit a canvas_update event so
                        # the frontend can auto-open the tile without user action.
                        _canvas_event = _build_canvas_update(tool_name, tool_result)
                        if _canvas_event:
                            yield json.dumps(_canvas_event)

                        messages_for_llm.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": tool_result,
                            }
                        )

                    # The timer-driven keepalive (spawned on stream entry) covers
                    # the long idle gap during tool execution independent of token
                    # cadence, so no yield-gated ping is needed here.

                    # Loop back for the next LLM call with tool results
                    continue

                # No tool calls — we have a final text response
                full_response = "".join(round_content_chunks) or "".join(collected_chunks)
                break  # Exit the tool-calling loop

            else:
                # Loop exhausted — all rounds were tool calls
                full_response = "".join(collected_chunks) or (
                    "I reached the maximum number of tool calls "
                    f"({_MAX_TOOL_ROUNDS}) without producing a final response."
                )

            # Fallback: some providers return 0 streaming chunks even
            # though non-streaming works fine.
            if not full_response.strip():
                logger.info(
                    "stream_message_to_llm: empty stream for %s, retrying without streaming",
                    raw_model,
                )
                try:
                    non_stream_kwargs: dict = {
                        "model": model,
                        "messages": messages_for_llm,
                    }
                    if openai_tools:
                        non_stream_kwargs["tools"] = openai_tools
                    try:
                        async with _stream_timeout(_STREAM_READ_TIMEOUT):
                            non_stream_response = await client.chat.completions.create(**non_stream_kwargs)
                    except Exception as e:
                        logger.error(
                            "stream_message_to_llm: non-streaming fallback timed out for %s: %s",
                            raw_model,
                            e,
                        )
                        non_stream_response = None
                    if non_stream_response and non_stream_response.choices:
                        full_response = non_stream_response.choices[0].message.content or ""
                    # Second fallback: retry without tools if still empty
                    # (some models don't support function calling)
                    if not full_response.strip() and openai_tools:
                        logger.info(
                            "stream_message_to_llm: empty response with tools for %s, retrying without tools",
                            raw_model,
                        )
                        non_stream_kwargs.pop("tools", None)
                        try:
                            async with _stream_timeout(_STREAM_READ_TIMEOUT):
                                no_tools_response = await client.chat.completions.create(**non_stream_kwargs)
                        except Exception as e:
                            logger.error(
                                "stream_message_to_llm: non-streaming no-tools fallback timed out for %s: %s",
                                raw_model,
                                e,
                            )
                            no_tools_response = None
                        if no_tools_response and no_tools_response.choices:
                            full_response = no_tools_response.choices[0].message.content or ""
                    if full_response:
                        yield json.dumps({"type": "token", "content": full_response})
                except Exception as retry_err:
                    logger.error(
                        "stream_message_to_llm: non-streaming retry also failed for %s: %s",
                        raw_model,
                        retry_err,
                    )
                # Both fallbacks exhausted with no content — emit a clean error
                # event so _sse_stream still terminates with [DONE].
                if not full_response.strip():
                    yield json.dumps(
                        {"type": "error", "error": "The model returned no content and the fallback request timed out."}
                    )

        # Use actual token counts if available from streaming, else estimate
        prompt_tokens = accumulated_prompt_tokens or len(content.split())
        completion_tokens = accumulated_completion_tokens or len(full_response.split())
        total_tokens = prompt_tokens + completion_tokens

        llm_duration = time.time() - llm_start
        record_llm_request(
            provider=provider_name,
            duration_seconds=llm_duration,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            success=True,
        )

        # Session was closed before LLM call to prevent idle-in-transaction timeout.
        # Always use fresh session for saving.

        assistant_msg: ChatMessage | None = None
        # Save with retry (3 attempts, exponential backoff)
        assistant_msg = None
        for _attempt in range(3):
            try:
                assistant_msg = await create_chat_message_fresh_session(thread_id, "assistant", full_response)
                break
            except Exception as save_err:
                logger.warning("stream: assistant message save attempt %d failed: %s", _attempt + 1, save_err)
                if _attempt < 2:
                    await asyncio.sleep(0.5 * (2**_attempt))
        if assistant_msg is None:
            logger.error("stream: assistant message save failed after 3 attempts")
            save_failed_payload = json.dumps({"type": "save_failed", "content": full_response[:500]})
            # Phase 2c.3: emit bare JSON — the outer SSE wrapper frames it
            # with "data: ". Prefixing here double-frames the event.
            yield save_failed_payload

        # ── T33 Stage 1: emit memory_recall_used events for cited claims ──
        # Emitted AFTER the assistant message is persisted so the frontend
        # can attach the recall metadata to the right message. Skipped when
        # the save failed because there's no message_id to attach to.
        if assistant_msg is not None:
            for claim in memory_recall_claims:
                yield json.dumps(build_recall_used_event(claim, message_id=str(assistant_msg.id)))

        # ── T33 Stage 2: emit memory_citation events for the chip UI ──
        # Same ordered list as the recall-used events above. The frontend
        # renders one <MemoryCitationChip> per memory_citation event.
        # The bracket label is built in the service (format_citation_label)
        # so the chip displays the locked format verbatim.
        if assistant_msg is not None:
            for claim in memory_recall_claims:
                yield json.dumps(build_citation_event(claim, message_id=str(assistant_msg.id)))

        # ── P0-1: durable memory extraction via Celery ────────────────
        try:
            from app.tasks.memory_extraction_tasks import extract_memory_claims_task

            extract_memory_claims_task.delay(
                thread_id=thread_id,
                user_id=user_id,
                user_message=content,
                assistant_response=full_response,
            )
        except Exception:
            logger.debug("memory_extraction Celery dispatch failed (non-fatal)", exc_info=True)

        try:
            from app.services.usage_service import get_usage_service

            get_usage_service().record_usage(
                user_id=str(user_id),
                model_id=model,
                provider="byok" if effective_user_key else "system",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=total_tokens * 0.000002,
            )
        except Exception as ue:
            logger.warning("Usage recording failed (non-fatal): %s", ue)

        yield json.dumps(
            {
                "type": "complete",
                "full_response": full_response,
                "message_id": assistant_msg.id if assistant_msg is not None else None,
                "model": model,
            }
        )

    except CircuitOpenError as e:
        llm_duration = time.time() - llm_start
        record_llm_request(provider=provider_name, duration_seconds=llm_duration, success=False)
        logger.warning("Circuit breaker open for %s: %s", provider_name, e)
        yield json.dumps(
            {
                "type": "error",
                "error": f"Service temporarily unavailable ({provider_name}). Please try again later.",
            }
        )
    except Exception as e:
        llm_duration = time.time() - llm_start
        record_llm_request(provider=provider_name, duration_seconds=llm_duration, success=False)
        logger.error("stream_message_to_llm failed: %s", e)
        yield json.dumps({"type": "error", "error": str(e)})


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Return the shared default OpenAI client, constructing it on first use.

    Lazily builds the module-level singleton so importing this module never
    requires credentials. Raises OpenAIError at call time (not import time) if
    no key is configured — which is the correct place for that failure.
    """
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=_LLM_API_KEY,
            base_url=_LLM_API_BASE,
        )
    return _client
