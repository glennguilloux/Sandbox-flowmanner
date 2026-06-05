"""
Provider Factory

Factory for creating AI provider service instances.
Supports OpenRouter and DeepSeek providers.
"""

import logging

from .deepseek_service import DeepSeekService
from .openrouter_service import OpenRouterService

logger = logging.getLogger(__name__)


class ProviderFactory:
    """
    Factory for creating AI provider service instances.

    Provides a centralized way to instantiate and access provider services.
    Supports user-specific API keys for 'bring your own LLM' feature.
    """

    _instances = {}

    @staticmethod
    def create(provider: str, api_key: str | None = None) -> object | None:
        """
        Create and return a provider service instance.

        Args:
            provider: Provider name ("openrouter" or "deepseek")
            api_key: Optional user API key (for BYO LLM feature)

        Returns:
            Provider service instance or None if provider not found
        """
        provider = provider.lower().strip()

        # Return cached instance if available and no custom API key
        if api_key is None and provider in ProviderFactory._instances:
            return ProviderFactory._instances[provider]

        providers = {
            "openrouter": OpenRouterService,
            "deepseek": DeepSeekService,
        }

        if provider not in providers:
            logger.warning(f"Unknown provider: {provider}")
            return None

        # Create instance with optional API key
        instance = providers[provider](api_key=api_key)

        # Cache instance only if using platform key (no custom key)
        if api_key is None:
            ProviderFactory._instances[provider] = instance

        logger.info(
            f"Created {provider} provider service instance (using {'user' if api_key else 'platform'} key)"
        )

        return instance

    @staticmethod
    def get(provider: str) -> object | None:
        """
        Get a provider service instance (alias for create).

        Args:
            provider: Provider name

        Returns:
            Provider service instance or None
        """
        return ProviderFactory.create(provider)

    @staticmethod
    def get_openrouter() -> OpenRouterService:
        """Get the OpenRouter service instance."""
        return ProviderFactory.create("openrouter")

    @staticmethod
    def get_deepseek() -> DeepSeekService:
        """Get the DeepSeek service instance."""
        return ProviderFactory.create("deepseek")

    @staticmethod
    def list_providers() -> list:
        """List all available providers."""
        return ["openrouter", "deepseek"]

    @staticmethod
    def clear_cache():
        """Clear cached provider instances."""
        ProviderFactory._instances.clear()
        logger.info("Cleared provider factory cache")
