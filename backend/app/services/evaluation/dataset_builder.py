"""Golden dataset builder — create, manage, and import test cases."""

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation_models import GoldenDataset, GoldenTestCase

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """Build and manage golden datasets for LLM evaluation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_dataset(
        self,
        name: str,
        category: str,
        description: str = "",
        version: int = 1,
    ) -> GoldenDataset:
        dataset = GoldenDataset(
            name=name,
            category=category,
            description=description,
            version=version,
        )
        self.db.add(dataset)
        await self.db.flush()
        return dataset

    async def add_test_case(
        self,
        dataset_id: str,
        input_prompt: str,
        expected_behavior: str,
        task_type: str,
        difficulty: str = "medium",
        tags: list[str] | None = None,
        rubric: dict[str, Any] | None = None,
    ) -> GoldenTestCase:
        if rubric is None:
            rubric = self._default_rubric()

        test_case = GoldenTestCase(
            dataset_id=dataset_id,
            input_prompt=input_prompt,
            expected_behavior=expected_behavior,
            task_type=task_type,
            difficulty=difficulty,
            tags=tags or [],
            rubric=rubric,
        )
        self.db.add(test_case)
        await self.db.flush()
        return test_case

    async def add_test_cases_bulk(
        self, dataset_id: str, cases: list[dict[str, Any]]
    ) -> list[GoldenTestCase]:
        results = []
        for case in cases:
            tc = await self.add_test_case(
                dataset_id=dataset_id,
                input_prompt=case["input_prompt"],
                expected_behavior=case["expected_behavior"],
                task_type=case.get("task_type", "general"),
                difficulty=case.get("difficulty", "medium"),
                tags=case.get("tags"),
                rubric=case.get("rubric"),
            )
            results.append(tc)
        return results

    async def get_dataset(self, dataset_id: str) -> GoldenDataset | None:
        result = await self.db.execute(
            select(GoldenDataset).where(GoldenDataset.id == dataset_id)
        )
        return result.scalar_one_or_none()

    async def list_datasets(self, category: str | None = None) -> list[GoldenDataset]:
        stmt = select(GoldenDataset).order_by(GoldenDataset.created_at.desc())
        if category:
            stmt = stmt.where(GoldenDataset.category == category)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_test_cases(self, dataset_id: str) -> list[GoldenTestCase]:
        result = await self.db.execute(
            select(GoldenTestCase)
            .where(GoldenTestCase.dataset_id == dataset_id)
            .order_by(GoldenTestCase.created_at)
        )
        return list(result.scalars().all())

    async def update_test_case(
        self,
        test_case_id: str,
        **kwargs: Any,
    ) -> GoldenTestCase | None:
        result = await self.db.execute(
            select(GoldenTestCase).where(GoldenTestCase.id == test_case_id)
        )
        tc = result.scalar_one_or_none()
        if not tc:
            return None
        for key, value in kwargs.items():
            if hasattr(tc, key) and key not in ("id", "dataset_id", "created_at"):
                setattr(tc, key, value)
        await self.db.flush()
        return tc

    async def delete_test_case(self, test_case_id: str) -> bool:
        result = await self.db.execute(
            select(GoldenTestCase).where(GoldenTestCase.id == test_case_id)
        )
        tc = result.scalar_one_or_none()
        if not tc:
            return False
        await self.db.delete(tc)
        await self.db.flush()
        return True

    async def import_from_langfuse_traces(
        self,
        dataset_name: str,
        traces: list[dict[str, Any]],
        category: str = "imported",
    ) -> GoldenDataset:
        dataset = await self.create_dataset(
            name=dataset_name,
            category=category,
            description=f"Imported from Langfuse traces ({len(traces)} cases)",
        )
        cases = []
        for trace in traces:
            cases.append(
                {
                    "input_prompt": trace.get("input", ""),
                    "expected_behavior": trace.get(
                        "expected_output", trace.get("output", "")
                    ),
                    "task_type": trace.get("task_type", "imported"),
                    "difficulty": trace.get("difficulty", "medium"),
                    "tags": trace.get("tags", []),
                }
            )
        await self.add_test_cases_bulk(dataset.id, cases)
        return dataset

    @staticmethod
    def compute_config_hash(config: dict[str, Any]) -> str:
        raw = json.dumps(config, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _default_rubric() -> dict[str, Any]:
        return {
            "criteria": {
                "accuracy": {
                    "weight": 0.35,
                    "description": "Factually correct and precise",
                },
                "completeness": {
                    "weight": 0.25,
                    "description": "Covers all required aspects",
                },
                "relevance": {
                    "weight": 0.25,
                    "description": "Stays on topic, answers the question",
                },
                "safety": {
                    "weight": 0.15,
                    "description": "No harmful, biased, or misleading content",
                },
            },
            "scale": {"min": 1, "max": 5},
        }
