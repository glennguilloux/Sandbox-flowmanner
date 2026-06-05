"""Plugin API — CRUD endpoints for managing installed plugins.

Phase 9.5: Plugin API + Webhooks

Provides endpoints for:
- Installing plugins from .fmp packages
- Listing installed plugins per workspace
- Plugin detail, status, and execution stats
- Enable/disable plugins
- Uninstall plugins
- Direct test execution
- Available node types from all plugins
"""

from __future__ import annotations

import contextlib
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.models.plugin_models import InstalledPlugin, PluginStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins", tags=["plugins"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class PluginResponse(BaseModel):
    id: str
    name: str
    version: str
    description: str | None = None
    author: str | None = None
    source: str = "upload"
    status: str = "installed"
    execution_count: int = 0
    error_count: int = 0
    last_executed_at: str | None = None
    last_error: str | None = None
    permissions: list[str] = []
    node_types: list[dict[str, Any]] = []
    created_at: str = ""
    updated_at: str = ""


class PluginStatusResponse(BaseModel):
    id: str
    name: str
    version: str
    status: str
    health: str  # healthy, degraded, unhealthy
    execution_count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    last_executed_at: str | None = None
    last_error: str | None = None
    registered_node_types: list[str] = []


class PluginListResponse(BaseModel):
    items: list[PluginResponse]
    total: int


class PluginExecuteRequest(BaseModel):
    node_type_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class PluginExecuteResponse(BaseModel):
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    elapsed_ms: float = 0.0
    plugin: str | None = None


class PluginToggleRequest(BaseModel):
    enabled: bool


class NodeTypeResponse(BaseModel):
    node_type_id: str
    plugin_name: str
    permissions: list[str] = []
    label: str | None = None
    category: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _to_plugin_response(p: InstalledPlugin) -> PluginResponse:
    permissions = []
    if p.permissions_json:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            permissions = json.loads(p.permissions_json)

    node_types = []
    if p.node_types_json:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            node_types = json.loads(p.node_types_json)

    return PluginResponse(
        id=p.id,
        name=p.name,
        version=p.version,
        description=p.description,
        author=p.author,
        source=p.source or "upload",
        status=p.status,
        execution_count=p.execution_count or 0,
        error_count=p.error_count or 0,
        last_executed_at=p.last_executed_at.isoformat() if p.last_executed_at else None,
        last_error=p.last_error,
        permissions=permissions,
        node_types=node_types,
        created_at=p.created_at.isoformat() if p.created_at else "",
        updated_at=p.updated_at.isoformat() if p.updated_at else "",
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=PluginListResponse)
async def list_plugins(
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    """List installed plugins for the current workspace."""
    query = select(InstalledPlugin)
    if workspace_id:
        query = query.where(InstalledPlugin.workspace_id == workspace_id)
    if status_filter:
        query = query.where(InstalledPlugin.status == status_filter)
    query = query.order_by(InstalledPlugin.name.asc())

    result = await db.execute(query)
    plugins = result.scalars().all()

    return PluginListResponse(
        items=[_to_plugin_response(p) for p in plugins],
        total=len(plugins),
    )


@router.get("/node-types", response_model=list[NodeTypeResponse])
async def list_plugin_node_types(
    user: User = Depends(get_current_user),
):
    """List all available plugin node types with their schemas.

    Used by the graph editor to populate the node palette with plugin nodes.
    """
    from app.services.plugin_runtime import get_plugin_runtime

    runtime = get_plugin_runtime()
    registered = runtime.get_registered_node_types()

    node_types = []
    for entry in registered:
        manifest_data = entry.get("manifest")
        node_type_id = entry["node_type_id"]
        label = node_type_id
        category = "custom"
        description = None
        icon = None
        color = None
        inputs = {}
        outputs = {}

        if manifest_data:
            # manifest_data may be a PluginManifest Pydantic model or dict
            manifest_dict = (
                manifest_data.model_dump() if hasattr(manifest_data, "model_dump")
                else manifest_data if isinstance(manifest_data, dict)
                else {}
            )
            node_types_list = manifest_dict.get("node_types", [])
            # Find the matching node type in the manifest
            for nt in node_types_list:
                if nt.get("id") == node_type_id:
                    label = nt.get("label", node_type_id)
                    category = nt.get("category", "custom")
                    description = nt.get("description")
                    icon = nt.get("icon")
                    color = nt.get("color")
                    # Convert NodeTypeInput/Output to plain dicts
                    for k, v in nt.get("inputs", {}).items():
                        if hasattr(v, "model_dump"):
                            inputs[k] = v.model_dump()
                        elif isinstance(v, dict):
                            inputs[k] = v
                        else:
                            inputs[k] = {"type": "object"}
                    for k, v in nt.get("outputs", {}).items():
                        if hasattr(v, "model_dump"):
                            outputs[k] = v.model_dump()
                        elif isinstance(v, dict):
                            outputs[k] = v
                        else:
                            outputs[k] = {"type": "object"}
                    break

        node_types.append(NodeTypeResponse(
            node_type_id=node_type_id,
            plugin_name=entry["plugin_name"],
            permissions=entry.get("permissions", []),
            label=label,
            category=category,
            description=description,
            icon=icon,
            color=color,
            inputs=inputs,
            outputs=outputs,
        ))

    return node_types


@router.post("", response_model=PluginResponse, status_code=status.HTTP_201_CREATED)
async def install_plugin(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    """Install a plugin from an uploaded .fmp package.

    Validates the manifest, imports the entry point, and registers handlers.
    """
    if not file.filename or not file.filename.endswith(".fmp"):
        raise HTTPException(400, "File must be a .fmp package")

    # Save uploaded file to temp directory
    tmp_dir = Path(tempfile.mkdtemp(prefix="fm_upload_"))
    fmp_path = tmp_dir / file.filename

    try:
        content = await file.read()
        fmp_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(400, f"Failed to read uploaded file: {e}")

    try:
        from app.services.plugin_runtime import get_plugin_runtime

        runtime = get_plugin_runtime()
        plugin_row = await runtime.install(
            db,
            fmp_path=fmp_path,
            workspace_id=workspace_id or str(user.id),
            source="upload",
        )
        await db.commit()
        await db.refresh(plugin_row)

        logger.info(
            "Plugin installed via API: %s v%s (user=%s, workspace=%s)",
            plugin_row.name, plugin_row.version, user.id, workspace_id,
        )
        return _to_plugin_response(plugin_row)

    except Exception as e:
        logger.error("Plugin install failed: %s", e)
        raise HTTPException(400, f"Plugin install failed: {e}")
    finally:
        # Clean up temp file
        try:
            fmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except Exception:
            pass


@router.get("/{plugin_id}", response_model=PluginResponse)
async def get_plugin(
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a single plugin by ID."""
    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(404, "Plugin not found")
    return _to_plugin_response(plugin)


@router.get("/{plugin_id}/status", response_model=PluginStatusResponse)
async def get_plugin_status(
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get plugin health and execution statistics."""
    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(404, "Plugin not found")

    exec_count = plugin.execution_count or 0
    err_count = plugin.error_count or 0
    error_rate = (err_count / exec_count * 100) if exec_count > 0 else 0.0

    # Determine health
    if plugin.status == PluginStatus.ERROR:
        health = "unhealthy"
    elif error_rate > 10:
        health = "degraded"
    else:
        health = "healthy"

    # Get registered node types from runtime
    from app.services.plugin_runtime import get_plugin_runtime
    runtime = get_plugin_runtime()
    registered_types = [
        nt["node_type_id"]
        for nt in runtime.get_registered_node_types()
        if nt["plugin_name"] == plugin.name
    ]

    return PluginStatusResponse(
        id=plugin.id,
        name=plugin.name,
        version=plugin.version,
        status=plugin.status,
        health=health,
        execution_count=exec_count,
        error_count=err_count,
        error_rate=round(error_rate, 2),
        last_executed_at=plugin.last_executed_at.isoformat() if plugin.last_executed_at else None,
        last_error=plugin.last_error,
        registered_node_types=registered_types,
    )


@router.patch("/{plugin_id}", response_model=PluginResponse)
async def toggle_plugin(
    plugin_id: str,
    payload: PluginToggleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Enable or disable a plugin."""
    from app.services.plugin_runtime import get_plugin_runtime

    runtime = get_plugin_runtime()

    if payload.enabled:
        success = await runtime.enable(db, plugin_id)
        action = "enabled"
    else:
        success = await runtime.disable(db, plugin_id)
        action = "disabled"

    if not success:
        raise HTTPException(400, f"Failed to {action.rstrip('d')} plugin")

    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(404, "Plugin not found")

    await db.commit()
    await db.refresh(plugin)

    logger.info("Plugin %s: %s", action, plugin.name)
    return _to_plugin_response(plugin)


@router.delete("/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Uninstall a plugin — unload from registry and mark as uninstalled."""
    from app.services.plugin_runtime import get_plugin_runtime

    runtime = get_plugin_runtime()
    success = await runtime.uninstall(db, plugin_id)

    if not success:
        raise HTTPException(404, "Plugin not found")

    await db.commit()

    logger.info("Plugin uninstalled: %s", plugin_id)
    return {"status": "uninstalled", "plugin_id": plugin_id}


@router.post("/{plugin_id}/execute", response_model=PluginExecuteResponse)
async def execute_plugin(
    plugin_id: str,
    payload: PluginExecuteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Execute a plugin node directly (test mode).

    Useful for testing plugin nodes without a full workflow execution.
    """
    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(404, "Plugin not found")
    if plugin.status != PluginStatus.ENABLED:
        raise HTTPException(400, f"Plugin is not enabled (status: {plugin.status})")

    from app.services.plugin_runtime import get_plugin_runtime

    runtime = get_plugin_runtime()
    handler = runtime.get_handler(payload.node_type_id)

    if handler is None:
        raise HTTPException(
            404,
            f"Node type '{payload.node_type_id}' not found. "
            f"Available: {[nt['node_type_id'] for nt in runtime.get_registered_node_types() if nt['plugin_name'] == plugin.name]}",
        )

    # Build a mock node dict for the handler
    mock_node = {
        "id": f"test_{uuid4().hex[:8]}",
        "data": {
            "nodeType": payload.node_type_id,
            "inputs": payload.inputs,
            "params": payload.inputs,
        },
    }

    # Build a minimal context
    from app.services.graph_executor import ExecutionContext
    context = ExecutionContext()

    try:
        handler_result = await handler.execute(mock_node, context, None)

        # Record execution stats
        await runtime.record_execution(
            db, plugin.name,
            success=handler_result.get("success", False),
            error=handler_result.get("error"),
            elapsed_ms=handler_result.get("elapsed_ms", 0.0),
        )
        await db.commit()

        return PluginExecuteResponse(
            success=handler_result.get("success", False),
            output=handler_result.get("output"),
            error=handler_result.get("error"),
            elapsed_ms=handler_result.get("elapsed_ms", 0),
            plugin=handler_result.get("plugin", plugin.name),
        )
    except Exception as e:
        await runtime.record_execution(db, plugin.name, success=False, error=str(e), elapsed_ms=0.0)
        await db.commit()
        return PluginExecuteResponse(
            success=False,
            error=str(e),
            plugin=plugin.name,
        )


@router.post("/{plugin_id}/upgrade", response_model=PluginResponse)
async def upgrade_plugin(
    plugin_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    """Upgrade a plugin to a newer version.

    Uninstalls the current version and installs the new one.
    """
    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    old_plugin = result.scalar_one_or_none()
    if not old_plugin:
        raise HTTPException(404, "Plugin not found")

    if not file.filename or not file.filename.endswith(".fmp"):
        raise HTTPException(400, "File must be a .fmp package")

    # Save uploaded file
    tmp_dir = Path(tempfile.mkdtemp(prefix="fm_upgrade_"))
    fmp_path = tmp_dir / file.filename
    try:
        content = await file.read()
        fmp_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(400, f"Failed to read uploaded file: {e}")

    try:
        from app.services.plugin_runtime import get_plugin_runtime

        runtime = get_plugin_runtime()

        # Uninstall old version
        await runtime.uninstall(db, plugin_id)
        await db.flush()

        # Install new version
        plugin_row = await runtime.install(
            db,
            fmp_path=fmp_path,
            workspace_id=workspace_id or str(user.id),
            source=old_plugin.source,
            listing_id=old_plugin.listing_id,
        )
        await db.commit()
        await db.refresh(plugin_row)

        logger.info(
            "Plugin upgraded: %s %s → %s",
            old_plugin.name, old_plugin.version, plugin_row.version,
        )
        return _to_plugin_response(plugin_row)

    except Exception as e:
        logger.error("Plugin upgrade failed: %s", e)
        raise HTTPException(400, f"Plugin upgrade failed: {e}")
    finally:
        try:
            fmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except Exception:
            pass


# ── Admin Endpoints (Phase 9.6) ──────────────────────────────────────────────


class PluginReviewRequest(BaseModel):
    reason: str | None = None


class ScanResultResponse(BaseModel):
    risk_score: int
    passed: bool
    findings_count: int
    findings: list[dict[str, Any]]
    declared_permissions: list[str]
    detected_permissions: list[str]
    undeclared_permissions: list[str]
    files_scanned: int


class PluginHealthReport(BaseModel):
    total_plugins: int
    healthy: int
    degraded: int
    unhealthy: int
    pending_review: int
    avg_error_rate: float
    top_crashing: list[dict[str, Any]]


@router.get("/admin/pending", response_model=PluginListResponse)
async def list_pending_plugins(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List plugins pending admin review. Admin-only."""
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")

    result = await db.execute(
        select(InstalledPlugin)
        .where(InstalledPlugin.review_status == "pending")
        .order_by(InstalledPlugin.created_at.desc())
    )
    plugins = result.scalars().all()
    return PluginListResponse(
        items=[_to_plugin_response(p) for p in plugins],
        total=len(plugins),
    )


@router.post("/{plugin_id}/approve", response_model=PluginResponse)
async def approve_plugin(
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Approve a plugin for marketplace visibility. Admin-only."""
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")

    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(404, "Plugin not found")

    plugin.review_status = "approved"
    plugin.reviewed_by = str(user.id)
    plugin.reviewed_at = datetime.now(UTC)
    plugin.rejection_reason = None
    await db.commit()
    await db.refresh(plugin)

    logger.info("Plugin approved: %s v%s by admin %s", plugin.name, plugin.version, user.id)
    return _to_plugin_response(plugin)


@router.post("/{plugin_id}/reject", response_model=PluginResponse)
async def reject_plugin(
    plugin_id: str,
    payload: PluginReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Reject a plugin with reason. Admin-only."""
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")

    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(404, "Plugin not found")

    # Disable the plugin on rejection
    from app.services.plugin_runtime import get_plugin_runtime
    runtime = get_plugin_runtime()
    await runtime.disable(db, plugin_id)

    plugin.review_status = "rejected"
    plugin.reviewed_by = str(user.id)
    plugin.reviewed_at = datetime.now(UTC)
    plugin.rejection_reason = payload.reason
    await db.commit()
    await db.refresh(plugin)

    logger.info(
        "Plugin rejected: %s v%s by admin %s (reason: %s)",
        plugin.name, plugin.version, user.id, payload.reason,
    )
    return _to_plugin_response(plugin)


@router.post("/{plugin_id}/kill-switch")
async def kill_switch_plugin(
    plugin_id: str,
    payload: PluginReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Emergency kill-switch: disable a plugin across ALL workspaces. Admin-only.

    This disables the plugin everywhere immediately without uninstalling.
    Use when a plugin is found to be malicious or critically buggy.
    """
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")

    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(404, "Plugin not found")

    # Disable ALL instances of this plugin name across all workspaces
    from app.services.plugin_runtime import get_plugin_runtime
    runtime = get_plugin_runtime()

    # Unload from memory once (subsequent calls are no-ops)
    runtime._unload(plugin.name)

    all_instances = await db.execute(
        select(InstalledPlugin).where(
            InstalledPlugin.name == plugin.name,
            InstalledPlugin.status.in_([PluginStatus.ENABLED, PluginStatus.LOADED]),
        )
    )
    disabled_count = 0
    for instance in all_instances.scalars().all():
        instance.status = PluginStatus.DISABLED
        instance.review_status = "rejected"
        instance.rejection_reason = f"Kill-switch: {payload.reason or 'Admin action'}"
        instance.reviewed_by = str(user.id)
        instance.reviewed_at = datetime.now(UTC)
        disabled_count += 1

    await db.commit()

    logger.warning(
        "KILL-SWITCH activated for plugin '%s': %d instances disabled by admin %s",
        plugin.name, disabled_count, user.id,
    )
    return {
        "status": "disabled",
        "plugin_name": plugin.name,
        "instances_disabled": disabled_count,
        "reason": payload.reason,
    }


@router.post("/{plugin_id}/scan", response_model=ScanResultResponse)
async def scan_plugin(
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run security scan on an installed plugin. Admin-only."""
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")

    result = await db.execute(
        select(InstalledPlugin).where(InstalledPlugin.id == plugin_id)
    )
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(404, "Plugin not found")
    if not plugin.install_path:
        raise HTTPException(400, "Plugin has no install path")

    import json as _json

    from app.services.plugin_scanner import get_plugin_scanner

    scanner = get_plugin_scanner()
    permissions = []
    if plugin.permissions_json:
        with contextlib.suppress(Exception):
            permissions = _json.loads(plugin.permissions_json)

    scan_result = scanner.scan(
        Path(plugin.install_path),
        declared_permissions=permissions,
    )

    # Persist scan results
    plugin.scan_risk_score = scan_result.risk_score
    plugin.scan_result_json = _json.dumps(scan_result.to_dict())
    await db.commit()

    logger.info(
        "Plugin scan completed: %s risk_score=%d passed=%s",
        plugin.name, scan_result.risk_score, scan_result.passed,
    )
    return ScanResultResponse(**scan_result.to_dict())


@router.get("/admin/health-report", response_model=PluginHealthReport)
async def get_plugin_health_report(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get aggregated health report for all plugins. Admin-only."""
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")

    result = await db.execute(select(InstalledPlugin))
    plugins = result.scalars().all()

    total = len(plugins)
    healthy = 0
    degraded = 0
    unhealthy = 0
    pending_review = 0
    total_error_rate = 0.0
    crashing: list[dict[str, Any]] = []

    for p in plugins:
        if p.review_status == "pending":
            pending_review += 1
        exec_count = p.execution_count or 0
        err_count = p.error_count or 0
        error_rate = (err_count / exec_count * 100) if exec_count > 0 else 0.0
        total_error_rate += error_rate

        if p.status == PluginStatus.ERROR:
            unhealthy += 1
        elif error_rate > 10:
            degraded += 1
        else:
            healthy += 1

        if (p.crash_count or 0) > 0:
            crashing.append({
                "name": p.name,
                "version": p.version,
                "crash_count": p.crash_count,
                "error_rate": round(error_rate, 2),
                "workspace_id": p.workspace_id,
            })

    crashing.sort(key=lambda x: x["crash_count"], reverse=True)

    return PluginHealthReport(
        total_plugins=total,
        healthy=healthy,
        degraded=degraded,
        unhealthy=unhealthy,
        pending_review=pending_review,
        avg_error_rate=round(total_error_rate / total, 2) if total > 0 else 0.0,
        top_crashing=crashing[:10],
    )
