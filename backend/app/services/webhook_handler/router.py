#!/usr/bin/env python3
"""
Webhook Router

Routes webhooks to appropriate handlers based on source and event type.
Supports dynamic handler registration and custom handler modules.
"""

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HandlerPriority(int, Enum):
    """Handler priority levels"""

    HIGHEST = 1
    HIGH = 25
    NORMAL = 50
    LOW = 75
    LOWEST = 100


@dataclass
class HandlerInfo:
    """Information about a registered handler"""

    name: str
    handler: Callable
    source: str
    event_types: list[str] = field(default_factory=list)
    priority: int = HandlerPriority.NORMAL
    enabled: bool = True
    description: str = ""


class WebhookRouter:
    """Routes webhooks to appropriate handlers"""

    def __init__(self):
        self._handlers: dict[str, list[HandlerInfo]] = {}
        self._default_handlers: dict[str, HandlerInfo] = {}
        self._global_handlers: list[HandlerInfo] = []

    def register(
        self,
        name: str,
        handler: Callable,
        source: str,
        event_types: list[str] | None = None,
        priority: int = HandlerPriority.NORMAL,
        description: str = "",
    ) -> None:
        """Register a webhook handler"""
        handler_info = HandlerInfo(
            name=name,
            handler=handler,
            source=source,
            event_types=event_types or [],
            priority=priority,
            description=description,
        )

        if source not in self._handlers:
            self._handlers[source] = []

        self._handlers[source].append(handler_info)
        self._handlers[source].sort(key=lambda h: h.priority)

        logger.info("Registered webhook handler '%s' for source '%s'", name, source)

    def register_default(self, name: str, handler: Callable, source: str) -> None:
        """Register a default handler for a source"""
        handler_info = HandlerInfo(
            name=name, handler=handler, source=source, priority=HandlerPriority.LOWEST
        )
        self._default_handlers[source] = handler_info
        logger.info("Registered default webhook handler '%s' for source '%s'", name, source)

    def register_global(
        self, name: str, handler: Callable, priority: int = HandlerPriority.LOWEST
    ) -> None:
        """Register a global handler that receives all webhooks"""
        handler_info = HandlerInfo(
            name=name, handler=handler, source="*", priority=priority
        )
        self._global_handlers.append(handler_info)
        self._global_handlers.sort(key=lambda h: h.priority)
        logger.info("Registered global webhook handler '%s'", name)

    def unregister(self, name: str) -> bool:
        """Unregister a handler by name"""
        for handlers in self._handlers.values():
            for i, handler in enumerate(handlers):
                if handler.name == name:
                    handlers.pop(i)
                    logger.info("Unregistered webhook handler '%s'", name)
                    return True

        if name in self._default_handlers:
            del self._default_handlers[name]
            logger.info("Unregistered default webhook handler '%s'", name)
            return True

        for i, handler in enumerate(self._global_handlers):
            if handler.name == name:
                self._global_handlers.pop(i)
                logger.info("Unregistered global webhook handler '%s'", name)
                return True

        return False

    def get_handlers(
        self, source: str, event_type: str | None = None
    ) -> list[HandlerInfo]:
        """Get applicable handlers for a webhook"""
        handlers = []

        # Add global handlers
        handlers.extend(self._global_handlers)

        # Add source-specific handlers
        source_handlers = self._handlers.get(source, [])
        for handler in source_handlers:
            if not handler.enabled:
                continue
            if event_type and handler.event_types:
                if event_type in handler.event_types or "*" in handler.event_types:
                    handlers.append(handler)
            else:
                handlers.append(handler)

        # Add default handler if no specific handlers matched
        if source in self._default_handlers:
            default = self._default_handlers[source]
            if default.enabled:
                handlers.append(default)

        # Sort by priority
        handlers.sort(key=lambda h: h.priority)

        return handlers

    async def route(
        self,
        source: str,
        event_type: str | None,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Route a webhook to appropriate handlers"""
        handlers = self.get_handlers(source, event_type)

        if not handlers:
            logger.warning("No handlers found for source '%s', event '%s'", source, event_type)
            return {
                "success": False,
                "error": "No handlers registered",
                "source": source,
                "event_type": event_type,
            }

        results = []
        errors = []

        for handler_info in handlers:
            try:
                logger.debug("Executing handler '%s' for %s/%s", handler_info.name, source, event_type)

                result = await self._execute_handler(
                    handler_info.handler, source, event_type, payload, headers
                )

                results.append(
                    {"handler": handler_info.name, "success": True, "result": result}
                )
            except Exception as e:
                logger.error("Handler '%s' failed: %s", handler_info.name, e)
                errors.append({"handler": handler_info.name, "error": str(e)})

        return {
            "success": len(errors) == 0,
            "handlers_executed": len(results),
            "errors": errors if errors else None,
            "results": results,
        }

    async def _execute_handler(
        self,
        handler: Callable,
        source: str,
        event_type: str | None,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> Any:
        """Execute a handler function"""
        import inspect

        # Check if handler is async
        if inspect.iscoroutinefunction(handler):
            return await handler(source, event_type, payload, headers)
        else:
            return handler(source, event_type, payload, headers)

    def load_handler_module(
        self, module_path: str, function_name: str
    ) -> Callable | None:
        """Load a handler function from a module path"""
        try:
            module = importlib.import_module(module_path)
            handler = getattr(module, function_name)
            if callable(handler):
                return handler
            logger.error("'%s' in '%s' is not callable", function_name, module_path)
            return None
        except ImportError as e:
            logger.error("Failed to import handler module '%s': %s", module_path, e)
            return None
        except AttributeError as e:
            logger.error("Handler function '%s' not found in '%s': %s", function_name, module_path, e)
            return None

    def list_handlers(self) -> dict[str, list[dict[str, Any]]]:
        """List all registered handlers"""
        result = {}

        for source, handlers in self._handlers.items():
            result[source] = [h.__dict__ for h in handlers]

        result["_defaults"] = {k: v.__dict__ for k, v in self._default_handlers.items()}
        result["_global"] = [h.__dict__ for h in self._global_handlers]

        return result


# Global router instance
webhook_router = WebhookRouter()
