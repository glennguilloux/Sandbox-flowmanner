"""
Linear Integration Package

Provides:
- Linear API client (async GraphQL)
- Webhook handler (issue → mission bridge)
- Mission sync (mission → issue feedback)
"""

from .client import LinearClient, get_linear_client
from .sync import sync_mission_to_linear

__all__ = [
    "LinearClient",
    "get_linear_client",
    "sync_mission_to_linear",
]
