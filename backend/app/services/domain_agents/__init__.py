"""Domain-Specific AI Assistants for FlowMind"""

from .base_domain_agent import BaseDomainAgent
from .biotech.agent import BiotechAgent
from .finance.agent import FinanceAgent
from .legal.agent import LegalAgent

__all__ = [
    "BaseDomainAgent",
    "BiotechAgent",
    "FinanceAgent",
    "LegalAgent",
]

DOMAIN_REGISTRY = {
    "legal": LegalAgent,
    "finance": FinanceAgent,
    "biotech": BiotechAgent,
}


def get_domain_agent(domain: str, config: dict = None):
    """Factory function to get a domain agent by name"""
    agent_class = DOMAIN_REGISTRY.get(domain)
    if agent_class:
        return agent_class(config=config)
    raise ValueError(f"Unknown domain: {domain}")
