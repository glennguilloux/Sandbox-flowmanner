"""
Tool Versioning System - Semantic versioning and lifecycle management for tools

Provides version tracking, deprecation workflows, migration helpers,
and rollback capabilities for all registered tools in the MetaLoop system.
"""

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class VersionStatus(Enum):
    """Lifecycle status of a tool version"""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    RETIRED = "retired"
    BETA = "beta"
    ALPHA = "alpha"


@dataclass
class SemanticVersion:
    """Semantic version representation (major.minor.patch)"""

    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    @classmethod
    def parse(cls, version_str: str) -> "SemanticVersion":
        """Parse version string like '1.2.3' or '1.2.3-beta+build'"""
        pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.-]+))?(?:\+([a-zA-Z0-9.-]+))?$"
        match = re.match(pattern, version_str.strip())
        if not match:
            raise ValueError(f"Invalid semantic version: {version_str}")

        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4),
            build=match.group(5),
        )

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version

    def __lt__(self, other: "SemanticVersion") -> bool:
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch
        # Prerelease versions have lower precedence
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        return (self.prerelease or "") < (other.prerelease or "")

    def __le__(self, other: "SemanticVersion") -> bool:
        return self == other or self < other

    def __gt__(self, other: "SemanticVersion") -> bool:
        return not self <= other

    def __ge__(self, other: "SemanticVersion") -> bool:
        return not self < other

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return False
        return (self.major, self.minor, self.patch, self.prerelease) == (
            other.major,
            other.minor,
            other.patch,
            other.prerelease,
        )

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    def bump_major(self) -> "SemanticVersion":
        """Bump major version (breaking changes)"""
        return SemanticVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> "SemanticVersion":
        """Bump minor version (new features)"""
        return SemanticVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> "SemanticVersion":
        """Bump patch version (bug fixes)"""
        return SemanticVersion(self.major, self.minor, self.patch + 1)


@dataclass
class ToolVersion:
    """Represents a specific version of a tool"""

    tool_id: str
    version: SemanticVersion
    status: VersionStatus = VersionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    deprecated_at: datetime | None = None
    sunset_date: datetime | None = None
    retired_at: datetime | None = None
    handler: Callable[[dict[str, Any]], Awaitable[Any]] | None = None
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    changelog: str = ""
    migration_guide: str = ""
    breaking_changes: list[str] = field(default_factory=list)
    checksum: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """Compute checksum for version integrity"""
        data = f"{self.tool_id}:{self.version}:{json.dumps(self.input_schema, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def is_usable(self) -> bool:
        """Check if this version can still be used"""
        if self.status == VersionStatus.RETIRED:
            return False
        return not (self.status == VersionStatus.SUNSET and self.sunset_date and datetime.now(UTC) > self.sunset_date)

    def is_deprecated(self) -> bool:
        """Check if version is deprecated"""
        return self.status in (VersionStatus.DEPRECATED, VersionStatus.SUNSET)


@dataclass
class Migration:
    """Migration path between tool versions"""

    tool_id: str
    from_version: SemanticVersion
    to_version: SemanticVersion
    migration_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    auto_migrate: bool = False
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def migrate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Apply migration to parameters"""
        if self.migration_handler:
            return self.migration_handler(params)
        return params


@dataclass
class DeprecationNotice:
    """Deprecation notice for a tool version"""

    tool_id: str
    version: SemanticVersion
    reason: str
    sunset_date: datetime
    migration_path: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged_by: list[str] = field(default_factory=list)

    def days_until_sunset(self) -> int:
        """Calculate days until sunset"""
        delta = self.sunset_date - datetime.now(UTC)
        return max(0, delta.days)

    def is_expired(self) -> bool:
        """Check if deprecation period has expired"""
        return datetime.now(UTC) > self.sunset_date


class ToolVersioningService:
    """
    Central service for managing tool versions.

    Features:
    - Semantic versioning support
    - Version lifecycle management
    - Deprecation workflow with sunset dates
    - Migration helpers between versions
    - Rollback capability
    """

    def __init__(self):
        self._versions: dict[str, dict[str, ToolVersion]] = {}  # tool_id -> version_str -> ToolVersion
        self._migrations: dict[str, list[Migration]] = {}  # tool_id -> list of migrations
        self._deprecations: dict[str, DeprecationNotice] = {}  # key: "tool_id:version"
        self._active_versions: dict[str, SemanticVersion] = {}  # tool_id -> current active version
        self._version_history: dict[str, list[SemanticVersion]] = {}  # tool_id -> ordered versions
        self._rollback_stack: dict[str, list[tuple[SemanticVersion, datetime]]] = {}
        self._lock = asyncio.Lock()

    async def register_version(
        self,
        tool_id: str,
        version: str,
        handler: Callable[[dict[str, Any]], Awaitable[Any]],
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        changelog: str = "",
        status: VersionStatus = VersionStatus.ACTIVE,
    ) -> ToolVersion:
        """
        Register a new version of a tool.

        Args:
            tool_id: Unique tool identifier
            version: Semantic version string (e.g., "1.0.0")
            handler: Async function to execute the tool
            input_schema: JSON schema for input validation
            output_schema: JSON schema for output validation
            changelog: Description of changes
            status: Initial version status

        Returns:
            The created ToolVersion
        """
        async with self._lock:
            sem_ver = SemanticVersion.parse(version)

            tool_version = ToolVersion(
                tool_id=tool_id,
                version=sem_ver,
                handler=handler,
                input_schema=input_schema or {},
                output_schema=output_schema or {},
                changelog=changelog,
                status=status,
            )

            if tool_id not in self._versions:
                self._versions[tool_id] = {}
                self._version_history[tool_id] = []

            version_str = str(sem_ver)
            self._versions[tool_id][version_str] = tool_version

            # Update version history
            if sem_ver not in self._version_history[tool_id]:
                self._version_history[tool_id].append(sem_ver)
                self._version_history[tool_id].sort(reverse=True)

            # Set as active if first version or explicitly active
            if tool_id not in self._active_versions or status == VersionStatus.ACTIVE:
                self._active_versions[tool_id] = sem_ver

            logger.info(
                "Registered tool version: %s@%s with status %s",
                tool_id,
                version,
                status.value,
            )
            return tool_version

    async def get_version(self, tool_id: str, version: str | None = None) -> ToolVersion | None:
        """
        Get a specific version of a tool.

        Args:
            tool_id: Tool identifier
            version: Version string, or None for active version

        Returns:
            ToolVersion if found, None otherwise
        """
        if tool_id not in self._versions:
            return None

        if version is None:
            # Return active version
            active_ver = self._active_versions.get(tool_id)
            if active_ver:
                return self._versions[tool_id].get(str(active_ver))
            return None

        return self._versions[tool_id].get(version)

    async def list_versions(self, tool_id: str) -> list[ToolVersion]:
        """List all versions of a tool, ordered newest first"""
        if tool_id not in self._versions:
            return []

        versions = list(self._versions[tool_id].values())
        versions.sort(key=lambda v: v.version, reverse=True)
        return versions

    async def deprecate_version(
        self,
        tool_id: str,
        version: str,
        reason: str,
        sunset_days: int = 90,
        migration_path: str | None = None,
    ) -> DeprecationNotice | None:
        """
        Mark a version as deprecated with a sunset date.

        Args:
            tool_id: Tool identifier
            version: Version to deprecate
            reason: Reason for deprecation
            sunset_days: Days until version is retired
            migration_path: Suggested migration path

        Returns:
            DeprecationNotice if successful, None if version not found
        """
        async with self._lock:
            tool_version = await self.get_version(tool_id, version)
            if not tool_version:
                logger.warning("Cannot deprecate: %s@%s not found", tool_id, version)
                return None

            sunset_date = datetime.now(UTC) + timedelta(days=sunset_days)

            tool_version.status = VersionStatus.DEPRECATED
            tool_version.deprecated_at = datetime.now(UTC)
            tool_version.sunset_date = sunset_date

            notice = DeprecationNotice(
                tool_id=tool_id,
                version=tool_version.version,
                reason=reason,
                sunset_date=sunset_date,
                migration_path=migration_path,
            )

            key = f"{tool_id}:{version}"
            self._deprecations[key] = notice

            logger.warning(
                "Deprecated %s@%s: %s. Sunset in %s days (%s)",
                tool_id,
                version,
                reason,
                sunset_days,
                sunset_date.isoformat(),
            )
            return notice

    async def register_migration(
        self,
        tool_id: str,
        from_version: str,
        to_version: str,
        migration_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        auto_migrate: bool = False,
        description: str = "",
    ) -> Migration:
        """
        Register a migration path between versions.

        Args:
            tool_id: Tool identifier
            from_version: Source version
            to_version: Target version
            migration_handler: Function to transform params
            auto_migrate: Whether to auto-apply migration
            description: Migration description

        Returns:
            The created Migration
        """
        migration = Migration(
            tool_id=tool_id,
            from_version=SemanticVersion.parse(from_version),
            to_version=SemanticVersion.parse(to_version),
            migration_handler=migration_handler,
            auto_migrate=auto_migrate,
            description=description,
        )

        if tool_id not in self._migrations:
            self._migrations[tool_id] = []

        self._migrations[tool_id].append(migration)
        logger.info("Registered migration: %s %s -> %s", tool_id, from_version, to_version)

        return migration

    async def get_migration(self, tool_id: str, from_version: str, to_version: str) -> Migration | None:
        """Find a migration path between versions"""
        if tool_id not in self._migrations:
            return None

        from_ver = SemanticVersion.parse(from_version)
        to_ver = SemanticVersion.parse(to_version)

        for migration in self._migrations[tool_id]:
            if migration.from_version == from_ver and migration.to_version == to_ver:
                return migration

        return None

    async def migrate_params(
        self, tool_id: str, from_version: str, to_version: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Migrate parameters from one version to another.

        Args:
            tool_id: Tool identifier
            from_version: Source version
            to_version: Target version
            params: Parameters to migrate

        Returns:
            Migrated parameters
        """
        migration = await self.get_migration(tool_id, from_version, to_version)

        if not migration:
            logger.warning("No migration found: %s %s -> %s", tool_id, from_version, to_version)
            return params

        migrated = migration.migrate(params)
        logger.debug("Migrated params for %s: %s -> %s", tool_id, from_version, to_version)
        return migrated

    async def rollback(self, tool_id: str, target_version: str | None = None) -> bool:
        """
        Rollback to a previous version.

        Args:
            tool_id: Tool identifier
            target_version: Version to rollback to, or None for previous

        Returns:
            True if rollback successful
        """
        async with self._lock:
            if tool_id not in self._version_history:
                logger.error("Cannot rollback: %s has no version history", tool_id)
                return False

            history = self._version_history[tool_id]
            current = self._active_versions.get(tool_id)

            if target_version:
                target = SemanticVersion.parse(target_version)
            else:
                # Find previous version
                if not current or len(history) < 2:
                    logger.error("Cannot rollback: no previous version for %s", tool_id)
                    return False
                idx = history.index(current)
                if idx >= len(history) - 1:
                    logger.error("Cannot rollback: already at oldest version")
                    return False
                target = history[idx + 1]

            # Save current to rollback stack
            if current:
                if tool_id not in self._rollback_stack:
                    self._rollback_stack[tool_id] = []
                self._rollback_stack[tool_id].append((current, datetime.now(UTC)))

            # Set target as active
            self._active_versions[tool_id] = target

            logger.warning("Rolled back %s to version %s", tool_id, target)
            return True

    async def get_deprecation_notices(self, tool_id: str | None = None) -> list[DeprecationNotice]:
        """Get all active deprecation notices"""
        notices = []
        for notice in self._deprecations.values():
            if (tool_id is None or notice.tool_id == tool_id) and not notice.is_expired():
                notices.append(notice)
        return notices

    async def check_version_health(self, tool_id: str) -> dict[str, Any]:
        """Check health status of tool versions"""
        versions = await self.list_versions(tool_id)

        active_count = sum(1 for v in versions if v.status == VersionStatus.ACTIVE)
        deprecated_count = sum(1 for v in versions if v.is_deprecated())
        retired_count = sum(1 for v in versions if v.status == VersionStatus.RETIRED)

        notices = await self.get_deprecation_notices(tool_id)

        return {
            "tool_id": tool_id,
            "total_versions": len(versions),
            "active": active_count,
            "deprecated": deprecated_count,
            "retired": retired_count,
            "active_deprecations": len(notices),
            "latest_version": str(versions[0].version) if versions else None,
            "current_active": str(self._active_versions.get(tool_id, "none")),
        }

    async def cleanup_retired(self, days_old: int = 30) -> int:
        """Remove retired versions older than specified days"""
        async with self._lock:
            cutoff = datetime.now(UTC) - timedelta(days=days_old)
            removed = 0

            for tool_id in list(self._versions.keys()):
                for ver_str in list(self._versions[tool_id].keys()):
                    version = self._versions[tool_id][ver_str]
                    if version.status == VersionStatus.RETIRED and version.retired_at and version.retired_at < cutoff:
                        del self._versions[tool_id][ver_str]
                        removed += 1
                        logger.info("Cleaned up retired version: %s@%s", tool_id, ver_str)

            return removed


# Singleton instance
_versioning_service: ToolVersioningService | None = None


def get_versioning_service() -> ToolVersioningService:
    """Get the singleton ToolVersioningService instance"""
    global _versioning_service
    if _versioning_service is None:
        _versioning_service = ToolVersioningService()
        logger.info("Initialized ToolVersioningService singleton")
    return _versioning_service
