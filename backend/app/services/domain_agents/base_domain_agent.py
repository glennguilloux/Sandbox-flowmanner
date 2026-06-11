"""Base class for domain-specific AI assistants"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseDomainAgent(ABC):
    """
    Abstract base class for domain-specific AI assistants.

    Each domain agent (Legal, Finance, Biotech) inherits from this class
    and implements domain-specific prompts, tools, and response handling.
    """

    # Domain metadata - override in subclasses
    domain_name: str = "base"
    domain_icon: str = "🤖"
    domain_color: str = "#6B7280"
    domain_description: str = "Base domain agent"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.model = self.config.get("model", "qwen3.5:35b")
        self.temperature = self.config.get("temperature", 0.7)
        self.max_tokens = self.config.get("max_tokens", 4096)
        self.api_key = self.config.get("api_key")
        self._llm_client = None

    @property
    def metadata(self) -> dict[str, str]:
        """Return domain metadata for UI rendering"""
        return {
            "domain": self.domain_name,
            "icon": self.domain_icon,
            "color": self.domain_color,
            "description": self.domain_description,
        }

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the domain-specific system prompt"""
        pass

    @abstractmethod
    def get_tools(self) -> list[dict[str, Any]]:
        """Return domain-specific tools/capabilities"""
        pass

    @abstractmethod
    def process_response(self, response: str) -> dict[str, Any]:
        """Process and structure the LLM response"""
        pass

    async def run(self, query: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Execute a query against the domain agent using a real LLM call.

        Uses BudgetEnforcer.call() — the single LLM call path — with the
        domain-specific system prompt.

        Falls back to the previous echo behavior if the LLM call fails
        (e.g. no models available, budget exhausted).

        Args:
            query: The user's question or request
            context: Optional context (previous messages, user info, etc.)

        Returns:
            Dict containing the response and metadata
        """
        logger.info("[%s] Processing query: %s...", self.domain_name.upper(), query[:100])

        try:
            from app.models.capability_models import Budget
            from app.services.budget_enforcer import get_budget_enforcer

            enforcer = get_budget_enforcer()
            system_prompt = self.get_system_prompt()

            messages: list[dict] = [{"role": "system", "content": system_prompt}]
            if context and context.get("history"):
                messages.extend(context["history"])
            messages.append({"role": "user", "content": query})

            response = await enforcer.call(
                budget=Budget(max_cost_usd=0.50),
                model_id=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if response.get("success"):
                result = {
                    "domain": self.domain_name,
                    "query": query,
                    "response": response.get("response", ""),
                    "metadata": self.metadata,
                    "success": True,
                    "model": response.get("model"),
                    "usage": response.get("cost"),
                }
                return result

        except Exception as e:
            logger.warning(
                "[%s] LLM call failed, falling back to echo: %s",
                self.domain_name.upper(),
                e,
            )

        # Graceful fallback: echo the input (maintains availability)
        return {
            "domain": self.domain_name,
            "query": query,
            "response": f"[{self.domain_name.upper()}] {query}",
            "metadata": self.metadata,
            "success": True,
            "fallback": True,
        }

    def validate_config(self) -> bool:
        """Validate the agent configuration"""
        return True

    def get_capabilities(self) -> list[str]:
        """Return list of domain-specific capabilities"""
        return []
