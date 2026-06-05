"""Plugin Runtime — manages plugin lifecycle and execution.

Central coordinator for plugin installation, loading, enabling/disabling,
and execution.  On startup, loads all enabled plugins from the database
and registers their handlers with the NodeHandlerRegistry.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.plugin_models import InstalledPlugin, PluginStatus
from app.sdk.base import BaseNodeHandler, BasePlugin
from app.sdk.context import PluginContext
from app.sdk.exceptions import (
    PluginError,
    PluginLoadError,
)
from app.services.plugin_loader import (
    load_plugin_from_dir,
    load_plugin_from_fmp,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.sdk.manifest import PluginManifest

logger = logging.getLogger(__name__)


class _PluginHandlerAdapter(BaseNodeHandler):
    """Wraps a plugin's BaseNodeHandler to match graph_node_handlers.BaseNodeHandler interface.

    The graph executor's BaseNodeHandler.execute() takes (node, context, interpreter),
    but the plugin SDK's BaseNodeHandler.execute() takes a PluginContext.
    This adapter bridges the two.
    """

    def __init__(
        self,
        plugin_handler: BaseNodeHandler,
        plugin_name: str,
        permissions: list[str],
        config: dict[str, Any] | None = None,
    ) -> None:
        self._handler = plugin_handler
        self._plugin_name = plugin_name
        self._permissions = set(permissions)
        self._config = config or {}
        # Copy the node_type_id from the wrapped handler
        self.node_type_id = plugin_handler.node_type_id

    async def execute(self, node: dict, context: Any, interpreter: Any = None) -> dict:
        """Bridge: convert graph executor context to PluginContext, run handler."""
        data = node.get("data", {})
        inputs = data.get("inputs") or data.get("params") or {}

        # Resolve interpolation in inputs
        if interpreter and hasattr(context, "resolve_interpolation"):
            resolved_inputs = {}
            for k, v in inputs.items():
                if isinstance(v, str):
                    resolved_inputs[k] = context.resolve_interpolation(v)
                else:
                    resolved_inputs[k] = v
            inputs = resolved_inputs

        # Get previous node outputs
        node_outputs = {}
        if hasattr(context, "_node_outputs"):
            node_outputs = context._node_outputs

        workspace_id = None
        execution_id = None
        if interpreter:
            if hasattr(interpreter, "workflow"):
                workspace_id = getattr(interpreter.workflow, "workspace_id", None)
            if hasattr(interpreter, "execution"):
                execution_id = getattr(interpreter.execution, "id", None)

        plugin_ctx = PluginContext(
            inputs=inputs,
            config=self._config,
            node_outputs=node_outputs,
            workspace_id=workspace_id,
            execution_id=execution_id,
        )

        # Run validation
        errors = await self._handler.validate(plugin_ctx)
        if errors:
            return {"success": False, "error": f"Validation failed: {errors}"}

        # Execute with timing
        start = time.monotonic()
        try:
            result = await self._handler.execute(plugin_ctx)
            elapsed_ms = (time.monotonic() - start) * 1000
            return {
                "success": True,
                "output": result,
                "plugin": self._plugin_name,
                "elapsed_ms": elapsed_ms,
            }
        except PluginError as e:
            logger.warning("Plugin '%s' error: %s", self._plugin_name, e)
            return {"success": False, "error": str(e), "plugin": self._plugin_name}
        except Exception as e:
            logger.exception("Plugin '%s' handler execution failed", self._plugin_name)
            return {"success": False, "error": str(e), "plugin": self._plugin_name}

    async def validate(self, node: dict) -> list[str]:
        return []


class PluginRuntime:
    """Manages the full plugin lifecycle.

    Usage::

        runtime = PluginRuntime()
        await runtime.load_installed(db)
        runtime.execute_plugin_node(node_type_id, node, context, interpreter)
    """

    def __init__(self) -> None:
        # plugin_name → BasePlugin instance
        self._plugins: dict[str, BasePlugin] = {}
        # node_type_id → _PluginHandlerAdapter
        self._handlers: dict[str, _PluginHandlerAdapter] = {}
        # plugin_name → manifest
        self._manifests: dict[str, PluginManifest] = {}
        # plugin_name → unpack directory path
        self._install_paths: dict[str, Path] = {}

    async def load_installed(self, db: AsyncSession) -> int:
        """Load all enabled plugins from the database.

        Called during application startup.  Returns the count of
        successfully loaded plugins.
        """
        result = await db.execute(
            select(InstalledPlugin).where(
                InstalledPlugin.status == PluginStatus.ENABLED
            )
        )
        plugins = result.scalars().all()

        loaded = 0
        for plugin_row in plugins:
            try:
                await self._load_from_db_record(plugin_row)
                loaded += 1
            except Exception as e:
                logger.error(
                    "Failed to load plugin '%s' v%s: %s",
                    plugin_row.name, plugin_row.version, e,
                )
                # Mark as error state
                plugin_row.status = PluginStatus.ERROR
                plugin_row.last_error = str(e)

        await db.commit()
        logger.info("Plugin runtime: loaded %d/%d enabled plugins", loaded, len(plugins))
        return loaded

    async def install(
        self,
        db: AsyncSession,
        *,
        fmp_path: Path | None = None,
        plugin_dir: Path | None = None,
        workspace_id: str,
        source: str = "upload",
        listing_id: str | None = None,
    ) -> InstalledPlugin:
        """Install a plugin from a .fmp file or unpacked directory.

        Validates the manifest, imports the entry point, creates a DB record,
        and registers the handlers.
        """
        if fmp_path:
            manifest, plugin_instance, unpack_dir = load_plugin_from_fmp(fmp_path)
        elif plugin_dir:
            manifest, plugin_instance = load_plugin_from_dir(plugin_dir)
            unpack_dir = plugin_dir
        else:
            raise ValueError("Either fmp_path or plugin_dir must be provided")

        # Security scan before install (Phase 9.6)
        scan_result = None
        try:
            from app.services.plugin_scanner import get_plugin_scanner
            scanner = get_plugin_scanner()
            scan_result = scanner.scan(
                unpack_dir,
                declared_permissions=manifest.permissions,
            )
            if not scan_result.passed:
                logger.warning(
                    "Plugin '%s' failed security scan (risk_score=%d). Installing with pending review.",
                    manifest.name, scan_result.risk_score,
                )
        except Exception as e:
            logger.debug("Plugin scan failed (non-blocking): %s", e)

        # Determine review status based on scan
        review_status = "pending"
        if scan_result and scan_result.passed and scan_result.risk_score < 30:
            review_status = "approved"  # Auto-approve low-risk plugins

        # Create DB record
        plugin_row = InstalledPlugin(
            workspace_id=workspace_id,
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            author=manifest.author,
            manifest_json=manifest.model_dump_json(),
            source=source,
            listing_id=listing_id,
            install_path=str(unpack_dir),
            status=PluginStatus.ENABLED,
            permissions_json=json.dumps(manifest.permissions),
            node_types_json=json.dumps([
                {"id": nt.id, "label": nt.label, "category": nt.category}
                for nt in manifest.node_types
            ]),
            review_status=review_status,
            scan_risk_score=scan_result.risk_score if scan_result else 0,
            scan_result_json=json.dumps(scan_result.to_dict()) if scan_result else None,
        )
        db.add(plugin_row)
        await db.flush()

        # Register handlers in memory
        self._register_handlers(plugin_row, manifest, plugin_instance)

        logger.info(
            "Installed plugin '%s' v%s (%d node types)",
            manifest.name, manifest.version, len(manifest.node_types),
        )
        return plugin_row

    async def uninstall(self, db: AsyncSession, plugin_id: str) -> bool:
        """Uninstall a plugin — unload from registry and mark as uninstalled."""
        result = await db.execute(
            select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
        )
        plugin_row = result.scalar_one_or_none()
        if plugin_row is None:
            return False

        # Unload from memory
        self._unload(plugin_row.name)

        # Update DB
        plugin_row.status = PluginStatus.UNINSTALLED
        await db.commit()
        return True

    async def enable(self, db: AsyncSession, plugin_id: str) -> bool:
        """Enable a disabled plugin — re-register its handlers."""
        result = await db.execute(
            select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
        )
        plugin_row = result.scalar_one_or_none()
        if plugin_row is None:
            return False

        try:
            await self._load_from_db_record(plugin_row)
            plugin_row.status = PluginStatus.ENABLED
            await db.commit()
            return True
        except Exception as e:
            plugin_row.status = PluginStatus.ERROR
            plugin_row.last_error = str(e)
            await db.commit()
            return False

    async def disable(self, db: AsyncSession, plugin_id: str) -> bool:
        """Disable a plugin — remove handlers from registry, keep DB record."""
        result = await db.execute(
            select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
        )
        plugin_row = result.scalar_one_or_none()
        if plugin_row is None:
            return False

        self._unload(plugin_row.name)
        plugin_row.status = PluginStatus.DISABLED
        await db.commit()
        return True

    def get_handler(self, node_type_id: str) -> _PluginHandlerAdapter | None:
        """Get a plugin handler for a node type ID."""
        return self._handlers.get(node_type_id)

    def get_registered_node_types(self) -> list[dict[str, Any]]:
        """Return all registered plugin node types with metadata."""
        types = []
        for node_type_id, handler in self._handlers.items():
            manifest = self._manifests.get(handler._plugin_name)
            types.append({
                "node_type_id": node_type_id,
                "plugin_name": handler._plugin_name,
                "permissions": list(handler._permissions),
                "manifest": manifest.model_dump() if manifest else None,
            })
        return types

    def is_plugin_node(self, node_type_id: str) -> bool:
        """Check if a node type is provided by a plugin."""
        return node_type_id in self._handlers

    async def record_execution(
        self, db: AsyncSession, plugin_name: str, *, success: bool, error: str | None = None, elapsed_ms: float = 0.0
    ) -> None:
        """Persist execution stats to the installed_plugins table."""
        try:
            result = await db.execute(
                select(InstalledPlugin).where(InstalledPlugin.name == plugin_name)
            )
            plugin_row = result.scalar_one_or_none()
            if plugin_row is None:
                return
            plugin_row.execution_count = (plugin_row.execution_count or 0) + 1
            plugin_row.last_executed_at = datetime.now(UTC)
            if not success:
                plugin_row.error_count = (plugin_row.error_count or 0) + 1
                plugin_row.crash_count = (plugin_row.crash_count or 0) + 1
                if error:
                    plugin_row.last_error = error[:2000]

            # Update p99 latency (track max as p99 proxy — real p99 needs a histogram)
            if elapsed_ms > 0:
                old_p99 = plugin_row.p99_latency_ms or 0.0
                plugin_row.p99_latency_ms = max(old_p99, elapsed_ms)
            await db.flush()
        except Exception as e:
            logger.debug("Failed to record plugin execution stats: %s", e)

    def get_stats(self) -> dict[str, Any]:
        """Return runtime stats."""
        return {
            "loaded_plugins": len(self._plugins),
            "registered_node_types": len(self._handlers),
            "plugins": {
                name: {
                    "version": m.version,
                    "node_types": [nt.id for nt in m.node_types],
                }
                for name, m in self._manifests.items()
            },
        }

    # ── Internal helpers ──────────────────────────────────────────

    async def _load_from_db_record(self, plugin_row: InstalledPlugin) -> None:
        """Load a plugin from its DB record and install path."""
        install_path = plugin_row.install_path
        if not install_path:
            raise PluginLoadError(
                "No install_path recorded",
                plugin_name=plugin_row.name,
            )

        plugin_dir = Path(install_path)
        if not plugin_dir.exists():
            raise PluginLoadError(
                f"Install path does not exist: {install_path}",
                plugin_name=plugin_row.name,
            )

        manifest, plugin_instance = load_plugin_from_dir(plugin_dir)
        self._register_handlers(plugin_row, manifest, plugin_instance)

    def _register_handlers(
        self,
        plugin_row: InstalledPlugin,
        manifest: PluginManifest,
        plugin_instance: BasePlugin,
    ) -> None:
        """Register all handlers from a plugin into the runtime."""
        plugin_name = manifest.name
        permissions = manifest.permissions or []

        # Store plugin and manifest
        self._plugins[plugin_name] = plugin_instance
        self._manifests[plugin_name] = manifest
        if plugin_row.install_path:
            self._install_paths[plugin_name] = Path(plugin_row.install_path)

        # Register each handler
        for handler_cls in plugin_instance.handlers:
            handler_instance = handler_cls()
            adapter = _PluginHandlerAdapter(
                plugin_handler=handler_instance,
                plugin_name=plugin_name,
                permissions=permissions,
            )
            self._handlers[handler_instance.node_type_id] = adapter
            logger.info(
                "Registered plugin node type '%s' from '%s'",
                handler_instance.node_type_id, plugin_name,
            )

    def _unload(self, plugin_name: str) -> None:
        """Remove all handlers for a plugin from memory."""
        plugin = self._plugins.pop(plugin_name, None)
        if plugin is None:
            return

        # Find and remove all handlers belonging to this plugin
        to_remove = [
            nid for nid, h in self._handlers.items()
            if h._plugin_name == plugin_name
        ]
        for nid in to_remove:
            del self._handlers[nid]
            logger.info("Unregistered plugin node type '%s'", nid)

        self._manifests.pop(plugin_name, None)
        self._install_paths.pop(plugin_name, None)


# ── Singleton ──────────────────────────────────────────────────────

_runtime: PluginRuntime | None = None


def get_plugin_runtime() -> PluginRuntime:
    """Get or create the global PluginRuntime singleton."""
    global _runtime
    if _runtime is None:
        _runtime = PluginRuntime()
    return _runtime
