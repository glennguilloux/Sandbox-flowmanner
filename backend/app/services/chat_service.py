from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import func, select

from app.models.chat import ChatBranch, ChatFile, ChatMessage, ChatThread
from app.models.phase4_models import UserFile

logger = logging.getLogger(__name__)

from datetime import UTC
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PROVIDER_MAP = {
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "zhipuai": ("https://open.bigmodel.cn/api/paas/v4", "ZHIPUAI_API_KEY"),
    "llamacpp": (f"{settings.LLAMACPP_URL}/v1", None),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
    "deepinfra": ("https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "google": ("https://generativelanguage.googleapis.com/v1beta", "GOOGLE_API_KEY"),
    "openai_compatible": ("https://api.openai.com/v1", None),
    "glennguilloux": ("https://ai.glennguilloux.com:9443/v1", None),
}

OPENAI_PROVIDER_FAMILIES = frozenset(("openai", "openai_compatible"))


def _normalize_provider(provider: str) -> str:
    """Normalize provider name to canonical form.

    Handles both underscore and hyphen variants:
    - openai_compatible -> openai_compatible
    - openai-compatible -> openai_compatible
    - openai -> openai
    """
    if not provider:
        return provider
    return provider.lower().replace("-", "_")


def _get_base_url_for_provider(provider: str) -> str:
    """Get base URL for a normalized provider."""
    normalized = _normalize_provider(provider)

    if normalized == "openai_compatible":
        return "https://api.openai.com/v1"

    base_url, _ = PROVIDER_MAP.get(normalized, (None, None))
    if base_url:
        return base_url

    return _LLM_API_BASE


def _get_provider_for_model(model_id: str) -> str | None:
    """Extract normalized provider from model ID (e.g., 'llamacpp/qwen' -> 'llamacpp')."""
    if "/" not in model_id:
        return None
    return _normalize_provider(model_id.split("/", 1)[0])


def _get_upstream_model_name(model_id: str) -> str:
    """Extract the upstream model name to send to the API.

    Strips provider prefix but preserves nested paths:
    - openai/gpt-4o-mini -> gpt-4o-mini
    - openai_compatible/gpt-4o-mini-2024-07-18 -> gpt-4o-mini-2024-07-18
    - openai-compatible/gpt-4o-mini -> gpt-4o-mini
    - openrouter/anthropic/claude-3.5-sonnet -> anthropic/claude-3.5-sonnet
    - gpt-4o-mini -> gpt-4o-mini (no prefix)
    """
    if "/" not in model_id:
        return model_id
    return model_id.split("/", 1)[1]


def _resolve_provider(model_id: str) -> tuple[str, str, str]:
    """Resolve provider details for a model ID.

    Returns (base_url, api_key, upstream_model_name)
    """
    upstream_model = _get_upstream_model_name(model_id)
    provider = _get_provider_for_model(model_id)

    if not provider:
        return _LLM_API_BASE, _LLM_API_KEY, upstream_model

    normalized = _normalize_provider(provider)

    if normalized == "openai_compatible":
        return "https://api.openai.com/v1", None, upstream_model

    base_url, key_env = PROVIDER_MAP.get(normalized, (None, None))
    if not base_url:
        return _LLM_API_BASE, _LLM_API_KEY, upstream_model

    api_key = os.getenv(key_env) if key_env else "not-needed"
    return base_url, api_key, upstream_model


def _detect_provider_from_key(api_key: str) -> str | None:
    """Detect provider from BYOK key format.

    Covers distinct key-prefix families across 11 providers.
    Generic / ambiguous prefixes return None (no mismatch enforced).
    """
    if not api_key:
        return None
    key_lower = api_key.lower()
    if key_lower.startswith("sk-or-"):
        return "openrouter"
    if key_lower.startswith("sk-ds-"):
        return "deepseek"
    if key_lower.startswith("sk-ant-"):
        return "anthropic"
    if key_lower.startswith("sk-proj-"):
        return "openai"
    if key_lower.startswith("aiza"):
        return "google"
    if key_lower.startswith("gsk_"):
        return "groq"
    if key_lower.startswith("fw_"):
        return "fireworks"
    if key_lower.startswith("xai-"):
        return "xai"
    # Generic "sk-" is shared by OpenAI, Together, DeepInfra, and others.
    # Returning None avoids false mismatch errors.
    return None


def _providers_compatible(key_provider: str | None, model_provider: str | None) -> bool:
    """Check if a key provider is compatible with a model provider family."""
    if not key_provider or not model_provider:
        return True
    key_p = _normalize_provider(key_provider)
    model_p = _normalize_provider(model_provider) if model_provider else None
    if not model_p:
        return True
    if model_p in ("llamacpp", "ollama"):
        return True
    if key_p == model_p:
        return True
    return bool(
        model_p in OPENAI_PROVIDER_FAMILIES and key_p in OPENAI_PROVIDER_FAMILIES
    )


async def _lookup_stored_byok_key(
    db: AsyncSession,
    user_id: int,
    provider_hint: str | None = None,
) -> tuple[str | None, str | None]:
    """Look up the best stored BYOK key for a user.

    Returns (api_key, base_url) or (None, None) if no key found.
    If provider_hint is given, prefers a key whose provider matches.
    Falls back to any active key if no provider match.
    """
    logger.debug("BYOK lookup: user=%s provider=%s", user_id, provider_hint)
    try:
        from sqlalchemy import select

        from app.models.byok_models import UserAPIKey

        stmt = (
            select(UserAPIKey)
            .where(UserAPIKey.user_id == user_id)
            .where(UserAPIKey.is_active == True)
        )
        result = await db.execute(stmt)
        keys = list(result.scalars().all())
        if not keys:
            return None, None

        # Prefer a key whose provider matches the hint
        if provider_hint:
            normalized_hint = _normalize_provider(provider_hint)
            for k in keys:
                if _normalize_provider(k.provider) == normalized_hint:
                    logger.info(
                        "BYOK lookup FOUND: user=%s provider=%s key_id=%s",
                        user_id,
                        provider_hint,
                        k.id,
                    )
                    return k.get_api_key(), k.base_url

            # No provider match found — do NOT fall back to a random key.
            # Returning a key for the wrong provider causes 400 errors
            # (e.g. sending demo-llm to OpenRouter instead of glennguilloux).
            logger.info(
                "BYOK lookup NO MATCH: user=%s provider=%s available=%s",
                user_id,
                provider_hint,
                [k.provider for k in keys],
            )
            return None, None

        # Fall back to the first active key
        logger.debug(
            "BYOK lookup FALLBACK: user=%s provider=%s -> using first key key_id=%s",
            user_id,
            provider_hint,
            keys[0].id,
        )
        return keys[0].get_api_key(), keys[0].base_url
    except Exception:
        logger.warning(
            "BYOK lookup ERROR: user=%s provider=%s",
            user_id,
            provider_hint,
            exc_info=True,
        )
        return None, None


def _validate_byok_key_matches_model(
    user_api_key: str | None, model_id: str
) -> str | None:
    """Validate that BYOK key matches the requested model provider.

    Returns None if valid.
    Returns error message if mismatch:
    - For llamacpp/*: always valid (ignore key)
    - For openai_compatible/*: accept any OpenAI-family key or unknown keys
    - For other providers: check if key matches model provider
    """
    if not user_api_key or not model_id:
        return None

    model_provider = _get_provider_for_model(model_id)

    if model_provider == "llamacpp":
        return None

    key_provider = _detect_provider_from_key(user_api_key)

    if not _providers_compatible(key_provider, model_provider):
        return f"Provider mismatch: model '{model_id}' requires {model_provider.title()}, but X-User-API-Key appears to be for {key_provider.title()}"

    return None


# Sandboxd preview guidance appended to system prompt when enabled
_SANDBOXD_SYSTEM_GUIDANCE = """

## Live Preview Tools (sandboxd)

When the user asks you to build something visual (landing page, dashboard,
chart, tool, app, or any HTML/CSS/JS project), use the sandboxd tools to
create a live preview. Follow this workflow **exactly**:

1. **sandboxd_preview** — call with `{}` (no arguments) to create a new sandbox.
   Save the returned `sandbox_id` for ALL subsequent calls.
2. **sandboxd_file_write** — write your files. Pass `sandbox_id` and `path` and `content`.
   Example: `{"sandbox_id": "...", "path": "index.html", "content": "<!DOCTYPE html>..."}`
   Subdirectories are created automatically (e.g. `"css/style.css"` works fine).
   Write ALL files before calling sandboxd_serve.
3. **sandboxd_serve** — start the dev server and get the preview URL:
   `{"sandbox_id": "..."}`
   This starts a server on port 3000 that serves from the sandbox workspace
   directory where your files were written. Returns the preview URL directly.
   That's it — 3 tool calls total.
4. **sandboxd_file_read** — read a file back: `{"sandbox_id": "...", "path": "index.html"}`
5. **sandboxd_file_list** — list workspace files: `{"sandbox_id": "...", "path": ""}`

If you need to run custom commands (npm install, python scripts, etc.), use
**sandboxd_exec** with the `command` field (argv array).

The preview URL format is:
https://s-<sandbox_id>-3000.preview.flowmanner.com

The URL is publicly accessible. The sandbox stays alive for 35 minutes.

If any tool returns an error containing "container is not running" or
"not running", do NOT retry more than once — explain the error to the user."""

# Maximum number of tool-call rounds before forcing a text response
_MAX_TOOL_ROUNDS = settings.CHAT_MAX_TOOL_ROUNDS


# LLM configuration from environment
_LLM_API_KEY = os.getenv("LLM_API_KEY")
_LLM_API_BASE = (
    os.getenv("LLM_API_BASE")
    or os.getenv("LLM_BASE_URL")
    or "https://api.deepseek.com/v1"
)
_LLM_MODEL = os.getenv("LLM_MODEL_NAME", "deepseek/deepseek-v4-flash")

# Initialize AsyncOpenAI client for ZhipuAI (OpenAI-compatible)
_client = AsyncOpenAI(
    api_key=_LLM_API_KEY,
    base_url=_LLM_API_BASE,
)


def _resolve_model(model_preference: str | None = None) -> str:
    """Resolve model name. Strip any provider prefix for direct API calls."""
    model = model_preference or _LLM_MODEL
    # Strip provider prefix if present (e.g. "openai/glm-4-plus" -> "glm-4-plus")
    if "/" in model:
        model = model.split("/", 1)[1]
    return model


async def create_chat_thread(
    db: AsyncSession,
    user_id: int,
    username: str,
    title: str,
    model_preference: str | None = None,
    workspace_id: str | None = None,
) -> ChatThread:
    metadata = {"model_preference": model_preference} if model_preference else None
    thread = ChatThread(
        title=title,
        user_id=user_id,
        username=username,
        metadata_=metadata,
        workspace_id=workspace_id,
    )
    db.add(thread)
    await db.flush()
    await db.refresh(thread)
    return thread


async def get_chat_thread(db: AsyncSession, thread_id: int) -> ChatThread | None:
    result = await db.execute(select(ChatThread).where(ChatThread.id == thread_id))
    return result.scalar_one_or_none()


async def require_chat_thread_access(
    db: AsyncSession,
    thread_id: int,
    user_id: int,
) -> ChatThread:
    """Fetch a chat thread and verify the user has access.

    Access rules:
    1. If the thread has a workspace_id → verify the user is an active member
       of that workspace.
    2. If the thread has no workspace_id → fall back to user_id ownership.
    3. If the thread doesn't exist → 404.
    """
    from fastapi import HTTPException

    thread = await get_chat_thread(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Not found")

    if thread.workspace_id:
        from app.models.workspace_models import WorkspaceMember

        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == thread.workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.is_active == True,
            )
        )
        if result.scalar_one_or_none() is None:
            # Check cross-workspace grants across all user's workspaces
            from app.services.cross_workspace_service import (
                check_entity_access,
                find_user_workspaces,
            )

            user_workspaces = await find_user_workspaces(db, user_id)
            has_cross_access = False
            for ws_id in user_workspaces:
                if ws_id == thread.workspace_id:
                    continue
                grant = await check_entity_access(
                    db,
                    user_id=user_id,
                    target_workspace_id=ws_id,
                    entity_type="chat_thread",
                    entity_id=str(thread_id),
                    required_permission="read",
                )
                if grant:
                    has_cross_access = True
                    break
            if not has_cross_access:
                logger.warning(
                    "entity_access_denied"
                    " user_id=%s entity_type=chat_thread entity_id=%s"
                    " workspace_id=%s reason=no_membership",
                    user_id,
                    thread_id,
                    thread.workspace_id,
                )
                try:
                    import asyncio

                    from app.api.middleware.audit import log_event

                    asyncio.create_task(
                        log_event(
                            user_id=user_id,
                            action="entity.access_denied",
                            details={
                                "entity_type": "chat_thread",
                                "entity_id": str(thread_id),
                                "workspace_id": str(thread.workspace_id),
                                "reason": "no_membership",
                            },
                        )
                    )
                except Exception:
                    pass
                raise HTTPException(status_code=404, detail="Not found")
    else:
        if thread.user_id != user_id:
            logger.warning(
                "entity_access_denied"
                " user_id=%s entity_type=chat_thread entity_id=%s"
                " owner_user_id=%s reason=owner_mismatch",
                user_id,
                thread_id,
                thread.user_id,
            )
            try:
                import asyncio

                from app.api.middleware.audit import log_event

                asyncio.create_task(
                    log_event(
                        user_id=user_id,
                        action="entity.access_denied",
                        details={
                            "entity_type": "chat_thread",
                            "entity_id": str(thread_id),
                            "reason": "owner_mismatch",
                        },
                    )
                )
            except Exception:
                pass
            raise HTTPException(status_code=404, detail="Not found")

    return thread


async def list_chat_threads(
    db: AsyncSession,
    user_id: int,
    *,
    offset: int = 0,
    limit: int = 20,
    workspace_id: str | None = None,
) -> tuple[list[ChatThread], int]:
    base_filter = (
        ChatThread.workspace_id == workspace_id
        if workspace_id is not None
        else ChatThread.user_id == user_id
    )
    count_q = select(func.count()).select_from(ChatThread).where(base_filter)
    total = (await db.execute(count_q)).scalar() or 0
    items_q = (
        select(ChatThread)
        .where(base_filter)
        .order_by(ChatThread.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list((await db.execute(items_q)).scalars().all())
    return items, total


async def update_chat_thread(
    db: AsyncSession,
    thread_id: int,
    *,
    title: str | None = None,
    is_archived: bool | None = None,
) -> ChatThread | None:
    thread = await get_chat_thread(db, thread_id)
    if thread is None:
        return None
    if title is not None:
        thread.title = title
    if is_archived is not None:
        thread.is_archived = is_archived
    await db.flush()
    await db.refresh(thread)
    return thread


async def delete_chat_thread(db: AsyncSession, thread_id: int) -> bool:
    thread = await get_chat_thread(db, thread_id)
    if thread is None:
        return False
    await db.delete(thread)
    await db.flush()
    return True


async def create_chat_message(
    db: AsyncSession,
    thread_id: int,
    role: str,
    content: str,
    *,
    user_id: int | None = None,
) -> ChatMessage:
    msg = ChatMessage(thread_id=thread_id, role=role, content=content)
    if user_id is not None:
        msg.user_id = user_id
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def create_chat_message_fresh_session(
    thread_id: int,
    role: str,
    content: str,
    *,
    user_id: int | None = None,
) -> ChatMessage:
    """Create a chat message using a fresh DB session.

    Used as a fallback when the caller's session has a dead connection
    (e.g. after long LLM streaming where idle-in-transaction kills the
    underlying asyncpg connection).  The session is committed by the
    context manager on successful exit.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as fresh_db:
        msg = ChatMessage(thread_id=thread_id, role=role, content=content)
        if user_id is not None:
            msg.user_id = user_id
        fresh_db.add(msg)
        await fresh_db.flush()
        await fresh_db.refresh(msg)
        return msg


async def update_chat_message(
    db: AsyncSession,
    message_id: int,
    content: str,
) -> ChatMessage | None:
    """Update a chat message's content and set edited_at timestamp."""
    from datetime import datetime

    result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    message = result.scalar_one_or_none()
    if message is None:
        return None
    message.content = content
    message.edited_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(message)
    return message


async def delete_chat_message(db: AsyncSession, message_id: int) -> bool:
    """Delete a chat message by ID."""
    result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    message = result.scalar_one_or_none()
    if message is None:
        return False
    await db.delete(message)
    await db.flush()
    return True


async def get_chat_messages(
    db: AsyncSession,
    thread_id: int,
    *,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[ChatMessage], int]:
    count_q = (
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
    )
    total = (await db.execute(count_q)).scalar() or 0
    items_q = (
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    items = list((await db.execute(items_q)).scalars().all())
    return items, total


async def get_chat_files(
    db: AsyncSession,
    thread_id: int,
) -> list[ChatFile]:
    result = await db.execute(select(ChatFile).where(ChatFile.chat_id == thread_id))
    return list(result.scalars().all())


async def create_chat_file(
    db: AsyncSession,
    thread_id: int,
    filename: str,
    mime_type: str,
    path: str,
    size_bytes: int,
) -> ChatFile:
    file = ChatFile(
        chat_id=thread_id,
        filename=filename,
        mime_type=mime_type,
        path=path,
        size_bytes=size_bytes,
    )
    db.add(file)
    await db.flush()
    await db.refresh(file)
    return file


def _get_model_preference(thread: ChatThread) -> str | None:
    if thread.metadata_ and isinstance(thread.metadata_, dict):
        return thread.metadata_.get("model_preference")
    return None


async def _process_attachments(
    db: AsyncSession, messages: list[dict], attachments: list[dict], model: str
) -> list[dict]:
    is_vision_model = not model.startswith("llamacpp/")

    for att in attachments:
        file_id = att.get("file_id", "")
        att_type = att.get("type", "file")
        filename = att.get("filename", "unknown")

        result = await db.execute(select(UserFile).where(UserFile.id == file_id))
        db_file = result.scalar_one_or_none()
        if (
            not db_file
            or not db_file.storage_path
            or not os.path.exists(db_file.storage_path)
        ):
            continue

        if att_type == "image" and is_vision_model:
            raw_bytes = Path(db_file.storage_path).read_bytes()
            b64 = base64.b64encode(raw_bytes).decode("utf-8")
            content_type = db_file.content_type or "image/png"

            if messages and messages[-1].get("role") == "user":
                existing = messages[-1].get("content", "")
                if isinstance(existing, str):
                    messages[-1]["content"] = [
                        {"type": "text", "text": existing},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{content_type};base64,{b64}"},
                        },
                    ]
                else:
                    messages[-1]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{content_type};base64,{b64}"},
                        }
                    )

        elif att_type == "image" and not is_vision_model:
            if messages and messages[-1].get("role") == "user":
                existing = messages[-1].get("content", "")
                if isinstance(existing, str):
                    messages[-1]["content"] = f"{existing}\n\n[Image: {filename}]"

        elif att_type == "file":
            try:
                content_type = (db_file.content_type or "").lower()
                filename_lower = (db_file.filename or "").lower()

                if "pdf" in content_type:
                    import pdfplumber

                    with pdfplumber.open(db_file.storage_path) as pdf:
                        pages_text = []
                        for page in pdf.pages:
                            t = page.extract_text() or ""
                            pages_text.append(t)
                        file_text = "\n\n".join(pages_text)

                elif (
                    "wordprocessingml" in content_type
                    or ".docx" in filename_lower
                    or "msword" in content_type
                ):
                    from docx import Document

                    doc = Document(db_file.storage_path)
                    file_text = "\n".join(p.text for p in doc.paragraphs)

                elif (
                    "spreadsheetml" in content_type
                    or ".xlsx" in filename_lower
                    or "excel" in content_type
                ):
                    import openpyxl

                    wb = openpyxl.load_workbook(
                        db_file.storage_path, read_only=True, data_only=True
                    )
                    rows = []
                    for sheet in wb.sheetnames:
                        ws = wb[sheet]
                        sheet_rows = []
                        for row in ws.iter_rows(values_only=True):
                            line = "\t".join(
                                str(c) if c is not None else "" for c in row
                            )
                            sheet_rows.append(line)
                        rows.append(f"=== Sheet: {sheet} ===\n" + "\n".join(sheet_rows))
                    file_text = "\n\n".join(rows)
                    wb.close()

                elif (
                    "presentationml" in content_type
                    or ".pptx" in filename_lower
                    or "powerpoint" in content_type
                ):
                    from pptx import Presentation

                    prs = Presentation(db_file.storage_path)
                    slides_text = []
                    for i, slide in enumerate(prs.slides, 1):
                        slide_texts = []
                        for shape in slide.shapes:
                            if shape.has_text_frame:
                                slide_texts.append(shape.text)
                            elif shape.has_table:
                                table = shape.table
                                slide_texts.extend(
                                    "\t".join(cell.text for cell in row.cells)
                                    for row in table.rows
                                )
                        slides_text.append(
                            f"=== Slide {i} ===\n" + "\n".join(slide_texts)
                        )
                    file_text = "\n\n".join(slides_text)

                else:
                    file_text = Path(db_file.storage_path).read_text(
                        encoding="utf-8", errors="replace"
                    )
            except Exception:
                continue
            limit = 10000
            truncated = file_text[:limit]
            if len(file_text) > limit:
                truncated += "\n... (truncated)"
            context_msg = (
                f"[Attached file: {filename}]\n{truncated}\n[End of attached file]"
            )
            messages.insert(-1, {"role": "user", "content": context_msg})

    return messages


async def _inject_web_search(messages: list[dict], query: str) -> list[dict]:
    try:
        from app.services.web_search.models import SearchConfig
        from app.services.web_search.service_enhanced import EnhancedWebSearchService

        config = SearchConfig(
            duckduckgo_enabled=True,
            searxng_enabled=True,
            searxng_url="http://searxng:8080",
        )
        service = EnhancedWebSearchService(config)
        # Extract key search terms for better results
        search_query = query
        for prefix in [
            "what is",
            "what's",
            "what are",
            "tell me",
            "can you",
            "do you know",
            "how much is",
            "how much does",
            "current",
            "latest",
            "find",
            "search",
        ]:
            if search_query.lower().startswith(prefix):
                search_query = search_query[len(prefix) :].strip(" ?!,.;:")
                break
        if not search_query.strip():
            search_query = query
        search_result = await service.search(
            query=search_query,
            max_results=5,
            use_cache=False,
            use_reranking=False,
            use_query_understanding=False,
        )

        results = search_result.get("results", [])
        if not results:
            return messages

        lines = [
            "IMPORTANT: The following web search results contain CURRENT, FACTUAL information.",
            f'Use these results to answer the user\'s question about: "{query}"',
            "Do NOT say you lack access to live data — you have the data right here.",
            "If the results contain a price, date, or figure, cite it directly.",
            "",
            "Search results:",
        ]
        for i, r in enumerate(results[:5], 1):
            if isinstance(r, dict):
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("snippet", r.get("content", ""))[:200]
            else:
                title = getattr(r, "title", "Untitled") or "Untitled"
                url = getattr(r, "url", "") or ""
                snippet = (
                    getattr(r, "snippet", "") or getattr(r, "content", "") or ""
                )[:200]
            lines.append(f"{i}. {title} — {url}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")

        search_context = "\n".join(lines)
        # Append search results to the last user message so the model can't ignore them
        messages[-1][
            "content"
        ] = f"{search_context}\n\nBased on the search results above, answer the following:\n{messages[-1]['content']}"

    except Exception as e:
        logger.warning("Web search failed (non-fatal): %s", e)

    return messages


async def _build_chat_messages(
    db: AsyncSession,
    thread_id: int,
    max_history: int = 20,
) -> list[dict]:
    # Build the messages array for the LLM including conversation history.
    # Fetches the last max_history messages from the thread and includes them
    # in the prompt. Uses the thread custom system prompt if available.
    thread = await get_chat_thread(db, thread_id)

    system_prompt = "You are a helpful assistant."
    if thread and thread.metadata_ and isinstance(thread.metadata_, dict):
        custom = thread.metadata_.get("system_prompt", "")
        if custom and custom.strip():
            system_prompt = custom

    # Append sandboxd preview guidance when sandboxd is enabled
    if settings.SANDBOXD_ENABLED:
        system_prompt += _SANDBOXD_SYSTEM_GUIDANCE

    messages = [{"role": "system", "content": system_prompt}]

    history_stmt = (
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.id.desc())
        .limit(max_history)
    )
    history_result = await db.execute(history_stmt)
    recent_messages = list(reversed(history_result.scalars().all()))

    messages.extend(
        {"role": msg.role, "content": msg.content}
        for msg in recent_messages
        if msg.role in ("user", "assistant")
    )

    return messages


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
) -> dict:
    """Send a message to the LLM and get a non-streaming response.

    If user_api_key is provided, a per-request AsyncOpenAI client is created
    using that key (BYOK path). The key is used only for this call and discarded.
    If model_id is provided it overrides model_preference and the env default.
    If user_base_url is provided, it overrides the resolved base_url for custom providers.
    For llamacpp/* models, any BYOK key is ignored (llama.cpp doesn't use API keys).
    """
    await create_chat_message(db, thread_id, "user", content, user_id=user_id)
    # Commit the user message immediately so the transaction is released.
    # During the long LLM call (minutes with tool-calls), the connection
    # would otherwise sit idle-in-transaction and get killed by PostgreSQL's
    # idle_in_transaction_session_timeout.
    await db.commit()

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
        stored_key, stored_base = await _lookup_stored_byok_key(
            db, user_id, provider_hint=model_provider
        )
        if stored_key:
            effective_user_key = stored_key
            effective_base_url = stored_base

    if raw_model and raw_model.startswith("llamacpp/"):
        effective_user_key = None

    if effective_user_key:
        effective_base = effective_base_url or base_url
        client = AsyncOpenAI(api_key=effective_user_key, base_url=effective_base)
    elif base_url != _LLM_API_BASE or api_key != _LLM_API_KEY:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    else:
        client = _client

    # Circuit breaker protection
    from app.core.circuit_breaker import CircuitOpenError, get_circuit_breaker
    from app.core.metrics import record_llm_request

    provider_name = _get_provider_for_model(raw_model) or "deepseek"
    breaker = get_circuit_breaker(provider_name)
    llm_start = time.time()

    try:
        openai_tools = _get_chat_openai_tools()

        async with breaker.protect():
            messages_for_llm = await _build_chat_messages(db, thread_id)

            if attachments:
                messages_for_llm = await _process_attachments(
                    db, messages_for_llm, attachments, raw_model
                )

            if web_search:
                messages_for_llm = await _inject_web_search(messages_for_llm, content)

            # ── Tool-calling loop (non-streaming) ───────────────────
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_total_tokens = 0

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
                        tool_result = await _execute_tool_call(
                            tc.function.name, tc.function.arguments
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
                no_tools_response = await client.chat.completions.create(
                    model=model, messages=messages_for_llm
                )
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

        try:
            await create_chat_message(db, thread_id, "assistant", assistant_content)
        except Exception as save_err:
            # Catch broad Exception: asyncpg.InterfaceError, sqlalchemy.InterfaceError,
            # OperationalError etc.  Validation/constraint errors will also fail on
            # the fresh session, so the retry is safe (no silent data corruption).
            logger.warning(
                "Assistant message save failed on original session (%s), retrying with fresh session",
                save_err,
            )
            await create_chat_message_fresh_session(
                thread_id, "assistant", assistant_content
            )

        try:
            from app.services.usage_service import get_usage_service

            get_usage_service().record_usage(
                user_id=str(user_id),
                model_id=model,
                provider="byok" if user_api_key else "system",
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                cost=total_total_tokens * 0.000002,
            )
        except Exception as ue:
            logger.warning("Usage recording failed (non-fatal): %s", ue)

        return {
            "success": True,
            "content": assistant_content,
            "tokens": total_total_tokens,
            "model": model,
        }
    except CircuitOpenError as e:
        llm_duration = time.time() - llm_start
        record_llm_request(
            provider=provider_name, duration_seconds=llm_duration, success=False
        )
        logger.warning("Circuit breaker open for %s: %s", provider_name, e)
        return {
            "success": False,
            "content": f"Service temporarily unavailable ({provider_name}). Please try again later.",
            "tokens": 0,
            "model": model,
        }
    except Exception as e:
        llm_duration = time.time() - llm_start
        record_llm_request(
            provider=provider_name, duration_seconds=llm_duration, success=False
        )
        logger.error("send_message_to_llm failed: %s", e)
        return {"success": False, "content": str(e), "tokens": 0, "model": model}


def _get_chat_openai_tools() -> list[dict] | None:
    """Return sandboxd tools in OpenAI function-calling format, or None if disabled."""
    if not settings.SANDBOXD_ENABLED:
        return None
    try:
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()
        sandboxd_ids = {
            "sandboxd_preview",
            "sandboxd_exec",
            "sandboxd_file_write",
            "sandboxd_file_read",
            "sandboxd_file_list",
            "sandboxd_serve",
        }
        tools = [
            t.to_openai_schema()
            for t in registry.list_all()
            if t.tool_id in sandboxd_ids
        ]
        return tools or None
    except Exception:
        logger.debug("Failed to get chat tools from registry", exc_info=True)
        return None


async def _execute_tool_call(tool_name: str, arguments_json: str) -> str:
    """Execute a single tool call via the registry and return the result as JSON."""
    try:
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get(tool_name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        args = json.loads(arguments_json) if arguments_json else {}
        result = await tool.execute(args)
        if result.success:
            return json.dumps(result.result)
        return json.dumps({"error": result.error})
    except json.JSONDecodeError:
        return json.dumps({"error": f"Invalid JSON arguments: {arguments_json}"})
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return json.dumps({"error": str(e)})


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
):
    """Send a message to the LLM and stream the response via SSE.

    If user_api_key is provided, a per-request AsyncOpenAI client is created
    using that key (BYOK path). The key is used only for this call and discarded.
    If model_id is provided it overrides model_preference and the env default.
    If user_base_url is provided, it overrides the resolved base_url for custom providers.
    For llamacpp/* models, any BYOK key is ignored (llama.cpp doesn't use API keys).
    """
    await create_chat_message(db, thread_id, "user", content, user_id=user_id)
    # Commit the user message immediately so the transaction is released.
    # During long LLM streaming (minutes with tool-calls), the connection
    # would otherwise sit idle-in-transaction and get killed by PostgreSQL's
    # idle_in_transaction_session_timeout.
    await db.commit()

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
        stored_key, stored_base = await _lookup_stored_byok_key(
            db, user_id, provider_hint=model_provider
        )
        if stored_key:
            effective_user_key = stored_key
            effective_base_url = stored_base

    if raw_model and raw_model.startswith("llamacpp/"):
        effective_user_key = None

    if effective_user_key:
        effective_base = effective_base_url or base_url
        client = AsyncOpenAI(api_key=effective_user_key, base_url=effective_base)
    elif base_url != _LLM_API_BASE or api_key != _LLM_API_KEY:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    else:
        client = _client

    # Circuit breaker protection
    from app.core.circuit_breaker import CircuitOpenError, get_circuit_breaker
    from app.core.metrics import record_llm_request

    provider_name = _get_provider_for_model(raw_model) or "deepseek"
    breaker = get_circuit_breaker(provider_name)
    llm_start = time.time()

    try:
        openai_tools = _get_chat_openai_tools()

        async with breaker.protect():
            messages_for_llm = await _build_chat_messages(db, thread_id)

            if attachments:
                messages_for_llm = await _process_attachments(
                    db, messages_for_llm, attachments, raw_model
                )

            if web_search:
                messages_for_llm = await _inject_web_search(messages_for_llm, content)

            full_response = ""
            accumulated_prompt_tokens = 0
            accumulated_completion_tokens = 0

            # ── Tool-calling loop ───────────────────────────────────
            for _round in range(_MAX_TOOL_ROUNDS):
                create_kwargs: dict = {
                    "model": model,
                    "messages": messages_for_llm,
                    "stream": True,
                }
                if openai_tools:
                    create_kwargs["tools"] = openai_tools

                response = await client.chat.completions.create(**create_kwargs)

                # Accumulate streaming chunks — we need to detect both
                # content tokens AND tool_call deltas in the same stream.
                round_content_chunks: list[str] = []
                # tool_calls_by_index tracks partial tool call arguments
                tool_calls_by_index: dict[int, dict] = {}

                async for chunk in response:
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
                                    tc["function"][
                                        "arguments"
                                    ] += tc_delta.function.arguments

                    # Capture usage from streaming chunks (if provider includes it)
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage and isinstance(
                        getattr(chunk_usage, "prompt_tokens", None), int
                    ):
                        accumulated_prompt_tokens += chunk_usage.prompt_tokens or 0
                        accumulated_completion_tokens += (
                            chunk_usage.completion_tokens or 0
                        )

                    # Detect finish_reason
                    if choice.finish_reason == "tool_calls":
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

                        tool_result = await _execute_tool_call(tool_name, tool_args)

                        yield json.dumps(
                            {
                                "type": "tool_call_result",
                                "tool": tool_name,
                                "result": tool_result,
                                "call_id": call_id,
                            }
                        )

                        messages_for_llm.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": tool_result,
                            }
                        )

                    # Loop back for the next LLM call with tool results
                    continue

                # No tool calls — we have a final text response
                full_response = "".join(round_content_chunks) or "".join(
                    collected_chunks
                )
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
                    non_stream_response = await client.chat.completions.create(
                        **non_stream_kwargs
                    )
                    if non_stream_response.choices:
                        full_response = (
                            non_stream_response.choices[0].message.content or ""
                        )
                    # Second fallback: retry without tools if still empty
                    # (some models don't support function calling)
                    if not full_response.strip() and openai_tools:
                        logger.info(
                            "stream_message_to_llm: empty response with tools for %s, retrying without tools",
                            raw_model,
                        )
                        non_stream_kwargs.pop("tools", None)
                        no_tools_response = await client.chat.completions.create(
                            **non_stream_kwargs
                        )
                        if no_tools_response.choices:
                            full_response = (
                                no_tools_response.choices[0].message.content or ""
                            )
                    if full_response:
                        yield json.dumps({"type": "token", "content": full_response})
                except Exception as retry_err:
                    logger.error(
                        "stream_message_to_llm: non-streaming retry also failed for %s: %s",
                        raw_model,
                        retry_err,
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

        try:
            assistant_msg = await create_chat_message(
                db, thread_id, "assistant", full_response
            )
        except Exception as save_err:
            # Catch broad Exception: asyncpg.InterfaceError, sqlalchemy.InterfaceError,
            # OperationalError etc.  Validation/constraint errors will also fail on
            # the fresh session, so the retry is safe (no silent data corruption).
            logger.warning(
                "stream: assistant message save failed on original session (%s), retrying with fresh session",
                save_err,
            )
            assistant_msg = await create_chat_message_fresh_session(
                thread_id, "assistant", full_response
            )

        try:
            from app.services.usage_service import get_usage_service

            get_usage_service().record_usage(
                user_id=str(user_id),
                model_id=model,
                provider="byok" if user_api_key else "system",
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
                "message_id": assistant_msg.id,
                "model": model,
            }
        )

    except CircuitOpenError as e:
        llm_duration = time.time() - llm_start
        record_llm_request(
            provider=provider_name, duration_seconds=llm_duration, success=False
        )
        logger.warning("Circuit breaker open for %s: %s", provider_name, e)
        yield json.dumps(
            {
                "type": "error",
                "error": f"Service temporarily unavailable ({provider_name}). Please try again later.",
            }
        )
    except Exception as e:
        llm_duration = time.time() - llm_start
        record_llm_request(
            provider=provider_name, duration_seconds=llm_duration, success=False
        )
        logger.error("stream_message_to_llm failed: %s", e)
        yield json.dumps({"type": "error", "error": str(e)})


async def generate_thread_title(
    db: AsyncSession,
    thread_id: int,
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
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.id.asc())
        .limit(2)
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

        response = await _client.chat.completions.create(
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

            title = re.sub(
                r"^(Title|Subject|Topic):?\s*", "", title, flags=re.IGNORECASE
            )
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

    except Exception as e:
        logger.warning("Auto-titling failed for thread %d: %s", thread_id, e)

    return None


async def create_chat_branch(
    db: AsyncSession,
    user_id: int,
    parent_thread_id: int,
    parent_message_id: int,
    title: str,
) -> ChatBranch:
    """Create a new branch: copies messages up to parent_message_id into a new thread."""

    # Verify parent thread exists and belongs to user
    parent_thread = await get_chat_thread(db, parent_thread_id)
    if parent_thread is None:
        raise ValueError("Parent thread not found")

    # Create new thread for the branch
    branch_thread = await create_chat_thread(db, user_id, parent_thread.username, title)

    # Copy messages up to and including parent_message_id
    all_msgs, _ = await get_chat_messages(db, parent_thread_id)
    msgs_to_copy = [m for m in all_msgs if m.id <= parent_message_id]
    for msg in msgs_to_copy:
        await create_chat_message(
            db, branch_thread.id, msg.role, msg.content, user_id=msg.user_id
        )

    # Create branch record
    branch = ChatBranch(
        thread_id=branch_thread.id,
        parent_thread_id=parent_thread_id,
        parent_message_id=parent_message_id,
        user_id=user_id,
        title=title,
    )
    db.add(branch)
    await db.flush()
    await db.refresh(branch)
    return branch


async def list_chat_branches(
    db: AsyncSession,
    parent_thread_id: int,
) -> list[ChatBranch]:
    """List all branches from a given thread."""
    result = await db.execute(
        select(ChatBranch).where(ChatBranch.parent_thread_id == parent_thread_id)
    )
    return list(result.scalars().all())


async def get_chat_branch(db: AsyncSession, branch_id: int) -> ChatBranch | None:
    """Get a single branch by ID."""
    result = await db.execute(select(ChatBranch).where(ChatBranch.id == branch_id))
    return result.scalar_one_or_none()


async def delete_chat_branch(db: AsyncSession, branch_id: int) -> bool:
    """Delete a branch and its thread."""
    branch = await get_chat_branch(db, branch_id)
    if branch is None:
        return False
    # Delete the branch thread (cascades messages)
    await delete_chat_thread(db, branch.thread_id)
    # Delete the branch record
    await db.delete(branch)
    await db.flush()
    return True
