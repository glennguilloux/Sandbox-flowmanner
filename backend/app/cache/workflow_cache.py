#!/usr/bin/env python3
"""
Redis Cache Service for Workflows

Provides caching functionality for workflow metadata and scan results.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import redis

logger = logging.getLogger(__name__)


class WorkflowCache:
    """
    Redis-based cache for workflow data
    """

    def __init__(self, redis_url: str = "redis://redis:6379", default_ttl: int = 3600):
        """
        Initialize workflow cache

        Args:
            redis_url: Redis connection URL
            default_ttl: Default time-to-live in seconds
        """
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self.client = None
        self._connect()

    def _connect(self):
        """Connect to Redis"""
        try:
            self.client = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            self.client.ping()
            logger.info("✅ Redis connection established")
        except Exception as e:
            logger.warning('⚠️ Redis connection failed: %s. Using in-memory cache only.', e)
            self.client = None

    def store_workflow(self, workflow: dict[str, Any], ttl: int | None = None):
        """
        Store workflow metadata in cache

        Args:
            workflow: Workflow metadata dictionary
            ttl: Time-to-live in seconds (uses default if None)
        """
        if not self.client:
            return

        try:
            workflow_id = workflow.get("id")
            if not workflow_id:
                logger.warning("Workflow missing ID, skipping cache")
                return

            key = f"workflow:data:{workflow_id}"
            serialized = json.dumps(workflow)

            if ttl is None:
                ttl = self.default_ttl

            self.client.setex(key, ttl, serialized)
            logger.debug('Cached workflow %s', workflow_id)

        except Exception as e:
            logger.error('Error caching workflow: %s', e)

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        """
        Retrieve workflow metadata from cache

        Args:
            workflow_id: Workflow identifier

        Returns:
            Workflow metadata or None
        """
        if not self.client:
            return None

        try:
            key = f"workflow:data:{workflow_id}"
            cached = self.client.get(key)

            if cached:
                return json.loads(cached)

            return None

        except Exception as e:
            logger.error('Error retrieving workflow from cache: %s', e)
            return None

    def store_workflow_list(
        self, workflows: list[dict[str, Any]], ttl: int | None = None
    ):
        """
        Store list of workflows

        Args:
            workflows: List of workflow metadata
            ttl: Time-to-live
        """
        if not self.client:
            return

        try:
            # Store each workflow individually
            for workflow in workflows:
                self.store_workflow(workflow, ttl)

            # Store the list of IDs
            workflow_ids = [w.get("id") for w in workflows if w.get("id")]
            key = "workflow:list:all"

            if ttl is None:
                ttl = self.default_ttl

            self.client.setex(key, ttl, json.dumps(workflow_ids))
            logger.info('Cached workflow list with %s items', len(workflow_ids))

        except Exception as e:
            logger.error('Error caching workflow list: %s', e)

    def get_workflow_list(self) -> list[dict[str, Any]]:
        """
        Retrieve list of all workflows from cache

        Returns:
            List of workflow metadata
        """
        if not self.client:
            return []

        try:
            key = "workflow:list:all"
            cached = self.client.get(key)

            if not cached:
                return []

            workflow_ids = json.loads(cached)
            workflows = []

            for workflow_id in workflow_ids:
                workflow = self.get_workflow(workflow_id)
                if workflow:
                    workflows.append(workflow)

            return workflows

        except Exception as e:
            logger.error('Error retrieving workflow list: %s', e)
            return []

    def store_scan_results(self, results: dict[str, Any], ttl: int | None = None):
        """
        Store scan results

        Args:
            results: Scan results dictionary
            ttl: Time-to-live
        """
        if not self.client:
            return

        try:
            key = "workflow:scan:latest"

            if ttl is None:
                ttl = self.default_ttl * 2  # Longer TTL for scan results

            self.client.setex(key, ttl, json.dumps(results))
            logger.info("Cached scan results")

        except Exception as e:
            logger.error('Error caching scan results: %s', e)

    def get_scan_results(self) -> dict[str, Any] | None:
        """
        Retrieve latest scan results

        Returns:
            Scan results or None
        """
        if not self.client:
            return None

        try:
            key = "workflow:scan:latest"
            cached = self.client.get(key)

            if cached:
                return json.loads(cached)

            return None

        except Exception as e:
            logger.error('Error retrieving scan results: %s', e)
            return None

    def invalidate_workflow(self, workflow_id: str):
        """
        Remove a workflow from cache

        Args:
            workflow_id: Workflow identifier
        """
        if not self.client:
            return

        try:
            # Remove workflow data
            key = f"workflow:data:{workflow_id}"
            self.client.delete(key)

            # Remove from list cache (will be rebuilt on next get)
            list_key = "workflow:list:all"
            if self.client.exists(list_key):
                cached = self.client.get(list_key)
                if cached:
                    workflow_ids = json.loads(cached)
                    if workflow_id in workflow_ids:
                        workflow_ids.remove(workflow_id)
                        self.client.setex(
                            list_key, self.default_ttl, json.dumps(workflow_ids)
                        )

            logger.info('Invalidated workflow %s', workflow_id)

        except Exception as e:
            logger.error('Error invalidating workflow: %s', e)

    def store_imported_workflow(
        self, imported_workflow: dict[str, Any], ttl: int | None = None
    ):
        """
        Store imported workflow metadata in cache

        Args:
            imported_workflow: Imported workflow metadata dictionary
            ttl: Time-to-live in seconds (uses default if None)
        """
        if not self.client:
            return

        try:
            import_id = imported_workflow.get("import_id")
            if not import_id:
                logger.warning("Imported workflow missing import_id, skipping cache")
                return

            key = f"workflow:import:{import_id}"
            serialized = json.dumps(imported_workflow)

            if ttl is None:
                ttl = self.default_ttl

            self.client.setex(key, ttl, serialized)
            logger.debug('Cached imported workflow %s', import_id)

        except Exception as e:
            logger.error('Error caching imported workflow: %s', e)

    def get_imported_workflow(self, import_id: str) -> dict[str, Any] | None:
        """
        Retrieve imported workflow metadata from cache

        Args:
            import_id: Import identifier

        Returns:
            Imported workflow metadata or None
        """
        if not self.client:
            return None

        try:
            key = f"workflow:import:{import_id}"
            cached = self.client.get(key)

            if cached:
                return json.loads(cached)

            return None

        except Exception as e:
            logger.error('Error retrieving imported workflow from cache: %s', e)
            return None

    def store_imported_workflow_list(
        self, imported_workflows: list[dict[str, Any]], ttl: int | None = None
    ):
        """
        Store list of imported workflows

        Args:
            imported_workflows: List of imported workflow metadata
            ttl: Time-to-live
        """
        if not self.client:
            return

        try:
            # Store each imported workflow individually
            for imported_workflow in imported_workflows:
                self.store_imported_workflow(imported_workflow, ttl)

            # Store the list of import IDs
            import_ids = [
                w.get("import_id") for w in imported_workflows if w.get("import_id")
            ]
            key = "workflow:import:list:all"

            if ttl is None:
                ttl = self.default_ttl

            self.client.setex(key, ttl, json.dumps(import_ids))
            logger.info('Cached imported workflow list with %s items', len(import_ids))

        except Exception as e:
            logger.error('Error caching imported workflow list: %s', e)

    def get_imported_workflow_list(self) -> list[dict[str, Any]]:
        """
        Retrieve list of all imported workflows from cache

        Returns:
            List of imported workflow metadata
        """
        if not self.client:
            return []

        try:
            key = "workflow:import:list:all"
            cached = self.client.get(key)

            if not cached:
                return []

            import_ids = json.loads(cached)
            imported_workflows = []

            for import_id in import_ids:
                imported_workflow = self.get_imported_workflow(import_id)
                if imported_workflow:
                    imported_workflows.append(imported_workflow)

            return imported_workflows

        except Exception as e:
            logger.error('Error retrieving imported workflow list: %s', e)
            return []

    def invalidate_import_cache(self):
        """Clear all imported workflow cache"""
        if not self.client:
            return

        try:
            # Find all import keys
            import_keys = self.client.keys("workflow:import:*")
            if import_keys:
                self.client.delete(*import_keys)
                logger.info('Invalidated %s import cache keys', len(import_keys))
        except Exception as e:
            logger.error('Error invalidating import cache: %s', e)

    def invalidate_all(self):
        """Clear all workflow-related cache"""
        if not self.client:
            return

        try:
            # Find all workflow keys
            workflow_keys = self.client.keys("workflow:*")
            if workflow_keys:
                self.client.delete(*workflow_keys)
                logger.info('Invalidated %s workflow cache keys', len(workflow_keys))
        except Exception as e:
            logger.error('Error invalidating all cache: %s', e)

    def store_change_event(self, change: dict[str, Any]):
        """
        Store a change event for tracking

        Args:
            change: Change event data
        """
        if not self.client:
            return

        try:
            timestamp = change.get("timestamp", datetime.now(UTC).isoformat())
            workflow_id = change.get("workflow_id", "unknown")

            key = f"workflow:changes:{workflow_id}"

            # Store as a list with limited size
            change_json = json.dumps(change)
            self.client.lpush(key, change_json)
            self.client.ltrim(key, 0, 99)  # Keep last 100 changes

            # Set TTL
            self.client.expire(key, self.default_ttl * 24)  # 24 hours

            logger.debug('Stored change event for %s', workflow_id)

        except Exception as e:
            logger.error('Error storing change event: %s', e)

    def get_change_history(
        self, workflow_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Get change history for a workflow

        Args:
            workflow_id: Workflow identifier
            limit: Number of changes to return

        Returns:
            List of change events
        """
        if not self.client:
            return []

        try:
            key = f"workflow:changes:{workflow_id}"
            changes_data = self.client.lrange(key, 0, limit - 1)

            changes = []
            for data in changes_data:
                try:
                    change = json.loads(data)
                    changes.append(change)
                except Exception:
                    logger.debug("Failed to parse cached change event")

            return changes

        except Exception as e:
            logger.error('Error retrieving change history: %s', e)
            return []

    def store_n8n_workflow(self, workflow: dict[str, Any], ttl: int | None = None):
        """
        Store n8n workflow metadata in cache

        Args:
            workflow: n8n workflow metadata dictionary
            ttl: Time-to-live in seconds (uses default if None)
        """
        if not self.client:
            return

        try:
            workflow_id = workflow.get("workflow_id")
            if not workflow_id:
                logger.warning("n8n workflow missing workflow_id, skipping cache")
                return

            key = f"n8n:workflow:{workflow_id}"
            serialized = json.dumps(workflow)

            if ttl is None:
                ttl = self.default_ttl

            self.client.setex(key, ttl, serialized)
            logger.debug('Cached n8n workflow %s', workflow_id)

        except Exception as e:
            logger.error('Error caching n8n workflow: %s', e)

    def get_n8n_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        """
        Retrieve n8n workflow metadata from cache

        Args:
            workflow_id: n8n workflow identifier

        Returns:
            n8n workflow metadata or None
        """
        if not self.client:
            return None

        try:
            key = f"n8n:workflow:{workflow_id}"
            cached = self.client.get(key)

            if cached:
                return json.loads(cached)

            return None

        except Exception as e:
            logger.error('Error retrieving n8n workflow from cache: %s', e)
            return None

    def store_n8n_workflow_list(
        self, workflows: list[dict[str, Any]], ttl: int | None = None
    ):
        """
        Store list of n8n workflows

        Args:
            workflows: List of n8n workflow metadata
            ttl: Time-to-live
        """
        if not self.client:
            return

        try:
            # Store each workflow individually
            for workflow in workflows:
                self.store_n8n_workflow(workflow, ttl)

            # Store the list of workflow IDs
            workflow_ids = [
                w.get("workflow_id") for w in workflows if w.get("workflow_id")
            ]
            key = "n8n:workflow:list:all"

            if ttl is None:
                ttl = self.default_ttl

            self.client.setex(key, ttl, json.dumps(workflow_ids))
            logger.info('Cached n8n workflow list with %s items', len(workflow_ids))

        except Exception as e:
            logger.error('Error caching n8n workflow list: %s', e)

    def get_n8n_workflow_list(self) -> list[dict[str, Any]]:
        """
        Retrieve list of all n8n workflows from cache

        Returns:
            List of n8n workflow metadata
        """
        if not self.client:
            return []

        try:
            key = "n8n:workflow:list:all"
            cached = self.client.get(key)

            if not cached:
                return []

            workflow_ids = json.loads(cached)
            workflows = []

            for workflow_id in workflow_ids:
                workflow = self.get_n8n_workflow(workflow_id)
                if workflow:
                    workflows.append(workflow)

            return workflows

        except Exception as e:
            logger.error('Error retrieving n8n workflow list: %s', e)
            return []

    def invalidate_n8n_workflow(self, workflow_id: str):
        """
        Remove an n8n workflow from cache

        Args:
            workflow_id: n8n workflow identifier
        """
        if not self.client:
            return

        try:
            # Remove workflow data
            key = f"n8n:workflow:{workflow_id}"
            self.client.delete(key)

            # Remove from list cache
            list_key = "n8n:workflow:list:all"
            if self.client.exists(list_key):
                cached = self.client.get(list_key)
                if cached:
                    workflow_ids = json.loads(cached)
                    if workflow_id in workflow_ids:
                        workflow_ids.remove(workflow_id)
                        self.client.setex(
                            list_key, self.default_ttl, json.dumps(workflow_ids)
                        )

            logger.info('Invalidated n8n workflow %s', workflow_id)

        except Exception as e:
            logger.error('Error invalidating n8n workflow: %s', e)

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Cache statistics
        """
        if not self.client:
            return {"connected": False}

        try:
            # Count workflow keys
            workflow_keys = self.client.keys("workflow:data:*")
            list_keys = self.client.keys("workflow:list:*")
            change_keys = self.client.keys("workflow:changes:*")

            # Count n8n workflow keys
            n8n_workflow_keys = self.client.keys("n8n:workflow:*")

            return {
                "connected": True,
                "total_workflows": len(workflow_keys),
                "list_cache_entries": len(list_keys),
                "change_history_entries": len(change_keys),
                "total_n8n_workflows": len(n8n_workflow_keys),
                "total_keys": len(self.client.keys("workflow:*"))
                + len(n8n_workflow_keys),
            }

        except Exception as e:
            logger.error('Error getting cache stats: %s', e)
            return {"connected": False, "error": str(e)}


# Global cache instance
_cache_instance = None


def get_workflow_cache(redis_url: str = None, default_ttl: int = 3600) -> WorkflowCache:
    """
    Get or create global workflow cache instance

    Args:
        redis_url: Redis URL (uses env var or default if None)
        default_ttl: Default TTL

    Returns:
        WorkflowCache instance
    """
    global _cache_instance

    if _cache_instance is None:
        import os

        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379")

        _cache_instance = WorkflowCache(redis_url, default_ttl)

    return _cache_instance


def init_cache(redis_url: str = None):
    """
    Initialize global cache instance

    Args:
        redis_url: Redis URL
    """
    global _cache_instance
    _cache_instance = get_workflow_cache(redis_url)
