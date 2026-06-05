#!/usr/bin/env python3
"""
RabbitMQ Initialization Script

This module provides functions to explicitly declare RabbitMQ exchanges and queues
before Celery workers start. This ensures the infrastructure exists and prevents
"no exchange 'X' in vhost '/'" errors.

Usage:
    python -m app.tasks.init_rabbitmq

    Or import and call:
    from app.tasks.init_rabbitmq import initialize_rabbitmq_infrastructure
    initialize_rabbitmq_infrastructure()
"""

import logging
import time
from typing import Any

from kombu import Connection, Exchange, Queue

from app.app_config import Config

logger = logging.getLogger(__name__)

# Exchange definitions matching celery_app.py
EXCHANGES = {
    "priority": {"type": "direct", "durable": True},
    "tasks": {"type": "direct", "durable": True},
    "default": {"type": "direct", "durable": True},
}

# Queue definitions matching celery_app.py
QUEUES = {
    "high_priority": {
        "exchange": "priority",
        "routing_key": "high_priority",
        "arguments": {"x-max-priority": 10},
    },
    "medium_priority": {
        "exchange": "priority",
        "routing_key": "medium_priority",
        "arguments": {"x-max-priority": 10},
    },
    "low_priority": {
        "exchange": "priority",
        "routing_key": "low_priority",
        "arguments": {"x-max-priority": 10},
    },
    "langgraph": {"exchange": "tasks", "routing_key": "langgraph"},
    "phase4": {"exchange": "tasks", "routing_key": "phase4"},
    "n8n": {"exchange": "tasks", "routing_key": "n8n"},
    "comfyui": {"exchange": "tasks", "routing_key": "comfyui"},
    "workers": {"exchange": "tasks", "routing_key": "workers"},
    "swarm": {"exchange": "tasks", "routing_key": "swarm"},
    "deepagents": {"exchange": "tasks", "routing_key": "deepagents"},
    "default": {"exchange": "default", "routing_key": "default"},
}


def initialize_rabbitmq_infrastructure(
    max_retries: int = 5, retry_delay: int = 5
) -> dict[str, Any]:
    """
    Initialize RabbitMQ by declaring all exchanges and queues.

    This function connects to RabbitMQ and explicitly declares all exchanges
    and queues defined in the configuration. It includes retry logic for
    handling connection issues during startup.

    Args:
        max_retries: Maximum number of connection retry attempts
        retry_delay: Seconds to wait between retry attempts

    Returns:
        Dictionary containing:
        - success: bool indicating if initialization succeeded
        - exchanges_created: List of created exchange names
        - queues_created: List of created queue names
        - errors: List of any errors encountered
    """
    result = {
        "success": False,
        "exchanges_created": [],
        "queues_created": [],
        "errors": [],
    }

    broker_url = Config.CELERY_BROKER_URL

    # Mask credentials in logs
    safe_url = broker_url
    if "@" in safe_url:
        parts = safe_url.split("@")
        if ":" in parts[0]:
            protocol_and_creds = parts[0].split("://")
            if len(protocol_and_creds) == 2:
                safe_url = f"{protocol_and_creds[0]}://***:***@{parts[1]}"

    logger.info(f"Initializing RabbitMQ infrastructure at {safe_url}")

    for attempt in range(1, max_retries + 1):
        try:
            with Connection(broker_url, connect_timeout=10) as conn:
                logger.info(f"Connected to RabbitMQ (attempt {attempt}/{max_retries})")

                channel = conn.default_channel

                # Declare exchanges
                for exchange_name, exchange_config in EXCHANGES.items():
                    try:
                        exchange = Exchange(
                            exchange_name,
                            type=exchange_config["type"],
                            durable=exchange_config["durable"],
                        )
                        exchange.declare(channel=channel)
                        result["exchanges_created"].append(exchange_name)
                        logger.info(f"Declared exchange: {exchange_name}")
                    except Exception as e:
                        error_msg = f"Failed to declare exchange '{exchange_name}': {e}"
                        result["errors"].append(error_msg)
                        logger.error(error_msg)

                # Declare queues
                for queue_name, queue_config in QUEUES.items():
                    try:
                        exchange = Exchange(
                            queue_config["exchange"],
                            type="direct",
                            durable=True,
                        )
                        queue = Queue(
                            queue_name,
                            exchange=exchange,
                            routing_key=queue_config["routing_key"],
                            queue_arguments=queue_config.get("arguments"),
                            durable=True,
                        )
                        queue.declare(channel=channel)
                        result["queues_created"].append(queue_name)
                        logger.info(f"Declared queue: {queue_name}")
                    except Exception as e:
                        error_msg = f"Failed to declare queue '{queue_name}': {e}"
                        result["errors"].append(error_msg)
                        logger.error(error_msg)

                result["success"] = len(result["errors"]) == 0
                if result["success"]:
                    logger.info(
                        "RabbitMQ infrastructure initialization completed successfully"
                    )
                else:
                    logger.warning(
                        f"RabbitMQ initialization completed with {len(result['errors'])} errors"
                    )

                return result

        except Exception as e:
            error_msg = f"Connection attempt {attempt} failed: {e}"
            result["errors"].append(error_msg)
            logger.warning(error_msg)

            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(
                    f"Failed to connect to RabbitMQ after {max_retries} attempts"
                )

    return result


def verify_rabbitmq_infrastructure() -> dict[str, Any]:
    """
    Verify that all required RabbitMQ exchanges and queues exist.

    This function can be used as a health check to ensure the RabbitMQ
    infrastructure is properly configured before starting workers.

    Returns:
        Dictionary containing:
        - healthy: bool indicating if all required components exist
        - exchanges_found: List of exchange names that exist
        - exchanges_missing: List of exchange names that are missing
        - queues_found: List of queue names that exist
        - queues_missing: List of queue names that are missing
        - errors: List of any errors encountered during verification
    """
    result = {
        "healthy": False,
        "exchanges_found": [],
        "exchanges_missing": [],
        "queues_found": [],
        "queues_missing": [],
        "errors": [],
    }

    broker_url = Config.CELERY_BROKER_URL

    try:
        with Connection(broker_url, connect_timeout=5) as conn:
            channel = conn.default_channel

            # Check exchanges
            for exchange_name in EXCHANGES:
                try:
                    exchange = Exchange(exchange_name, type="direct", durable=True)
                    exchange.declare(channel=channel, passive=True)
                    result["exchanges_found"].append(exchange_name)
                    logger.debug(f"Exchange exists: {exchange_name}")
                except Exception:
                    result["exchanges_missing"].append(exchange_name)
                    logger.warning(f"Exchange missing: {exchange_name}")

            # Check queues
            for queue_name in QUEUES:
                try:
                    queue_config = QUEUES[queue_name]
                    exchange = Exchange(
                        queue_config["exchange"], type="direct", durable=True
                    )
                    queue = Queue(
                        queue_name,
                        exchange=exchange,
                        routing_key=queue_config["routing_key"],
                        queue_arguments=queue_config.get("arguments"),
                        durable=True,
                    )
                    queue.declare(channel=channel, passive=True)
                    result["queues_found"].append(queue_name)
                    logger.debug(f"Queue exists: {queue_name}")
                except Exception:
                    result["queues_missing"].append(queue_name)
                    logger.warning(f"Queue missing: {queue_name}")

            result["healthy"] = (
                len(result["exchanges_missing"]) == 0
                and len(result["queues_missing"]) == 0
            )

            if result["healthy"]:
                logger.info("RabbitMQ infrastructure verification: HEALTHY")
            else:
                logger.warning(
                    f"RabbitMQ infrastructure verification: UNHEALTHY - "
                    f"Missing {len(result['exchanges_missing'])} exchanges, "
                    f"{len(result['queues_missing'])} queues"
                )

    except Exception as e:
        error_msg = f"Failed to verify RabbitMQ infrastructure: {e}"
        result["errors"].append(error_msg)
        logger.error(error_msg)

    return result


def get_infrastructure_status() -> str:
    """
    Get a human-readable status summary of RabbitMQ infrastructure.

    Returns:
        Multi-line string with status information
    """
    verification = verify_rabbitmq_infrastructure()

    lines = [
        "=" * 60,
        "RabbitMQ Infrastructure Status",
        "=" * 60,
        f"Status: {'HEALTHY' if verification['healthy'] else 'UNHEALTHY'}",
        "",
        f"Exchanges Found ({len(verification['exchanges_found'])}):",
    ]

    for exchange in verification["exchanges_found"]:
        lines.append(f"  - {exchange}")

    if verification["exchanges_missing"]:
        lines.append(f"\nExchanges Missing ({len(verification['exchanges_missing'])}):")
        for exchange in verification["exchanges_missing"]:
            lines.append(f"  - {exchange}")

    lines.append(f"\nQueues Found ({len(verification['queues_found'])}):")
    for queue in verification["queues_found"]:
        lines.append(f"  - {queue}")

    if verification["queues_missing"]:
        lines.append(f"\nQueues Missing ({len(verification['queues_missing'])}):")
        for queue in verification["queues_missing"]:
            lines.append(f"  - {queue}")

    if verification["errors"]:
        lines.append(f"\nErrors ({len(verification['errors'])}):")
        for error in verification["errors"]:
            lines.append(f"  - {error}")

    lines.append("=" * 60)

    return "\n".join(lines)


if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("RabbitMQ Infrastructure Initialization")
    print("=" * 60)

    # Initialize infrastructure
    result = initialize_rabbitmq_infrastructure()

    print()
    if result["success"]:
        print("SUCCESS: RabbitMQ infrastructure initialized")
        print(f"  Exchanges created: {len(result['exchanges_created'])}")
        print(f"  Queues created: {len(result['queues_created'])}")
    else:
        print("PARTIAL SUCCESS: Some components failed to initialize")
        print(f"  Exchanges created: {len(result['exchanges_created'])}")
        print(f"  Queues created: {len(result['queues_created'])}")
        print(f"  Errors: {len(result['errors'])}")

    print()
    print("Status Summary:")
    print(get_infrastructure_status())
