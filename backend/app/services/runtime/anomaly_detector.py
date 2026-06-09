"""
Phase 4: Anomaly Detector
Detect anomalies in system metrics
"""

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detect anomalies in system metrics"""

    def __init__(self):
        self._anomalies: list[dict[str, Any]] = []
        self._resolved: list[str] = []

    async def get_recent_anomalies(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get recent anomalies"""
        # Simulate some anomalies
        if not self._anomalies:
            self._anomalies = self._generate_sample_anomalies()

        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        return [
            a
            for a in self._anomalies
            if datetime.fromisoformat(a["detected_at"]) > cutoff
            and a["anomaly_id"] not in self._resolved
        ]

    def _generate_sample_anomalies(self) -> list[dict[str, Any]]:
        """Generate sample anomalies for demo"""
        anomaly_types = ["spike", "drop", "trend_change"]
        resources = ["cpu", "memory", "network", "disk_io"]
        severities = ["low", "medium", "high", "critical"]

        anomalies = []
        for _i in range(random.randint(2, 5)):
            resource = random.choice(resources)
            anomaly_type = random.choice(anomaly_types)
            severity = random.choice(severities)

            value = (
                random.uniform(70, 95)
                if anomaly_type == "spike"
                else random.uniform(5, 30)
            )
            expected_min = 30 if anomaly_type == "spike" else 50
            expected_max = 70 if anomaly_type == "spike" else 80

            anomalies.append(
                {
                    "anomaly_id": str(uuid.uuid4()),
                    "anomaly_type": anomaly_type,
                    "resource_type": resource,
                    "severity": severity,
                    "detected_at": (
                        datetime.now(UTC) - timedelta(hours=random.randint(1, 24))
                    ).isoformat(),
                    "value": round(value, 2),
                    "expected_range": [expected_min, expected_max],
                    "description": f"{anomaly_type.replace('_', ' ').title()} detected in {resource}",
                    "auto_resolvable": severity in ["low", "medium"],
                }
            )

        return anomalies

    async def resolve_anomaly(self, anomaly_id: str) -> bool:
        """Mark an anomaly as resolved"""
        self._resolved.append(anomaly_id)
        logger.info("Anomaly %s resolved", anomaly_id)
        return True


# Singleton instance
anomaly_detector = AnomalyDetector()
