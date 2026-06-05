#!/usr/bin/env python3
"""
Tool Handler Registry (Governance Layer)

Registry for managing tool handlers in governance layer.
Integrates WorkerHandler with other handlers for unified access.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ToolHandlerRegistry:
    """
    Registry for managing tool handlers in governance layer.
    
    Responsibilities:
    - Register tool handlers
    - Select appropriate handler for tasks
    - Execute tools via selected handler
    - List available handlers and actions
    """
    
    def __init__(self, redis_client=None):
        """
        Initialize tool handler registry.
        
        Args:
            redis_client: Optional Redis client for caching
        """
        self._handlers: dict[str, Any] = {}
        self._handler_configs: dict[str, dict[str, Any]] = {}
        self.redis_client = redis_client
        self.logger = logging.getLogger(__name__)
        
        # Register default handlers
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Register default tool handlers"""
        # Register WorkerHandler (lazy import to avoid circular dependency)
        from .worker_handler import WorkerHandler
        self.register_handler("worker", WorkerHandler())
        self.logger.info("Registered WorkerHandler as 'worker' handler")
    
    def register_handler(
        self,
        handler_id: str,
        handler: Any,
        config: dict[str, Any] | None = None
    ):
        """
        Register a tool handler.
        
        Args:
            handler_id: Unique handler identifier
            handler: Handler instance
            config: Optional handler configuration
        """
        # Check for required methods
        required_methods = ['execute', 'get_available_actions']
        for method in required_methods:
            if not hasattr(handler, method):
                raise ValueError(
                    f"Handler must implement method '{method}': {type(handler).__name__}"
                )
        
        self._handlers[handler_id] = handler
        if config:
            self._handler_configs[handler_id] = config
        
        self.logger.info(f"Registered handler: {handler_id} ({type(handler).__name__})")
    
    def get_handler(self, handler_id: str) -> Any | None:
        """
        Get handler by ID.
        
        Args:
            handler_id: Handler identifier
            
        Returns:
            Handler instance or None
        """
        return self._handlers.get(handler_id)
    
    def select_handler_for_task(
        self,
        task_type: str,
        task_params: dict[str, Any]
    ) -> str | None:
        """
        Select appropriate handler for a task.
        
        Args:
            task_type: Type of task (e.g., 'worker', 'n8n', 'comfyui')
            task_params: Task parameters
            
        Returns:
            Handler ID or None
        """
        # Check if handler exists for task_type
        if task_type in self._handlers:
            return task_type
        
        # Auto-select based on task parameters
        if 'action' in task_params:
            action = task_params['action']
            
            # Worker task actions
            worker_actions = [
                'step_2a_generate_request',
                'step_2b_process_response',
                'data_fetch',
                'data_transform'
            ]
            
            if action in worker_actions:
                return 'worker'
        
        # Default to worker handler
        return 'worker'
    
    def execute(
        self,
        handler_id: str,
        action: str,
        params: dict[str, Any],
        **kwargs
    ) -> dict[str, Any]:
        """
        Execute a task via specified handler.
        
        Args:
            handler_id: Handler to use
            action: Action to execute
            params: Action parameters
            **kwargs: Additional parameters
            
        Returns:
            Execution result
        """
        handler = self.get_handler(handler_id)
        if not handler:
            return {
                "success": False,
                "error": f"Handler not found: {handler_id}"
            }
        
        try:
            # Check if handler has execute method with expected signature
            if hasattr(handler, 'execute'):
                return handler.execute(action, params, **kwargs)
            else:
                return {
                    "success": False,
                    "error": f"Handler does not support execute method"
                }
        except Exception as e:
            self.logger.error(f"Execution error via {handler_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "handler_id": handler_id
            }
    
    def execute_with_auto_select(
        self,
        action: str,
        params: dict[str, Any],
        **kwargs
    ) -> dict[str, Any]:
        """
        Execute a task with automatic handler selection.
        
        Args:
            action: Action to execute
            params: Action parameters
            **kwargs: Additional parameters
            
        Returns:
            Execution result
        """
        handler_id = self.select_handler_for_task("auto", params)
        if not handler_id:
            return {
                "success": False,
                "error": "No suitable handler found"
            }
        
        return self.execute(handler_id, action, params, **kwargs)
    
    def list_handlers(self) -> dict[str, dict[str, Any]]:
        """
        List all registered handlers.
        
        Returns:
            Dictionary of handler information
        """
        handlers_info = {}
        
        for handler_id, handler in self._handlers.items():
            try:
                info = {
                    "handler_id": handler_id,
                    "handler_name": type(handler).__name__,
                }
                
                if hasattr(handler, 'get_available_actions'):
                    info["available_actions"] = handler.get_available_actions()
                
                handlers_info[handler_id] = info
            except Exception as e:
                self.logger.error(f"Error getting info for {handler_id}: {e}")
                handlers_info[handler_id] = {
                    "error": str(e)
                }
        
        return handlers_info
    
    def list_actions(self, handler_id: str | None = None) -> dict[str, list[str]]:
        """
        List available actions.
        
        Args:
            handler_id: Optional handler ID to filter
            
        Returns:
            Dictionary of handler ID to actions list
        """
        if handler_id:
            handler = self.get_handler(handler_id)
            if handler and hasattr(handler, 'get_available_actions'):
                return {handler_id: handler.get_available_actions()}
            return {}
        
        # List all actions for all handlers
        all_actions = {}
        for handler_id, handler in self._handlers.items():
            try:
                if hasattr(handler, 'get_available_actions'):
                    all_actions[handler_id] = handler.get_available_actions()
            except Exception as e:
                self.logger.error(f"Error listing actions for {handler_id}: {e}")
                all_actions[handler_id] = []
        
        return all_actions
    
    def get_handler_status(self, handler_id: str) -> dict[str, Any]:
        """
        Get handler status.
        
        Args:
            handler_id: Handler identifier
            
        Returns:
            Handler status information
        """
        handler = self.get_handler(handler_id)
        if not handler:
            return {
                "status": "not_found",
                "handler_id": handler_id
            }
        
        status_info = {
            "status": "available",
            "handler_id": handler_id,
            "handler_name": type(handler).__name__,
        }
        
        if hasattr(handler, 'get_available_actions'):
            status_info["available_actions"] = handler.get_available_actions()
        
        return status_info


# Global registry instance
_registry = None


def get_tool_handler_registry(redis_client=None) -> ToolHandlerRegistry:
    """
    Get global tool handler registry instance.
    
    Args:
        redis_client: Optional Redis client
        
    Returns:
        ToolHandlerRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ToolHandlerRegistry(redis_client=redis_client)
    return _registry
