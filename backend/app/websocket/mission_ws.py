"""WebSocket endpoint for real-time mission updates and workspace presence.

Uses Socket.IO for bidirectional communication.
Falls back to SSE via mission stream endpoint if Socket.IO is not available.

Events handled:
  - connect / disconnect    — JWT auth, presence tracking
  - subscribe_mission / unsubscribe_mission
  - subscribe_graph / unsubscribe_graph
  - workspace:subscribe     — join workspace room, mark presence, broadcast
  - workspace:dm            — relay direct messages between workspace members
  - workspace:typing        — broadcast typing indicator
"""

import logging

logger = logging.getLogger(__name__)

try:
    import socketio

    _sio_available = True
except ImportError:
    _sio_available = False

if _sio_available:
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
    # Mount socket.io at /ws — ASGIApp handles /socket.io/ paths internally.
    # Starlette Mount keeps the full path in scope["path"], so we work around
    # by creating a tiny ASGI wrapper that strips the /ws prefix.
    _inner = socketio.ASGIApp(sio, socketio_path="socket.io")

    class _StripWSPrefix:
        """ASGI wrapper that strips /ws prefix so Engine.IO sees /socket.io/..."""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] in ("http", "websocket"):
                path = scope.get("path", "")
                if path.startswith("/ws/"):
                    scope = {**scope, "path": path[3:]}  # strip /ws
                elif path == "/ws":
                    scope = {**scope, "path": "/"}
            await self.app(scope, receive, send)

    ws_app = _StripWSPrefix(_inner)

    # ── Presence helpers ───────────────────────────────────────────────

    async def _broadcast_presence(
        workspace_id: str,
        user_id: int,
        status: str,
        user_name: str = "",
        user_email: str = "",
        skip_sid: str | None = None,
    ):
        """Broadcast a presence event to all members of a workspace room."""
        await sio.emit(
            "workspace:presence",
            {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "status": status,
                "user_name": user_name,
                "user_email": user_email,
            },
            room=f"workspace_{workspace_id}",
            skip_sid=skip_sid,
        )

    async def _handle_presence_connect(
        workspace_id: str, user_id: int, sid: str
    ) -> None:
        """Track presence when a user connects to a workspace."""
        try:
            from app.websocket.presence import user_online

            is_first = await user_online(workspace_id, user_id, sid)
            if is_first:
                await _broadcast_presence(workspace_id, user_id, "online", skip_sid=sid)
                # Record workspace activity event (fire-and-forget)
                try:
                    from app.api.v1.workspace_activity import record_workspace_activity
                    from app.database import AsyncSessionLocal

                    async with AsyncSessionLocal() as session:
                        await record_workspace_activity(
                            session,
                            workspace_id=workspace_id,
                            user_id=str(user_id),
                            event_type="member_online",
                            actor_name=str(user_id),
                        )
                        await session.commit()
                except Exception:
                    logger.debug("presence_activity_record_failed", exc_info=True)
        except Exception as e:
            logger.warning(
                "Presence connect failed for user %d in ws %s: %s",
                user_id,
                workspace_id,
                e,
            )

    async def _handle_presence_disconnect(sid: str) -> None:
        """Track presence when a socket disconnects."""
        try:
            from app.websocket.presence import user_offline

            result = await user_offline(sid)
            if result and result.get("fully_offline"):
                await _broadcast_presence(
                    result["workspace_id"],
                    result["user_id"],
                    "offline",
                )
        except Exception as e:
            logger.warning("Presence disconnect failed for sid %s: %s", sid, e)

    # ── Core events ────────────────────────────────────────────────────

    @sio.event
    async def connect(sid, environ, auth):
        """Authenticate the WebSocket connection via JWT in auth handshake or Authorization header."""
        try:
            user_id = None

            # Try Socket.IO auth handshake first (client passes auth: { token })
            if auth and isinstance(auth, dict):
                token = auth.get("token")
                if token:
                    import jwt

                    from app.config import settings

                    try:
                        payload = jwt.decode(
                            token, settings.JWT_SECRET_KEY, algorithms=["HS256"]
                        )
                        user_id = int(payload.get("sub", 0))
                    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
                        logger.debug(
                            "WebSocket JWT auth handshake decode failed: %s", e
                        )

            # Fallback: try Authorization header via environ
            if not user_id:
                from app.websocket.presence import decode_token_from_environ

                payload = decode_token_from_environ(environ)
                if payload:
                    user_id = int(payload.get("sub", 0))

            if user_id:
                await sio.save_session(sid, {"user_id": user_id})
                logger.debug("WebSocket authenticated: user %d (sid=%s)", user_id, sid)
            else:
                logger.debug("WebSocket connect: no valid JWT (sid=%s)", sid)
                # Don't reject — allow anonymous for mission/graph subscriptions
        except Exception as e:
            logger.warning("WebSocket connect auth error (sid=%s): %s", sid, e)

    @sio.event
    async def disconnect(sid):
        """Clean up presence tracking when socket disconnects."""
        await _handle_presence_disconnect(sid)

    @sio.event
    async def subscribe_mission(sid, data):
        """Client subscribes to mission updates."""
        mission_id = data.get("mission_id")
        if mission_id:
            await sio.enter_room(sid, f"mission_{mission_id}")

    @sio.event
    async def unsubscribe_mission(sid, data):
        """Client unsubscribes from mission updates."""
        mission_id = data.get("mission_id")
        if mission_id:
            await sio.leave_room(sid, f"mission_{mission_id}")

    @sio.event
    async def subscribe_graph(sid, data):
        """Client subscribes to graph execution updates."""
        execution_id = data.get("execution_id")
        if execution_id:
            await sio.enter_room(sid, f"graph_exec_{execution_id}")

    @sio.event
    async def unsubscribe_graph(sid, data):
        """Client unsubscribes from graph execution updates."""
        execution_id = data.get("execution_id")
        if execution_id:
            await sio.leave_room(sid, f"graph_exec_{execution_id}")

    @sio.event
    async def workspace_subscribe(sid, data):
        """Client subscribes to a workspace room for presence and DMs.

        Expected data: { workspace_id: str }
        The user must be authenticated (JWT on connect) and a workspace member.
        """
        workspace_id = data.get("workspace_id")
        if not workspace_id:
            return

        session = await sio.get_session(sid)
        user_id = session.get("user_id") if session else None
        if not user_id:
            logger.debug("workspace:subscribe rejected: no auth (sid=%s)", sid)
            return

        # Validate workspace membership
        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal
            from app.models.workspace_models import WorkspaceMember

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(WorkspaceMember).where(
                        WorkspaceMember.workspace_id == workspace_id,
                        WorkspaceMember.user_id == user_id,
                        WorkspaceMember.is_active == True,
                    )
                )
                if not result.scalar_one_or_none():
                    logger.warning(
                        "workspace:subscribe rejected: user %d not a member of %s",
                        user_id,
                        workspace_id,
                    )
                    return
        except Exception as e:
            logger.error("workspace:subscribe DB check failed: %s", e)
            return

        # Join the workspace room
        room = f"workspace_{workspace_id}"
        await sio.enter_room(sid, room)
        logger.info(
            "User %d subscribed to workspace %s (sid=%s)", user_id, workspace_id, sid
        )

        # Track presence and broadcast
        await _handle_presence_connect(workspace_id, user_id, sid)

    @sio.event
    async def workspace_dm(sid, data):
        """Relay a direct message between workspace members.

        Expected data: { workspace_id: str, recipient_id: int, content: str }
        The message is forwarded to the workspace room.
        Only workspace members can send messages (fail-open on DB error).
        """
        session = await sio.get_session(sid)
        user_id = session.get("user_id") if session else None
        if not user_id:
            return

        workspace_id = data.get("workspace_id")
        recipient_id = data.get("recipient_id")
        content = data.get("content", "")

        if not workspace_id or not recipient_id or not content.strip():
            return

        # Light membership check (fail-open: allow message if DB is down)
        message_id = None
        message_created_at = None
        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal
            from app.models.workspace_models import WorkspaceMember, WorkspaceMessage

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(WorkspaceMember).where(
                        WorkspaceMember.workspace_id == workspace_id,
                        WorkspaceMember.user_id == user_id,
                        WorkspaceMember.is_active == True,
                    )
                )
                if not result.scalar_one_or_none():
                    return

                # Persist the message
                msg = WorkspaceMessage(
                    workspace_id=workspace_id,
                    sender_id=user_id,
                    recipient_id=recipient_id,
                    content=content.strip(),
                )
                db.add(msg)
                await db.commit()
                await db.refresh(msg)
                message_id = msg.id
                message_created_at = (
                    msg.created_at.isoformat() if msg.created_at else None
                )
        except Exception:
            logger.debug("workspace_dm_persist_failed", exc_info=True)

        # Emit to the workspace room — the frontend filters by recipient_id
        await sio.emit(
            "workspace:dm",
            {
                "id": message_id,
                "workspace_id": workspace_id,
                "sender_id": user_id,
                "recipient_id": recipient_id,
                "content": content,
                "created_at": message_created_at,
            },
            room=f"workspace_{workspace_id}",
        )

    @sio.event
    async def workspace_typing(sid, data):
        """Broadcast typing indicator in a workspace room.

        Expected data: { workspace_id: str, recipient_id: int, is_typing: bool }
        """
        session = await sio.get_session(sid)
        user_id = session.get("user_id") if session else None
        if not user_id:
            return

        workspace_id = data.get("workspace_id")
        recipient_id = data.get("recipient_id")
        is_typing = data.get("is_typing", False)

        if not workspace_id or not recipient_id:
            return

        await sio.emit(
            "workspace:typing",
            {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "recipient_id": recipient_id,
                "is_typing": is_typing,
            },
            room=f"workspace_{workspace_id}",
        )

else:
    # Fallback: no-op ASGI app
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def noop_endpoint(request):
        return JSONResponse(
            {
                "detail": "WebSocket not available. Use SSE endpoint /api/v1/missions/{id}/stream"
            },
            status_code=200,
        )

    ws_app = Starlette(routes=[Route("/{path:path}", noop_endpoint)])
    sio = ws_app  # For compatibility with main_fastapi.py mount
