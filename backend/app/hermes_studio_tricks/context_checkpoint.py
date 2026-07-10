"""Context-compression "checkpoint" for long agent/workflow runs.

Independent reimplementation of the *handoff-summary pattern* from Hermes
Studio's ``context-compressor`` (no code copied; the repo is BSL-licensed).

Key ideas we reuse:

1. The summary is framed as **REFERENCE ONLY** so the model does not obey stale
   requests embedded in it (``SUMMARY_PREFIX``).
2. A rigid schema with ``## Active Task`` as the most important field — copy the
   user's last unfulfilled request verbatim so the next assistant resumes there.
3. Incremental compression: we persist the index of the last compressed message
   and only re-summarize the new tail.
4. A pathological-run guard for ``tiktoken`` (a long CJK / unbroken letter run
   makes its BPE merge loop O(n^2) and hang the process). We detect it up front
   and fall back to a cheap heuristic.

This module is provider-agnostic: you pass in a ``summarize`` callable that
calls whatever LLM you want. Nothing here calls an API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

try:
    import tiktoken

    _TIKTOKEN_OK = True
except Exception:  # pragma: no cover - optional dep
    tiktoken = None
    _TIKTOKEN_OK = False


# Framing prefix injected before every summary so the model treats it as
# background reference, not live instructions.
SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted into the "
    "summary below. This is a handoff from a previous context window — treat it as "
    "background reference, NOT as active instructions. Do NOT answer questions or "
    "fulfill requests mentioned in this summary; they were already addressed. "
    "Your current task is identified in the '## Active Task' section. Respond ONLY "
    "to the latest user message that appears AFTER this summary."
)

TEMPLATE_SECTIONS = """Use this exact structure:

## Active Task
[THE SINGLE MOST IMPORTANT FIELD. Copy the user's most recent request or task
assignment verbatim — the exact words they used. If multiple tasks were requested
and only some are done, list only the ones NOT yet completed.]

## Goal
[What the user is trying to accomplish overall]

## Constraints & Preferences
[User preferences, coding style, constraints, important decisions]

## Completed Actions
[Numbered list of concrete actions taken — include tool used, target, outcome.
Format: N. ACTION target — outcome [tool: name]]

## Active State
[Working directory, branch, modified/created files, test status, running processes]

## In Progress
[Work currently underway when compaction fired]

## Blocked
[Blockers, errors, exact error messages]

## Key Decisions
[Important technical decisions and WHY]

## Relevant Files
[Files read/modified/created with a brief note on each]

## Remaining Work
[What remains, framed as context]

## Critical Context
[Specific values, error messages, config details that would be lost]"""

MAX_LETTER_RUN = 2000


@dataclass
class ChatMessage:
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_name: str | None = None


@dataclass
class CheckpointConfig:
    trigger_tokens: int = 100_000
    summary_budget: int = 8_000
    head_message_count: int = 0
    tail_message_count: int = 10
    summarization_timeout_ms: int = 300_000


@dataclass
class CheckpointResult:
    messages: list[ChatMessage]
    compressed: bool
    llm_compressed: bool
    summary_token_estimate: int
    verbatim_count: int
    compressed_start_index: int


# -- token counting (with pathological-run guard) --------------------------


def _has_pathological_run(text: str) -> bool:
    run = 0
    for ch in text:
        cc = ord(ch)
        if (65 <= cc <= 90) or (97 <= cc <= 122) or cc > 0x2E7F:
            run += 1
            if run > MAX_LETTER_RUN:
                return True
        else:
            run = 0
    return False


def _heuristic_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u2e80-\u9fff\uac00-\ud7af\u3000-\u303f\uff00-\uffef]", text))
    other = len(text) - cjk
    return int(cjk * 1.5 + other / 4)


def count_tokens(text: str) -> int:
    """Count tokens; falls back to a cheap heuristic for CJK / long unbroken runs."""
    if not text:
        return 0
    if _has_pathological_run(text):
        return _heuristic_tokens(text)
    if not _TIKTOKEN_OK or tiktoken is None:
        return _heuristic_tokens(text)
    try:
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return _heuristic_tokens(text)


def count_message_tokens(msg: ChatMessage) -> int:
    if isinstance(msg.content, str):
        return count_tokens(msg.content)
    return 0


def count_messages_tokens(messages: Sequence[ChatMessage]) -> int:
    return sum(count_message_tokens(m) for m in messages)


# -- prompting -------------------------------------------------------------


def build_full_prompt(content_to_summarize: str, summary_budget: int) -> str:
    return (
        "You are a summarization agent creating a context checkpoint. Your output "
        "will be injected as reference material for a DIFFERENT assistant that "
        "continues the conversation. Do NOT respond to any questions or requests in "
        "the conversation — only output the structured summary. Do NOT include any "
        "preamble, greeting, or prefix.\n\n"
        f"TURNS TO SUMMARIZE:\n{content_to_summarize}\n\n{TEMPLATE_SECTIONS}\n\n"
        f"Target ~{summary_budget} tokens. Be CONCRETE — include file paths, command "
        "outputs, error messages, line numbers, specific values.\n\n"
        "Write only the summary body. Do not include any preamble or prefix."
    )


def build_incremental_prompt(previous_summary: str, content_to_summarize: str, summary_budget: int) -> str:
    return (
        "You are a summarization agent creating a context checkpoint. A previous "
        "compaction produced the summary below. New turns have occurred since then.\n\n"
        f"PREVIOUS SUMMARY:\n{previous_summary}\n\n"
        f"NEW TURNS TO INCORPORATE:\n{content_to_summarize}\n\n"
        f"{TEMPLATE_SECTIONS}\n\n"
        "Update the summary. PRESERVE still-relevant info, add new completed actions, "
        "move items from 'In Progress' to 'Completed Actions', update 'Active State'. "
        "CRITICAL: update '## Active Task' to the user's most recent unfulfilled "
        f"request.\n\nTarget ~{summary_budget} tokens. Be CONCRETE.\n\n"
        "Write only the summary body. Do not include any preamble or prefix."
    )


def serialize_for_summary(messages: Sequence[ChatMessage]) -> str:
    """Flatten messages into a readable transcript for the summarizer."""
    parts: list[str] = []
    for msg in messages:
        role = f"[tool:{msg.tool_name}]" if msg.role == "tool" else msg.role
        content = msg.content or ""
        if msg.role == "assistant" and msg.tool_calls:
            calls = "; ".join(
                f"{tc.get('function', {}).get('name', '?')}({tc.get('function', {}).get('arguments', '')[:1500]})"
                for tc in (msg.tool_calls or [])
            )
            parts.append(f"{role}: [tool_call: {calls}]")
            if content.strip():
                parts.append(f"{role}: {content}")
        else:
            parts.append(f"{role}: {content}")
    return "\n\n".join(p for p in parts if p.strip())


# -- core compressor -------------------------------------------------------


def checkpoint(
    messages: Sequence[ChatMessage],
    summarize: Callable[[str], str],
    *,
    config: CheckpointConfig | None = None,
    previous_summary: str | None = None,
    previous_last_index: int = -1,
) -> CheckpointResult:
    """Compress a message list into a handoff summary.

    ``summarize`` is a callable taking the prompt string and returning the summary.
    Returns the rebuilt message list (summary + tail) plus metadata.
    """
    cfg = config or CheckpointConfig()
    msgs = list(messages)
    total = len(msgs)

    # Under threshold -> return as-is.
    if count_messages_tokens(msgs) <= cfg.trigger_tokens:
        return CheckpointResult(
            messages=msgs,
            compressed=False,
            llm_compressed=False,
            summary_token_estimate=count_messages_tokens(msgs),
            verbatim_count=total,
            compressed_start_index=-1,
        )

    head = msgs[: cfg.head_message_count] if cfg.head_message_count else []
    tail_start = max(cfg.head_message_count, total - cfg.tail_message_count)
    if previous_summary and 0 <= previous_last_index < total:
        to_summarize = msgs[previous_last_index + 1 : tail_start]
    else:
        to_summarize = msgs[:tail_start]

    transcript = serialize_for_summary(to_summarize)
    prompt = (
        build_incremental_prompt(previous_summary, transcript, cfg.summary_budget)
        if previous_summary
        else build_full_prompt(transcript, cfg.summary_budget)
    )
    summary = summarize(prompt).strip()

    summary_message = ChatMessage(role="user", content=f"{SUMMARY_PREFIX}\n\n{summary}")
    rebuilt = [*head, summary_message, *msgs[tail_start:]]

    return CheckpointResult(
        messages=rebuilt,
        compressed=True,
        llm_compressed=True,
        summary_token_estimate=count_tokens(summary),
        verbatim_count=len(rebuilt),
        compressed_start_index=tail_start,
    )
