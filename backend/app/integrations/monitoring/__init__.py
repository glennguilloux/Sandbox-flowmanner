"""
Monitoring Package

Yellow Zone: Health checks and metrics collection for OpenWhisk integration.
"""

from .health_check import HealthCheck, create_health_check

__all__ = [
    'HealthCheck',
    'create_health_check',
]

__version__ = '1.0.0'
