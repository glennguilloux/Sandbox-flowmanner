"""
Celery application configuration.
"""

import os

from celery import Celery

# Create Celery app with RabbitMQ broker
celery_app = Celery(
    "workflows",
    broker=os.getenv(
        "CELERY_BROKER_URL", "amqp://rabbitmq:rabbitmq_password@rabbitmq:5672//"
    ),
    backend=os.getenv("REDIS_URL", "redis://redis:6379"),
    include=[],
)

# Optional configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
