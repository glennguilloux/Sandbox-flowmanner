from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.services.model_router import ModelRouter

logger = logging.getLogger(__name__)

TOPICS = frozenset(
    {
        "role_definition",
        "constraints",
        "output_format",
        "examples",
        "frameworks",
        "anti_patterns",
        "evaluation",
        "chain_of_thought",
        "context_management",
        "tool_use",
    }
)

_TOPIC_KEYWORDS: dict[str, set[str]] = {
    "role_definition": {
        "you are a",
        "act as",
        "your role",
        "you're a",
        "persona",
        "as an ai",
    },
    "constraints": {
        "do not",
        "must not",
        "avoid",
        "never",
        "don't",
        "should not",
        "cannot",
    },
    "output_format": {
        "output",
        "return",
        "format",
        "json",
        "respond with",
        "response format",
    },
    "examples": {"for example", "e.g.", "example:", "for instance", "such as"},
    "frameworks": {"framework", "methodology", "approach:", "technique"},
    "anti_patterns": {
        "common mistake",
        "anti-pattern",
        "pitfall",
        "watch out for",
        "don't",
    },
    "evaluation": {"evaluate", "score", "rate", "judge", "assess", "criteria"},
    "chain_of_thought": {
        "step",
        "first",
        "then",
        "think",
        "reason",
        "chain of thought",
        "cot",
    },
    "context_management": {"context", "memory", "conversation", "history", "window"},
    "tool_use": {"tool", "function call", "use the", "invoke", "tool_call"},
}


@dataclass
class Chunk:
    id: str
    book_title: str
    text: str
    topics: list[str]
    relevance_score: float
    chunk_index: int
    total_chunks: int
    created_at: str


def _tiktoken_len(text: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return len(text) // 4


class ChunkingService:
    def __init__(self):
        self._splitter = None

    @property
    def splitter(self):
        if self._splitter is None:
            try:
                from langchain.text_splitter import RecursiveCharacterTextSplitter

                self._splitter = RecursiveCharacterTextSplitter(
                    chunk_size=settings.RAG_CHUNK_SIZE,
                    chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                    length_function=_tiktoken_len,
                    separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
                )
            except ImportError:
                self._splitter = None
        return self._splitter

    async def chunk_book(
        self,
        text: str,
        book_title: str,
        llm_router: ModelRouter | None = None,
    ) -> list[Chunk]:
        raw_chunks = self.splitter.split_text(text) if self.splitter is not None else [text]

        result: list[Chunk] = []
        total = len(raw_chunks)
        now = datetime.now(UTC).isoformat()

        for i, raw in enumerate(raw_chunks):
            stripped = raw.strip()
            if not stripped:
                continue

            if llm_router is not None:
                topics = await self._detect_topics_llm(stripped, llm_router)
            else:
                topics = self._detect_topics_fast(stripped)

            result.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    book_title=book_title,
                    text=stripped,
                    topics=topics,
                    relevance_score=self._assign_relevance(topics, stripped),
                    chunk_index=i,
                    total_chunks=total,
                    created_at=now,
                )
            )

        return result

    def _detect_topics_fast(self, text: str) -> list[str]:
        lower = text.lower()
        matched: list[str] = []
        for topic, keywords in _TOPIC_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                matched.append(topic)
        return matched

    async def _detect_topics_llm(self, text: str, llm_router: ModelRouter) -> list[str]:
        prompt = (
            f"Given this text excerpt, which topics from {sorted(TOPICS)} apply?\n\n"
            f"---\n{text[:1000]}\n---\n\n"
            f'Return ONLY a JSON array of matching topic strings, e.g. ["role_definition", "constraints"]. '
            f"If none match, return []."
        )
        try:
            response = await llm_router.route_request(
                messages=[{"role": "user", "content": prompt}],
                model_preference="deepseek/deepseek-v4-flash",
                max_tokens=200,
                temperature=0,
            )
            content = response.get("response", "")
            import json

            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [t for t in parsed if t in TOPICS]
        except Exception:
            logger.debug("topic_detection_llm_failed", exc_info=True)
        return self._detect_topics_fast(text)

    @staticmethod
    def _assign_relevance(topics: list[str], text: str) -> float:
        score = min(len(topics) / 5.0, 1.0)
        prompt_indicators = (
            "system prompt",
            "you are",
            "instructions",
            "guidelines",
            "rules:",
        )
        if any(ind in text.lower() for ind in prompt_indicators):
            score = min(score + 0.3, 1.0)
        return round(score, 2)
