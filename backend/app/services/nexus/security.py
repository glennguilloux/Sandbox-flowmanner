"""
Security Hardening - Input validation, rate limiting, and audit logging

Provides comprehensive security for the MetaLoop agent system including
input sanitization, rate limiting, audit logging, secret management,
and permission-based access control.
"""

import asyncio
import hashlib
import html
import logging
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Permission(Enum):
    """System permissions"""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"
    DELETE = "delete"
    MANAGE_AGENTS = "manage_agents"
    ACCESS_SECRETS = "access_secrets"
    VIEW_AUDIT_LOGS = "view_audit_logs"


class AuditEventType(Enum):
    """Types of audit events"""

    LOGIN = "login"
    LOGOUT = "logout"
    TOOL_EXECUTION = "tool_execution"
    AGENT_SPAWN = "agent_spawn"
    SECRET_ACCESS = "secret_access"
    PERMISSION_CHANGE = "permission_change"
    RATE_LIMIT_HIT = "rate_limit_hit"
    INPUT_BLOCKED = "input_blocked"
    CONFIG_CHANGE = "config_change"
    DATA_ACCESS = "data_access"
    ERROR = "error"


class Severity(Enum):
    """Audit event severity levels"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit log event record"""

    event_id: str
    event_type: AuditEventType
    severity: Severity
    timestamp: datetime = field(default_factory=datetime.utcnow)
    user_id: str | None = None
    agent_id: str | None = None
    tool_name: str | None = None
    action: str = ""
    resource: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    session_id: str | None = None
    success: bool = True
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "ip_address": self.ip_address,
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass
class RateLimitRule:
    """Rate limiting configuration"""

    entity_id: str
    entity_type: str
    max_requests: int
    window_seconds: int
    burst_allowance: int = 0
    block_duration_seconds: int = 300
    created_at: datetime = field(default_factory=datetime.utcnow)

    def get_key(self, identifier: str) -> str:
        return f"{self.entity_type}:{identifier}:{self.window_seconds}"


@dataclass
class RateLimitState:
    """Current rate limit state for an entity"""

    requests: list[float] = field(default_factory=list)
    blocked_until: float | None = None
    total_blocked: int = 0
    last_request: float | None = None


@dataclass
class Secret:
    """Stored secret with metadata"""

    secret_id: str
    name: str
    value: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    created_by: str | None = None
    access_count: int = 0
    last_accessed: datetime | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at


@dataclass
class PermissionSet:
    """Permission configuration for an entity"""

    entity_id: str
    entity_type: str
    permissions: set[Permission] = field(default_factory=set)
    resource_permissions: dict[str, set[Permission]] = field(default_factory=dict)
    inherited_from: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def has_permission(self, permission: Permission, resource: str | None = None) -> bool:
        if permission in self.permissions:
            return True
        if resource and resource in self.resource_permissions:
            if permission in self.resource_permissions[resource]:
                return True
        return False


@dataclass
class ValidationResult:
    """Result of input validation"""

    is_valid: bool
    sanitized_value: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocked_patterns: list[str] = field(default_factory=list)


class SecurityService:
    """
    Central security service for the MetaLoop agent system.

    Features:
    - Input validation and sanitization
    - Rate limiting per agent/user
    - Audit logging for sensitive operations
    - Secret management integration
    - Permission checks for tool execution
    """

    INJECTION_PATTERNS = [
        r"(?i)(\\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE)\\b.*\\b(FROM|INTO|TABLE|DATABASE)\\b)",
        r"(?i)(\\b(UNION\\s+SELECT)\\b)",
        r"(?i)(\\b(OR|AND)\\s+['\"]?\\d+['\"]?\\s*=\\s*['\"]?\\d+['\"]?)",
        r"(?i)<\\s*script[^>]*>.*?<\\s*/\\s*script\\s*>",
        r"(?i)(javascript\\s*:)",
        r"(?i)(on\\w+\\s*=)",
        r"(?i)(\\||;|\\$\\(|`|\\$\\{)",
        r"(?i)(\\b(eval|exec|system|shell|passthru)\\s*\\()",
        r"\\.\\./",
        r"\\.\\\\\\\\",
    ]

    SENSITIVE_PATTERNS = [
        r"(?i)password",
        r"(?i)secret",
        r"(?i)api[_-]?key",
        r"(?i)token",
        r"(?i)credential",
        r"(?i)private[_-]?key",
    ]

    def __init__(self):
        self._rate_limit_rules: dict[str, RateLimitRule] = {}
        self._rate_limit_states: dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._audit_log: list[AuditEvent] = []
        self._secrets: dict[str, Secret] = {}
        self._permission_sets: dict[str, PermissionSet] = {}
        self._blocked_entities: set[str] = set()
        self._lock = asyncio.Lock()

        self._default_user_limit = RateLimitRule(
            entity_id="default_user", entity_type="user", max_requests=100, window_seconds=60, burst_allowance=20
        )
        self._default_agent_limit = RateLimitRule(
            entity_id="default_agent", entity_type="agent", max_requests=1000, window_seconds=60, burst_allowance=100
        )

        self._compiled_injection_patterns = [re.compile(p) for p in self.INJECTION_PATTERNS]
        self._compiled_sensitive_patterns = [re.compile(p) for p in self.SENSITIVE_PATTERNS]

        self._audit_handlers: list[Callable[[AuditEvent], Awaitable[None]]] = []

    def register_audit_handler(self, handler: Callable[[AuditEvent], Awaitable[None]]):
        self._audit_handlers.append(handler)

    async def _send_audit_event(self, event: AuditEvent):
        for handler in self._audit_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Audit handler failed: {e}")

    def _generate_id(self) -> str:
        return uuid.uuid4().hex[:16]

    def validate_input(
        self,
        value: str,
        field_name: str = "input",
        max_length: int = 10000,
        allow_html: bool = False,
        strict: bool = True,
    ) -> ValidationResult:
        errors = []
        warnings = []
        blocked_patterns = []

        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False, errors=[f"{field_name}: Expected string, got {type(value).__name__}"]
            )

        if len(value) > max_length:
            errors.append(f"{field_name}: Exceeds maximum length of {max_length}")
            return ValidationResult(is_valid=False, errors=errors)

        sanitized = value
        for i, pattern in enumerate(self._compiled_injection_patterns):
            if pattern.search(value):
                pattern_name = self.INJECTION_PATTERNS[i][:50]
                blocked_patterns.append(pattern_name)

                if strict:
                    errors.append(f"{field_name}: Blocked suspicious pattern")
                    logger.warning(f"Input blocked for field {field_name}: matched pattern")
                else:
                    warnings.append(f"{field_name}: Contains suspicious pattern")
                    sanitized = pattern.sub("[BLOCKED]", sanitized)

        if not allow_html:
            sanitized = html.escape(sanitized)

        for pattern in self._compiled_sensitive_patterns:
            if pattern.search(value):
                warnings.append(f"{field_name}: May contain sensitive data")

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            sanitized_value=sanitized if is_valid else None,
            errors=errors,
            warnings=warnings,
            blocked_patterns=blocked_patterns,
        )

    def validate_dict(
        self, data: dict[str, Any], schema: dict[str, dict[str, Any]], strict: bool = True
    ) -> tuple[dict[str, Any], list[str]]:
        sanitized = {}
        all_errors = []

        for field_name, field_schema in schema.items():
            field_type = field_schema.get("type", "string")
            required = field_schema.get("required", False)
            max_length = field_schema.get("max_length", 10000)
            allow_html = field_schema.get("allow_html", False)

            if field_name not in data:
                if required:
                    all_errors.append(f"Missing required field: {field_name}")
                continue

            value = data[field_name]

            if field_type == "string":
                result = self.validate_input(
                    str(value), field_name=field_name, max_length=max_length, allow_html=allow_html, strict=strict
                )
                if result.is_valid:
                    sanitized[field_name] = result.sanitized_value
                else:
                    all_errors.extend(result.errors)
            elif field_type == "integer":
                try:
                    sanitized[field_name] = int(value)
                except (ValueError, TypeError):
                    all_errors.append(f"{field_name}: Invalid integer value")
            elif field_type == "float":
                try:
                    sanitized[field_name] = float(value)
                except (ValueError, TypeError):
                    all_errors.append(f"{field_name}: Invalid float value")
            elif field_type == "boolean":
                if isinstance(value, bool):
                    sanitized[field_name] = value
                elif str(value).lower() in ("true", "1", "yes"):
                    sanitized[field_name] = True
                elif str(value).lower() in ("false", "0", "no"):
                    sanitized[field_name] = False
                else:
                    all_errors.append(f"{field_name}: Invalid boolean value")
            elif field_type == "list":
                if isinstance(value, list):
                    sanitized[field_name] = value
                else:
                    all_errors.append(f"{field_name}: Expected list")
            elif field_type == "dict":
                if isinstance(value, dict):
                    sanitized[field_name] = value
                else:
                    all_errors.append(f"{field_name}: Expected dict")
            else:
                sanitized[field_name] = value

        return sanitized, all_errors

    async def set_rate_limit(self, rule: RateLimitRule):
        async with self._lock:
            self._rate_limit_rules[rule.entity_id] = rule
            logger.info(f"Set rate limit for {rule.entity_type} {rule.entity_id}")

    async def check_rate_limit(self, entity_id: str, entity_type: str = "user") -> tuple[bool, int | None]:
        now = time.time()

        if entity_id in self._blocked_entities:
            return False, 300

        rule = self._rate_limit_rules.get(entity_id)
        if rule is None:
            rule = self._default_user_limit if entity_type == "user" else self._default_agent_limit

        state = self._rate_limit_states[entity_id]

        if state.blocked_until and now < state.blocked_until:
            retry_after = int(state.blocked_until - now)
            return False, retry_after

        cutoff = now - rule.window_seconds
        state.requests = [t for t in state.requests if t > cutoff]

        if len(state.requests) >= rule.max_requests + rule.burst_allowance:
            state.blocked_until = now + rule.block_duration_seconds
            state.total_blocked += 1

            await self.log_audit_event(
                event_type=AuditEventType.RATE_LIMIT_HIT,
                severity=Severity.WARNING,
                action="rate_limit_exceeded",
                details={
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "requests": len(state.requests),
                    "limit": rule.max_requests,
                },
            )

            logger.warning(f"Rate limit exceeded for {entity_type} {entity_id}")
            return False, rule.block_duration_seconds

        state.requests.append(now)
        state.last_request = now

        return True, None

    async def get_rate_limit_status(self, entity_id: str) -> dict[str, Any]:
        state = self._rate_limit_states.get(entity_id, RateLimitState())
        rule = self._rate_limit_rules.get(entity_id, self._default_user_limit)

        now = time.time()
        cutoff = now - rule.window_seconds
        recent_requests = [t for t in state.requests if t > cutoff]

        return {
            "entity_id": entity_id,
            "requests_in_window": len(recent_requests),
            "limit": rule.max_requests,
            "burst_allowance": rule.burst_allowance,
            "remaining": max(0, rule.max_requests + rule.burst_allowance - len(recent_requests)),
            "is_blocked": state.blocked_until is not None and state.blocked_until > now,
            "blocked_until": state.blocked_until,
            "total_blocked": state.total_blocked,
        }

    async def log_audit_event(
        self,
        event_type: AuditEventType,
        severity: Severity = Severity.INFO,
        user_id: str | None = None,
        agent_id: str | None = None,
        tool_name: str | None = None,
        action: str = "",
        resource: str = "",
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        session_id: str | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=self._generate_id(),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            agent_id=agent_id,
            tool_name=tool_name,
            action=action,
            resource=resource,
            details=details or {},
            ip_address=ip_address,
            session_id=session_id,
            success=success,
            error_message=error_message,
        )

        async with self._lock:
            self._audit_log.append(event)
            if len(self._audit_log) > 10000:
                self._audit_log = self._audit_log[-10000:]

        log_msg = f"Audit: {event_type.value} by {user_id or agent_id or 'system'} - {action}"
        if severity == Severity.CRITICAL:
            logger.critical(log_msg)
        elif severity == Severity.ERROR:
            logger.error(log_msg)
        elif severity == Severity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        await self._send_audit_event(event)

        return event

    async def get_audit_log(
        self,
        event_type: AuditEventType | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        severity: Severity | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        events = self._audit_log

        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if user_id:
            events = [e for e in events if e.user_id == user_id]
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
        if severity:
            events = [e for e in events if e.severity == severity]
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]

        return events[-limit:]

    async def store_secret(
        self,
        name: str,
        value: str,
        created_by: str | None = None,
        expires_at: datetime | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Secret:
        secret_id = self._generate_id()
        hashed_value = hashlib.sha256(value.encode()).hexdigest()

        secret = Secret(
            secret_id=secret_id,
            name=name,
            value=hashed_value,
            created_by=created_by,
            expires_at=expires_at,
            tags=tags or [],
            metadata=metadata or {},
        )

        async with self._lock:
            self._secrets[name] = secret

        await self.log_audit_event(
            event_type=AuditEventType.SECRET_ACCESS,
            severity=Severity.INFO,
            user_id=created_by,
            action="secret_created",
            resource=name,
            success=True,
        )

        logger.info(f"Stored secret: {name}")
        return secret

    async def get_secret(self, name: str, requester_id: str | None = None) -> str | None:
        secret = self._secrets.get(name)

        if secret is None:
            logger.warning(f"Secret not found: {name}")
            return None

        if secret.is_expired():
            logger.warning(f"Secret expired: {name}")
            return None

        async with self._lock:
            secret.access_count += 1
            secret.last_accessed = datetime.now(UTC)

        await self.log_audit_event(
            event_type=AuditEventType.SECRET_ACCESS,
            severity=Severity.INFO,
            user_id=requester_id,
            action="secret_accessed",
            resource=name,
            success=True,
        )

        return secret.value

    async def delete_secret(self, name: str, requester_id: str | None = None) -> bool:
        async with self._lock:
            if name not in self._secrets:
                return False
            del self._secrets[name]

        await self.log_audit_event(
            event_type=AuditEventType.SECRET_ACCESS,
            severity=Severity.WARNING,
            user_id=requester_id,
            action="secret_deleted",
            resource=name,
            success=True,
        )

        logger.info(f"Deleted secret: {name}")
        return True

    async def list_secrets(self, tags: list[str] | None = None) -> list[dict[str, Any]]:
        secrets = []
        for secret in self._secrets.values():
            if tags and not any(t in secret.tags for t in tags):
                continue

            secrets.append(
                {
                    "name": secret.name,
                    "created_at": secret.created_at.isoformat(),
                    "expires_at": secret.expires_at.isoformat() if secret.expires_at else None,
                    "access_count": secret.access_count,
                    "tags": secret.tags,
                    "is_expired": secret.is_expired(),
                }
            )

        return secrets

    async def set_permissions(self, permission_set: PermissionSet):
        async with self._lock:
            self._permission_sets[permission_set.entity_id] = permission_set

        await self.log_audit_event(
            event_type=AuditEventType.PERMISSION_CHANGE,
            severity=Severity.INFO,
            user_id=permission_set.entity_id,
            action="permissions_set",
            details={
                "permissions": [p.value for p in permission_set.permissions],
                "entity_type": permission_set.entity_type,
            },
        )

        logger.info(f"Set permissions for {permission_set.entity_type} {permission_set.entity_id}")

    async def check_permission(self, entity_id: str, permission: Permission, resource: str | None = None) -> bool:
        perm_set = self._permission_sets.get(entity_id)

        if perm_set is None:
            return permission == Permission.READ

        return perm_set.has_permission(permission, resource)

    async def check_tool_permission(self, agent_id: str, tool_name: str) -> tuple[bool, str | None]:
        if agent_id in self._blocked_entities:
            return False, "Agent is blocked"

        has_perm = await self.check_permission(agent_id, Permission.EXECUTE, resource=f"tool:{tool_name}")

        if not has_perm:
            return False, f"No execute permission for tool: {tool_name}"

        return True, None

    async def grant_permission(
        self, entity_id: str, permission: Permission, resource: str | None = None, granted_by: str | None = None
    ) -> bool:
        perm_set = self._permission_sets.get(entity_id)

        if perm_set is None:
            perm_set = PermissionSet(entity_id=entity_id, entity_type="agent")
            self._permission_sets[entity_id] = perm_set

        if resource:
            if resource not in perm_set.resource_permissions:
                perm_set.resource_permissions[resource] = set()
            perm_set.resource_permissions[resource].add(permission)
        else:
            perm_set.permissions.add(permission)

        await self.log_audit_event(
            event_type=AuditEventType.PERMISSION_CHANGE,
            severity=Severity.INFO,
            user_id=granted_by,
            agent_id=entity_id,
            action="permission_granted",
            resource=resource or "global",
            details={"permission": permission.value},
        )

        return True

    async def revoke_permission(
        self, entity_id: str, permission: Permission, resource: str | None = None, revoked_by: str | None = None
    ) -> bool:
        perm_set = self._permission_sets.get(entity_id)

        if perm_set is None:
            return False

        if resource:
            if resource in perm_set.resource_permissions:
                perm_set.resource_permissions[resource].discard(permission)
        else:
            perm_set.permissions.discard(permission)

        await self.log_audit_event(
            event_type=AuditEventType.PERMISSION_CHANGE,
            severity=Severity.WARNING,
            user_id=revoked_by,
            agent_id=entity_id,
            action="permission_revoked",
            resource=resource or "global",
            details={"permission": permission.value},
        )

        return True

    async def get_security_summary(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        hour_ago = now - timedelta(hours=1)

        recent_events = [e for e in self._audit_log if e.timestamp >= hour_ago]
        failed_events = [e for e in recent_events if not e.success]
        rate_limit_hits = [e for e in recent_events if e.event_type == AuditEventType.RATE_LIMIT_HIT]
        blocked_inputs = [e for e in recent_events if e.event_type == AuditEventType.INPUT_BLOCKED]

        return {
            "status": "secure" if len(failed_events) < 10 else "degraded",
            "total_audit_events": len(self._audit_log),
            "recent_events_1h": len(recent_events),
            "failed_events_1h": len(failed_events),
            "rate_limit_hits_1h": len(rate_limit_hits),
            "blocked_inputs_1h": len(blocked_inputs),
            "blocked_entities": len(self._blocked_entities),
            "active_secrets": len(self._secrets),
            "entities_with_permissions": len(self._permission_sets),
            "rate_limit_rules": len(self._rate_limit_rules),
        }


_security_service: SecurityService | None = None


def get_security_service() -> SecurityService:
    """Get the singleton SecurityService instance"""
    global _security_service
    if _security_service is None:
        _security_service = SecurityService()
        logger.info("Initialized SecurityService singleton")
    return _security_service
