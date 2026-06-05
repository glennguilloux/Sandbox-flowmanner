from __future__ import annotations

import contextlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.model_router import ModelRouter
    from app.services.rag.retrieval_service import RetrievalService, RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class GeneratedPrompt:
    system_prompt: str
    rationale: dict[str, list[str]] = field(default_factory=dict)
    recommended_model: str = "deepseek/deepseek-v4-flash"
    temperature: float = 0.7
    usage: dict = field(default_factory=dict)


_SECTION_ORDER = [
    "role_definition",
    "constraints",
    "output_format",
    "examples",
    "frameworks",
    "anti_patterns",
    "chain_of_thought",
    "context_management",
    "tool_use",
    "evaluation",
]


class PromptSynthesizer:
    def __init__(self, retrieval_service: RetrievalService, llm_router: ModelRouter):
        self.retrieval_service = retrieval_service
        self.llm_router = llm_router

    async def synthesize(
        self,
        user_id: str | int,
        goal: str,
        *,
        role_description: str | None = None,
        topics: list[str] | None = None,
        books: list[str] | None = None,
    ) -> GeneratedPrompt:
        query_parts = [goal]
        if role_description:
            query_parts.append(role_description)
        query = " ".join(query_parts)

        chunks = await self.retrieval_service.retrieve(
            user_id=user_id,
            query=query,
            topics=topics,
            book_title=books[0] if books and len(books) == 1 else None,
            limit=5,
        )

        if not chunks:
            return GeneratedPrompt(
                system_prompt="",
                rationale={"error": ["No relevant book notes found. Ingest notes first via /ingest."]},
                recommended_model="deepseek/deepseek-v4-flash",
                temperature=0.7,
            )

        grouped = self._group_chunks_by_topic(chunks)
        synthesis_prompt = self._build_synthesis_prompt(goal, role_description, grouped)

        response = await self.llm_router.route_request(
            messages=[{"role": "user", "content": synthesis_prompt}],
            model_preference="deepseek/deepseek-v4-flash",
            max_tokens=2048,
            temperature=0.7,
        )

        content = response.get("response", "")
        usage = response.get("usage", {})
        parsed = self._parse_response(content)
        parsed.usage = usage
        return parsed

    def _group_chunks_by_topic(self, chunks: list[RetrievedChunk]) -> str:
        groups: dict[str, list[str]] = defaultdict(list)
        for c in chunks:
            for topic in c.topics:
                groups[topic].append(f'From "{c.book_title}": {c.text}')

        parts: list[str] = []
        for topic in _SECTION_ORDER:
            if topic in groups:
                label = topic.replace("_", " ").title()
                items = "\n".join(f"- {t}" for t in groups[topic])
                parts.append(f"### {label}\n{items}")

        return "\n\n".join(parts) if parts else "No relevant excerpts found."

    @staticmethod
    def _build_synthesis_prompt(
        goal: str, role_description: str | None, grouped_chunks: str
    ) -> str:
        lines = [
            "You are an expert prompt engineer. Given these book excerpts:",
            "",
            grouped_chunks,
            "",
            f'Generate an optimal system prompt for:\nGoal: {goal}',
        ]
        if role_description:
            lines.append(f"Role: {role_description}")

        lines.extend([
            "",
            "Return your response in this format:",
            "",
            "## System Prompt",
            "[the generated system prompt]",
            "",
            "## Rationale",
            "[which chunks informed each section, as bullet points]",
            "",
            "## Configuration",
            "- Recommended model: [model]",
            "- Temperature: [value]",
        ])
        return "\n".join(lines)

    @staticmethod
    def _parse_response(content: str) -> GeneratedPrompt:
        system_prompt = ""
        rationale: dict[str, list[str]] = {}
        recommended_model = "deepseek/deepseek-v4-flash"
        temperature = 0.7

        sections = content.split("## ")

        for section in sections:
            section = section.strip()
            if section.lower().startswith("system prompt"):
                system_prompt = section.split("\n", 1)[1].strip() if "\n" in section else ""
            elif section.lower().startswith("rationale"):
                rationale_text = section.split("\n", 1)[1].strip() if "\n" in section else ""
                current_key = "general"
                for line in rationale_text.split("\n"):
                    line = line.strip().strip("- ").strip()
                    if line.endswith(":") and not line.startswith("http"):
                        current_key = line.rstrip(":").lower().replace(" ", "_")
                        rationale.setdefault(current_key, [])
                    elif line:
                        rationale.setdefault(current_key, []).append(line)
            elif section.lower().startswith("configuration"):
                for line in section.split("\n")[1:]:
                    line = line.strip().strip("- ").strip()
                    if "model" in line.lower() and ":" in line:
                        recommended_model = line.split(":", 1)[1].strip()
                    elif "temperature" in line.lower() and ":" in line:
                        with contextlib.suppress(ValueError):
                            temperature = float(line.split(":", 1)[1].strip())

        return GeneratedPrompt(
            system_prompt=system_prompt,
            rationale=rationale,
            recommended_model=recommended_model,
            temperature=temperature,
        )
