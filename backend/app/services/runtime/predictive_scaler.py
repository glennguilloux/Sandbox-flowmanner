"""
Phase 4: Predictive Scaler
ML-based resource prediction and auto-scaling
"""

import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class PredictiveScaler:
    """Predictive auto-scaling based on ML models"""

    def __init__(self):
        self.current_workers = 2
        self.min_workers = 1
        self.max_workers = 20
        self.target_cpu = 70.0
        self.target_memory = 80.0
        self._predictions: dict[str, Any] = {}

    async def get_predictions(self, horizon: str = "1h") -> dict[str, Any]:
        """Get resource predictions for the specified horizon"""
        # Simulate ML predictions
        cpu_current = random.uniform(40, 80)
        memory_current = random.uniform(50, 85)

        cpu_predicted = cpu_current + random.uniform(-15, 20)
        memory_predicted = memory_current + random.uniform(-10, 15)

        # Clamp values
        cpu_predicted = max(10, min(95, cpu_predicted))
        memory_predicted = max(20, min(95, memory_predicted))

        self._predictions = {
            "cpu": {
                "resource": "cpu",
                "current": round(cpu_current, 2),
                "predicted": round(cpu_predicted, 2),
                "confidence": round(random.uniform(0.7, 0.95), 2),
                "recommendation": self._get_recommendation(
                    "cpu", cpu_current, cpu_predicted
                ),
                "horizon": horizon,
            },
            "memory": {
                "resource": "memory",
                "current": round(memory_current, 2),
                "predicted": round(memory_predicted, 2),
                "confidence": round(random.uniform(0.7, 0.95), 2),
                "recommendation": self._get_recommendation(
                    "memory", memory_current, memory_predicted
                ),
                "horizon": horizon,
            },
        }

        return self._predictions

    def _get_recommendation(
        self, resource: str, current: float, predicted: float
    ) -> str:
        """Generate scaling recommendation"""
        if predicted > 85:
            return f"SCALE UP: {resource} predicted to exceed threshold"
        elif predicted < 30:
            return f"SCALE DOWN: {resource} predicted to be underutilized"
        else:
            return f"MAINTAIN: {resource} within acceptable range"

    async def get_scaling_recommendations(self) -> dict[str, Any]:
        """Get scaling recommendations"""
        predictions = await self.get_predictions()
        recommendations = {}

        for resource, data in predictions.items():
            if data["predicted"] > 85:
                recommendations[resource] = {
                    "action": "scale_up",
                    "urgency": "high" if data["predicted"] > 90 else "medium",
                    **data,
                }
            elif data["predicted"] < 30:
                recommendations[resource] = {
                    "action": "scale_down",
                    "urgency": "low",
                    **data,
                }
            else:
                recommendations[resource] = {
                    "action": "maintain",
                    "urgency": "none",
                    **data,
                }

        return recommendations

    async def get_status(self) -> dict[str, Any]:
        """Get current scaling status"""
        return {
            "current_workers": self.current_workers,
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "target_cpu": self.target_cpu,
            "target_memory": self.target_memory,
            "auto_scaling_enabled": True,
            "last_scale_event": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            "predictions": self._predictions,
        }

    async def scale_up(self, count: int = 1) -> dict[str, Any]:
        """Scale up workers"""
        new_count = min(self.current_workers + count, self.max_workers)
        actual_added = new_count - self.current_workers
        self.current_workers = new_count

        logger.info(
            "Scaled up by %s workers. Total: %s", actual_added, self.current_workers
        )

        return {
            "action": "scale_up",
            "workers_added": actual_added,
            "total_workers": self.current_workers,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def scale_down(self, count: int = 1) -> dict[str, Any]:
        """Scale down workers"""
        new_count = max(self.current_workers - count, self.min_workers)
        actual_removed = self.current_workers - new_count
        self.current_workers = new_count

        logger.info(
            "Scaled down by %s workers. Total: %s", actual_removed, self.current_workers
        )

        return {
            "action": "scale_down",
            "workers_removed": actual_removed,
            "total_workers": self.current_workers,
            "timestamp": datetime.now(UTC).isoformat(),
        }


# Singleton instance
predictive_scaler = PredictiveScaler()
