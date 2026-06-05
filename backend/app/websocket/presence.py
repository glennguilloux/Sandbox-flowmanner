"""
Presence tracking service for workspace online/offline status.

Uses Redis to track which users are online per workspace, with support
for multiple socket connections per user (multi-tab). Broadcasts presence
change events to all workspace members via Socket.IO.

Redis keys:
    ws_presence:workspace:{workspace_id} → Hash: user_id (int) → socket_count (int)
    ws_presence:socket:{socket_id}       → Hash: user_id, workspace_id, connected_at

Socket.IO events (emitted by this module):
    workspace:presence → { workspace_id, user_id, user_name, user_email, status: "online"|"offline" }

REST endpoint: GET /api/v1/workspaces/{id}/presence → { online_user_ids: [...], online_users: [...] }
"""

import logging
import time

from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)

PRESENCE_WS_KEY = "ws_presence:workspace:{workspace_id}"
PRESENCE_SOCKET_KEY = "ws_presence:socket:{socket_id}"

_redis_client: Redis | None = None


async def _get_redis() -> Redis | None:
    """Get or create the async Redis client for presence tracking."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
            await _redis_client.ping()
            logger.info("Presence Redis client connected")
        except Exception as e:
            logger.warning("Presence Redis unavailable: %s", e)
            _redis_client = None
    return _redis_client


async def _close_redis() -> None:
    """Close the Redis client on shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


def decode_token_from_environ(environ: dict) -> dict | None:
    """
    Extract and decode a JWT token from Socket.IO environ headers.

    Returns the decoded payload dict (with 'sub' = user_id) or None.
    """
    import jwt

    # Socket.IO stores HTTP headers in environ with HTTP_ prefix
    auth_header = environ.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        # Also check lowercase (some proxies)
        auth_header = environ.get("http_authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

    token = auth_header[7:]
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"],
        )
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
        logger.debug("WebSocket JWT decode failed: %s", e)
        return None


async def user_online(workspace_id: str, user_id: int, socket_id: str) -> bool:
    """
    Mark a user as online in a workspace.

    Increments the socket count for this user in the workspace.
    Returns True if this is the user's first connection (was offline before),
    False if they already had another socket open.
    """
    redis = await _get_redis()
    if redis is None:
        return False

    ws_key = PRESENCE_WS_KEY.format(workspace_id=workspace_id)
    socket_key = PRESENCE_SOCKET_KEY.format(socket_id=socket_id)

    # Store socket metadata
    await redis.hset(socket_key, mapping={
        "user_id": str(user_id),
        "workspace_id": workspace_id,
        "connected_at": str(time.time()),
    })
    await redis.expire(socket_key, 86400)  # 24h TTL as safety net

    # Increment socket count and check if first connection
    new_count = await redis.hincrby(ws_key, str(user_id), 1)
    await redis.expire(ws_key, 86400)

    is_first_connection = new_count == 1
    if is_first_connection:
        logger.info(
            "User %d came online in workspace %s (socket %s)",
            user_id, workspace_id, socket_id,
        )
    return is_first_connection


async def user_offline(socket_id: str) -> dict | None:
    """
    Mark a user as offline (one socket disconnected).

    Returns a dict with {workspace_id, user_id, fully_offline} if the socket
    was tracked, or None if the socket wasn't found.
    """
    redis = await _get_redis()
    if redis is None:
        return None

    socket_key = PRESENCE_SOCKET_KEY.format(socket_id=socket_id)
    socket_data = await redis.hgetall(socket_key)
    if not socket_data:
        return None

    user_id = int(socket_data["user_id"])
    workspace_id = socket_data["workspace_id"]

    # Clean up socket key
    await redis.delete(socket_key)

    # Decrement count; remove if zero
    ws_key = PRESENCE_WS_KEY.format(workspace_id=workspace_id)
    new_count = await redis.hincrby(ws_key, str(user_id), -1)

    fully_offline = new_count <= 0
    if fully_offline:
        await redis.hdel(ws_key, str(user_id))
        logger.info(
            "User %d went fully offline in workspace %s",
            user_id, workspace_id,
        )

    return {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "fully_offline": fully_offline,
    }


async def get_online_users(workspace_id: str) -> list[int]:
    """
    Get the list of online user IDs for a workspace.
    """
    redis = await _get_redis()
    if redis is None:
        return []

    ws_key = PRESENCE_WS_KEY.format(workspace_id=workspace_id)
    user_ids_str = await redis.hkeys(ws_key)
    return [int(uid) for uid in user_ids_str]


async def get_workspace_for_socket(socket_id: str) -> str | None:
    """
    Get the workspace_id associated with a socket.
    """
    redis = await _get_redis()
    if redis is None:
        return None

    socket_key = PRESENCE_SOCKET_KEY.format(socket_id=socket_id)
    return await redis.hget(socket_key, "workspace_id")
