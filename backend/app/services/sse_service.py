"""
SSE (Server-Sent Events) utilities for real-time mission updates.
Implements Story 1.2 (Real-Time Mission Updates) and Story B.4 (Hybrid HTTP/SSE/Redis pub/sub).
"""

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.config import settings


async def get_redis_client() -> Redis:
    """Get Redis client for pub/sub."""
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def publish_mission_update(mission_id: str, event_type: str, data: dict) -> None:
    """
    Publish a mission update to Redis channel.
    Called when mission status changes.
    """
    redis = await get_redis_client()
    try:
        channel = f"mission:{mission_id}:updates"
        message = json.dumps({"event": event_type, "data": data})
        await redis.publish(channel, message)
    finally:
        await redis.aclose()


async def publish_user_notification(user_id: int, notification_data: dict) -> None:
    """
    Publish a notification to a specific user's Redis channel for SSE delivery.
    Called by send_notification() when a notification needs real-time delivery.
    """
    redis = await get_redis_client()
    try:
        channel = f"user:{user_id}:notifications"
        message = json.dumps(notification_data)
        await redis.publish(channel, message)
    finally:
        await redis.aclose()


async def user_notification_sse_stream(user_id: int, initial_unread_count: int = 0) -> AsyncGenerator[str, None]:
    """
    SSE event stream for user notifications.
    Subscribes to Redis channel and yields events with proper SSE format
    for the frontend EventSource (notification and unread_count events).

    Sends an initial unread_count event on connect so the frontend
    has the current count immediately.
    """
    redis = await get_redis_client()
    pubsub = redis.pubsub()
    channel = f"user:{user_id}:notifications"

    await pubsub.subscribe(channel)

    try:
        # Send initial unread_count as first event
        yield f"event: unread_count\ndata: {json.dumps({'unread_count': initial_unread_count})}\n\n"

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
            if message:
                data = json.loads(message["data"])
                event_type = data.get("event", "notification")
                event_data = data.get("data", data)
                yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"
            else:
                # Send heartbeat keep-alive
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.01)
    except asyncio.CancelledError:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        raise


async def mission_sse_stream(mission_id: str) -> AsyncGenerator[str, None]:
    """
    SSE event stream for mission updates.
    Subscribes to Redis channel and yields events.
    """
    redis = await get_redis_client()
    pubsub = redis.pubsub()
    channel = f"mission:{mission_id}:updates"

    await pubsub.subscribe(channel)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
            if message:
                yield f"data: {message['data']}\n\n"
            else:
                # Send heartbeat
                yield 'data: {"event": "heartbeat"}\n\n'
            await asyncio.sleep(0.01)  # Small delay to prevent CPU spinning
    except asyncio.CancelledError:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        raise


async def mission_events_endpoint(mission_id: str):
    """FastAPI endpoint handler for SSE mission events."""
    return StreamingResponse(mission_sse_stream(mission_id), media_type="text/event-stream")
