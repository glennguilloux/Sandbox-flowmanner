"""
LLM Operations Tools — Token Counter.

token_counter → Accurately count tokens for text and chat messages using
    tiktoken with model-specific encodings. Supports counting, truncation,
    and chunk splitting modes for OpenAI, Anthropic, and open-source models.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Model Encoding Map ─────────────────────────────────────────────────

_MODEL_ENCODING_MAP: dict[str, str] = {
    # OpenAI — o200k_base
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4.5": "o200k_base",
    "chatgpt-4o": "o200k_base",
    "o1": "o200k_base",
    "o1-mini": "o200k_base",
    "o3": "o200k_base",
    # OpenAI — cl100k_base
    "gpt-4": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4-32k": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "gpt-3.5-turbo-16k": "cl100k_base",
    "text-embedding-3-small": "cl100k_base",
    "text-embedding-3-large": "cl100k_base",
    "text-embedding-ada-002": "cl100k_base",
    # OpenAI — p50k_base
    "text-davinci-003": "p50k_base",
    "text-davinci-002": "p50k_base",
    "code-davinci-002": "p50k_base",
    "davinci": "p50k_base",
    # Anthropic (approximate)
    "claude-3-opus": "cl100k_base",
    "claude-3-sonnet": "cl100k_base",
    "claude-3-haiku": "cl100k_base",
    "claude-3.5-sonnet": "cl100k_base",
    "claude-3.5-haiku": "cl100k_base",
    "claude": "cl100k_base",
    # Open-source (approximate)
    "llama": "cl100k_base",
    "mistral": "cl100k_base",
    "mixtral": "cl100k_base",
    "gemma": "cl100k_base",
    "qwen": "cl100k_base",
}

_CHARS_PER_TOKEN = 4.0

# Token overhead per message for chat models (approx)
_CHAT_OVERHEAD = 3  # tokens per message metadata


class TokenCounterInput(ToolInput):
    """Input schema: text, model, mode, max_tokens, chunk_overlap, return_tokens."""

    text: str | list[dict[str, str]] | None = Field(
        None,
        description="Text to count tokens for, or list of chat messages [{role, content}]",
    )
    model: str = Field(
        "gpt-4o",
        description="Model name to select tokenizer",
    )
    mode: Literal["count", "truncate", "split_chunks"] = Field(
        "count",
        description="Mode: 'count' tokens, 'truncate' to max_tokens, 'split_chunks' into chunks",
    )
    max_tokens: int | None = Field(
        None,
        description="Max tokens for truncate/split_chunks modes",
    )
    chunk_overlap: int = Field(
        0, ge=0,
        description="Token overlap between chunks (split_chunks mode)",
    )
    add_special_tokens: bool = Field(
        True,
        description="Include special tokens (<|endoftext|>, etc.) in count",
    )
    return_tokens: bool = Field(
        False,
        description="Return the actual token IDs in the result",
    )


class TokenCounterTool(BaseTool):
    """Count, truncate, and split tokens for LLM text and chat messages."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="token_counter",
            name="Token Counter",
            description=(
                "Count tokens for text and chat messages using tiktoken with "
                "model-specific encodings. Supports counting, truncation, and "
                "chunk splitting modes. Covers OpenAI, Anthropic, and open-source "
                "models with encoding approximation."
            ),
            category="llm-operations",
            input_schema=TokenCounterInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "mode": {"type": "string"},
                    "token_count": {"type": "integer"},
                    "model": {"type": "string"},
                    "encoding": {"type": "string"},
                    "is_approximate": {"type": "boolean"},
                    "character_count": {"type": "integer"},
                    "tokens": {"type": "array", "items": {"type": "integer"}},
                    "chunks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer"},
                                "text": {"type": "string"},
                                "token_count": {"type": "integer"},
                            },
                        },
                    },
                    "success": {"type": "boolean"},
                },
            },
            tags=["llm", "tokens", "tiktoken", "encoding", "truncation", "chunking"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)
        self._tiktoken_available = False
        try:
            import tiktoken
            self._tiktoken_available = True
        except ImportError:
            pass

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TokenCounterInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        # Resolve text: check backward-compat 'text' as str, or use 'text' as chat messages
        text_str = validated.text
        if text_str is None and "text" in input_data and isinstance(input_data["text"], str):
            text_str = input_data["text"]

        if not text_str:
            return ToolResult.error_result(tool_id=self.tool_id, error="text is required")

        encoding_name = self._resolve_encoding(validated.model)
        encoding_info = self._get_encoding_info(validated.model)

        try:
            if validated.mode == "count":
                result = self._handle_count(validated, text_str, encoding_name, encoding_info)
            elif validated.mode == "truncate":
                result = self._handle_truncate(validated, text_str, encoding_name, encoding_info)
            elif validated.mode == "split_chunks":
                result = self._handle_split(validated, text_str, encoding_name, encoding_info)
            else:
                return ToolResult.error_result(tool_id=self.tool_id, error=f"Unknown mode: {validated.mode}")

            result["success"] = True
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("token_counter failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── Mode handlers ────────────────────────────────────────────

    def _handle_count(self, validated: TokenCounterInput, text_str, encoding_name: str, encoding_info: dict) -> dict[str, Any]:
        text_content = self._extract_text(text_str)
        token_count, token_ids = self._count_tokens(text_content, validated.model, validated.return_tokens)
        result: dict[str, Any] = {
            "mode": "count",
            "token_count": token_count,
            "model": validated.model,
            "encoding": encoding_info["encoding_name"],
            "is_approximate": encoding_info["source"] == "heuristic",
            "character_count": len(text_content),
        }
        if validated.return_tokens and token_ids:
            result["tokens"] = token_ids
        return result

    def _handle_truncate(self, validated: TokenCounterInput, text_str, encoding_name: str, encoding_info: dict) -> dict[str, Any]:
        if not validated.max_tokens:
            return {"error": "max_tokens is required for truncate mode"}

        text_content = self._extract_text(text_str)
        token_count, _ = self._count_tokens(text_content, validated.model, False)

        if token_count <= validated.max_tokens:
            return {
                "mode": "truncate",
                "token_count": token_count,
                "model": validated.model,
                "encoding": encoding_info["encoding_name"],
                "truncated": False,
                "truncated_text": text_content,
                "max_tokens": validated.max_tokens,
                "tokens_removed": 0,
            }

        truncated = self._truncate_to_tokens(text_content, validated.model, validated.max_tokens)
        new_count, _ = self._count_tokens(truncated, validated.model, False)

        return {
            "mode": "truncate",
            "token_count": new_count,
            "model": validated.model,
            "encoding": encoding_info["encoding_name"],
            "truncated": True,
            "truncated_text": truncated,
            "max_tokens": validated.max_tokens,
            "tokens_removed": token_count - new_count,
            "original_token_count": token_count,
        }

    def _handle_split(self, validated: TokenCounterInput, text_str, encoding_name: str, encoding_info: dict) -> dict[str, Any]:
        if not validated.max_tokens:
            return {"error": "max_tokens is required for split_chunks mode"}

        text_content = self._extract(text_str)
        chunks = self._split_into_chunks(text_content, validated.model, validated.max_tokens, validated.chunk_overlap)

        return {
            "mode": "split_chunks",
            "model": validated.model,
            "encoding": encoding_info["encoding_name"],
            "max_tokens_per_chunk": validated.max_tokens,
            "chunk_overlap": validated.chunk_overlap,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }

    # ── Core helpers ─────────────────────────────────────────────

    def _extract_text(self, text_input: str | list[dict]) -> str:
        """Extract plain text from string or chat messages."""
        if isinstance(text_input, str):
            return text_input
        if isinstance(text_input, list):
            return "\n".join(f"{m.get('role', '')}: {m.get('content', '')}" for m in text_input)
        return str(text_input)

    def _extract(self, text_input: str | list[dict]) -> str:
        return self._extract_text(text_input)

    def _count_tokens(self, text: str, model: str, return_ids: bool) -> tuple[int, list[int] | None]:
        """Count tokens, optionally returning token IDs."""
        if not self._tiktoken_available:
            return self._heuristic_count(text), None

        encoding_name = self._resolve_encoding(model)
        import tiktoken

        try:
            enc = tiktoken.get_encoding(encoding_name)
        except (ValueError, KeyError):
            try:
                enc = tiktoken.encoding_for_model(model)
            except (ValueError, KeyError):
                return self._heuristic_count(text), None

        ids = enc.encode(text)
        return len(ids), ids if return_ids else None

    def _heuristic_count(self, text: str) -> int:
        return max(1, int(len(text) / _CHARS_PER_TOKEN))

    def _resolve_encoding(self, model: str) -> str:
        model_lower = model.lower()
        if model_lower in _MODEL_ENCODING_MAP:
            return _MODEL_ENCODING_MAP[model_lower]
        for prefix, encoding in sorted(_MODEL_ENCODING_MAP.items(), key=lambda x: -len(x[0])):
            if model_lower.startswith(prefix):
                return encoding
        return "cl100k_base"

    def _get_encoding_info(self, model: str) -> dict[str, str]:
        if self._tiktoken_available:
            return {"encoding_name": self._resolve_encoding(model), "source": "tiktoken"}
        return {"encoding_name": "heuristic", "source": "heuristic"}

    def _truncate_to_tokens(self, text: str, model: str, max_tokens: int) -> str:
        """Truncate text to fit within max_tokens."""
        if not self._tiktoken_available:
            # Heuristic: truncate to max_tokens * chars_per_token
            return text[: int(max_tokens * _CHARS_PER_TOKEN)] + "..."

        encoding_name = self._resolve_encoding(model)
        import tiktoken

        try:
            enc = tiktoken.get_encoding(encoding_name)
        except (ValueError, KeyError):
            return text[: int(max_tokens * _CHARS_PER_TOKEN)] + "..."

        ids = enc.encode(text)
        if len(ids) <= max_tokens:
            return text

        truncated_ids = ids[:max_tokens]
        return enc.decode(truncated_ids) + "..."

    def _split_into_chunks(self, text: str, model: str, max_tokens: int, overlap: int) -> list[dict[str, Any]]:
        """Split text into token-sized chunks with overlap."""
        if not self._tiktoken_available:
            chunk_size = int(max_tokens * _CHARS_PER_TOKEN)
            chunks = []
            for i, start in enumerate(range(0, len(text), chunk_size - int(overlap * _CHARS_PER_TOKEN))):
                chunk_text = text[start: start + chunk_size]
                if not chunk_text:
                    break
                chunks.append({
                    "index": i,
                    "text": chunk_text,
                    "token_count": self._heuristic_count(chunk_text),
                })
            return chunks

        encoding_name = self._resolve_encoding(model)
        import tiktoken

        try:
            enc = tiktoken.get_encoding(encoding_name)
        except (ValueError, KeyError):
            return self._heuristic_split(text, max_tokens, overlap)

        ids = enc.encode(text)
        chunk_ids = []
        step = max_tokens - overlap
        for i in range(0, len(ids), step):
            chunk = ids[i: i + max_tokens]
            if not chunk:
                break
            chunk_ids.append(chunk)

        chunks = []
        for idx, c_ids in enumerate(chunk_ids):
            chunk_text = enc.decode(c_ids)
            chunks.append({
                "index": idx,
                "text": chunk_text,
                "token_count": len(c_ids),
            })
        return chunks

    def _heuristic_split(self, text: str, max_tokens: int, overlap: int) -> list[dict[str, Any]]:
        chunk_size = int(max_tokens * _CHARS_PER_TOKEN)
        overlap_chars = int(overlap * _CHARS_PER_TOKEN)
        chunks = []
        for i, start in enumerate(range(0, len(text), chunk_size - overlap_chars)):
            chunk_text = text[start: start + chunk_size]
            if not chunk_text:
                break
            chunks.append({"index": i, "text": chunk_text, "token_count": self._heuristic_count(chunk_text)})
        return chunks


register_tool(TokenCounterTool())
