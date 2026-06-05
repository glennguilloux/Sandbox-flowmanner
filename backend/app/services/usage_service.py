from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.schemas.usage import UsageByModel, UsageRecord, UsageSummaryResponse

PERIOD_DELTAS: dict[str, timedelta] = {
    "day": timedelta(hours=24),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
}


def _period_cutoff(period: str) -> datetime:
    delta = PERIOD_DELTAS.get(period, timedelta(days=1))
    return datetime.now(UTC) - delta


def _bucket_timestamp(ts: datetime, granularity: str) -> datetime:
    if granularity == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


class UsageDataPoint:
    __slots__ = ("cost", "request_count", "timestamp", "tokens")

    def __init__(self, timestamp: datetime) -> None:
        self.timestamp = timestamp
        self.tokens = 0
        self.cost = 0.0
        self.request_count = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "tokens": self.tokens,
            "cost": self.cost,
            "request_count": self.request_count,
        }


class UsageService:
    def __init__(self) -> None:
        self._records: dict[str, list[UsageRecord]] = defaultdict(list)

    def record_usage(
        self,
        user_id: str,
        model_id: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float | None = None,
    ) -> UsageRecord:
        if cost is None:
            cost = (prompt_tokens * 0.000003) + (completion_tokens * 0.000006)

        record = UsageRecord(
            user_id=user_id,
            model_id=model_id,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=round(cost, 8),
            timestamp=datetime.now(UTC),
        )
        self._records[user_id].append(record)
        return record

    def get_summary(self, user_id: str, period: str = "day") -> UsageSummaryResponse:
        cutoff = _period_cutoff(period)
        records = [r for r in self._records.get(user_id, []) if r.timestamp >= cutoff]

        by_model: dict[tuple[str, str], UsageByModel] = {}
        total_tokens = 0
        total_cost = 0.0

        for r in records:
            key = (r.model_id, r.provider)
            total_tokens += r.prompt_tokens + r.completion_tokens
            total_cost += r.cost

            if key not in by_model:
                by_model[key] = UsageByModel(
                    model_id=r.model_id,
                    provider=r.provider,
                    prompt_tokens=0,
                    completion_tokens=0,
                    cost=0.0,
                )
            entry = by_model[key]
            by_model[key] = UsageByModel(
                model_id=entry.model_id,
                provider=entry.provider,
                prompt_tokens=entry.prompt_tokens + r.prompt_tokens,
                completion_tokens=entry.completion_tokens + r.completion_tokens,
                cost=round(entry.cost + r.cost, 8),
            )

        return UsageSummaryResponse(
            total_tokens=total_tokens,
            total_cost=round(total_cost, 8),
            period=period,
            breakdown=list(by_model.values()),
        )

    def get_timeseries(
        self,
        user_id: str,
        period: str = "day",
        granularity: str = "hour",
    ) -> list[dict]:
        cutoff = _period_cutoff(period)
        records = [r for r in self._records.get(user_id, []) if r.timestamp >= cutoff]

        buckets: dict[datetime, UsageDataPoint] = {}
        for r in records:
            key = _bucket_timestamp(r.timestamp, granularity)
            if key not in buckets:
                buckets[key] = UsageDataPoint(timestamp=key)
            dp = buckets[key]
            dp.tokens += r.prompt_tokens + r.completion_tokens
            dp.cost = round(dp.cost + r.cost, 8)
            dp.request_count += 1

        return [
            dp.to_dict() for dp in sorted(buckets.values(), key=lambda dp: dp.timestamp)
        ]

    def get_raw_records(self, user_id: str) -> list[UsageRecord]:
        return list(self._records.get(user_id, []))

    def clear(self, user_id: str | None = None) -> None:
        if user_id is None:
            self._records.clear()
        else:
            self._records.pop(user_id, None)


_usage_service: UsageService | None = None


def get_usage_service() -> UsageService:
    global _usage_service
    if _usage_service is None:
        _usage_service = UsageService()
    return _usage_service
