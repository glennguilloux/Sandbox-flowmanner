"""
Phase 4: Recovery Strategies
Different recovery strategies for various error types
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

class RecoveryStrategies:
    """Collection of recovery strategies"""

    def __init__(self):
        self._strategies = [
            {
                "strategy_id": "restart-service",
                "name": "Restart Service",
                "description": "Restart the affected service",
                "type": "automatic",
                "auto_execute": True,
                "applicable_errors": ["service_crash", "timeout", "connection_lost"],
                "priority": 1
            },
            {
                "strategy_id": "clear-cache",
                "name": "Clear Cache",
                "description": "Clear application cache to resolve corruption",
                "type": "automatic",
                "auto_execute": True,
                "applicable_errors": ["cache_error", "memory_leak"],
                "priority": 2
            },
            {
                "strategy_id": "scale-up",
                "name": "Scale Up Resources",
                "description": "Add more workers to handle load",
                "type": "automatic",
                "auto_execute": True,
                "applicable_errors": ["high_load", "resource_exhausted"],
                "priority": 3
            },
            {
                "strategy_id": "failover",
                "name": "Failover to Backup",
                "description": "Switch to backup system",
                "type": "automatic",
                "auto_execute": False,
                "applicable_errors": ["primary_failure", "datacenter_outage"],
                "priority": 1
            },
            {
                "strategy_id": "rollback",
                "name": "Rollback Deployment",
                "description": "Rollback to previous stable version",
                "type": "manual",
                "auto_execute": False,
                "applicable_errors": ["deployment_error", "version_incompatible"],
                "priority": 2
            }
        ]

    def get_all_strategies(self) -> list[dict[str, Any]]:
        """Get all available strategies"""
        return self._strategies

    def get_strategy(self, strategy_id: str) -> dict[str, Any]:
        """Get a specific strategy by ID"""
        for strategy in self._strategies:
            if strategy["strategy_id"] == strategy_id:
                return strategy
        return None

    def get_strategies_for_error(self, error_type: str) -> list[dict[str, Any]]:
        """Get applicable strategies for an error type"""
        return [
            s for s in self._strategies
            if error_type in s["applicable_errors"]
        ]

# Singleton instance
recovery_strategies = RecoveryStrategies()
