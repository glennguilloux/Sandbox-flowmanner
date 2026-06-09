#!/usr/bin/env python3
"""
A2A Server - FastA2A Protocol Implementation

Provides WebSocket-based agent-to-agent communication following FastA2A v0.2+ protocol.
Supports session management, agent routing, and file attachments.
"""

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """A2A message types"""

    TASK = "task"
    RESPONSE = "response"
    STATUS = "status"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    FILE = "file"


class SessionState(str, Enum):
    """Session states"""

    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class A2AMessage:
    """A2A protocol message"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.TASK
    sender: str = ""
    receiver: str = ""
    content: str = ""
    attachments: list[str] = field(default_factory=list)
    context_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "content": self.content,
            "attachments": self.attachments,
            "context_id": self.context_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "A2AMessage":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=MessageType(data.get("type", "task")),
            sender=data.get("sender", ""),
            receiver=data.get("receiver", ""),
            content=data.get("content", ""),
            attachments=data.get("attachments", []),
            context_id=data.get("context_id"),
            timestamp=data.get("timestamp", datetime.now(UTC).isoformat()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class A2ASession:
    """A2A communication session"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_url: str = ""
    state: SessionState = SessionState.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_activity: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    message_count: int = 0
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def update_activity(self):
        self.last_activity = datetime.now(UTC).isoformat()
        self.message_count += 1


class A2ASessionManager:
    """Manages A2A sessions"""

    def __init__(self):
        self._sessions: dict[str, A2ASession] = {}
        self._agent_sessions: dict[str, set[str]] = {}  # agent_url -> session_ids
        self._lock = asyncio.Lock()

    async def create_session(
        self, agent_url: str, context_id: str | None = None
    ) -> A2ASession:
        """Create a new session"""
        async with self._lock:
            session = A2ASession(
                agent_url=agent_url,
                context={"context_id": context_id} if context_id else {},
            )
            self._sessions[session.id] = session

            if agent_url not in self._agent_sessions:
                self._agent_sessions[agent_url] = set()
            self._agent_sessions[agent_url].add(session.id)

            logger.info("Created A2A session %s for agent %s", session.id, agent_url)
            return session

    async def get_session(self, session_id: str) -> A2ASession | None:
        """Get session by ID"""
        return self._sessions.get(session_id)

    async def list_sessions(self, agent_url: str | None = None) -> list[A2ASession]:
        """List all sessions, optionally filtered by agent"""
        if agent_url:
            session_ids = self._agent_sessions.get(agent_url, set())
            return [self._sessions[sid] for sid in session_ids if sid in self._sessions]
        return list(self._sessions.values())

    async def close_session(self, session_id: str) -> bool:
        """Close a session"""
        async with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.state = SessionState.CLOSED

                if session.agent_url in self._agent_sessions:
                    self._agent_sessions[session.agent_url].discard(session_id)

                logger.info("Closed A2A session %s", session_id)
                return True
            return False

    async def update_activity(self, session_id: str):
        """Update session activity"""
        if session_id in self._sessions:
            self._sessions[session_id].update_activity()


class A2AAgentRegistry:
    """Registry of available agents"""

    def __init__(self):
        self._agents: dict[str, dict[str, Any]] = {}

    def register_agent(self, agent_id: str, agent_info: dict[str, Any]):
        """Register an agent"""
        self._agents[agent_id] = {
            "id": agent_id,
            "name": agent_info.get("name", agent_id),
            "description": agent_info.get("description", ""),
            "capabilities": agent_info.get("capabilities", []),
            "status": agent_info.get("status", "available"),
            "url": agent_info.get("url", ""),
            "registered_at": datetime.now(UTC).isoformat(),
        }
        logger.info("Registered agent: %s", agent_id)

    def unregister_agent(self, agent_id: str):
        """Unregister an agent"""
        self._agents.pop(agent_id, None)
        logger.info("Unregistered agent: %s", agent_id)

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        """Get agent info"""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents"""
        return list(self._agents.values())


class A2AServer:
    """
    FastA2A Protocol Server

    Handles WebSocket connections for agent-to-agent communication.
    Implements session management, message routing, and file attachments.
    """

    def __init__(self):
        self.session_manager = A2ASessionManager()
        self.agent_registry = A2AAgentRegistry()
        self._connections: dict[str, WebSocket] = {}  # session_id -> websocket
        self._message_handlers: dict[MessageType, callable] = {}

        # Register default handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register message type handlers"""
        self._message_handlers = {
            MessageType.TASK: self._handle_task,
            MessageType.RESPONSE: self._handle_response,
            MessageType.STATUS: self._handle_status,
            MessageType.ERROR: self._handle_error,
            MessageType.HEARTBEAT: self._handle_heartbeat,
            MessageType.FILE: self._handle_file,
        }

    async def connect(self, websocket: WebSocket, agent_url: str) -> str:
        """Accept WebSocket connection and create session"""
        await websocket.accept()

        session = await self.session_manager.create_session(agent_url)
        self._connections[session.id] = websocket

        # Send connection confirmation
        await self._send_message(
            websocket,
            A2AMessage(
                type=MessageType.STATUS,
                content="connected",
                metadata={"session_id": session.id},
            ),
        )

        logger.info("WebSocket connected: session=%s, agent=%s", session.id, agent_url)
        return session.id

    async def disconnect(self, session_id: str):
        """Handle WebSocket disconnection"""
        await self.session_manager.close_session(session_id)
        self._connections.pop(session_id, None)
        logger.info("WebSocket disconnected: session=%s", session_id)

    async def _send_message(self, websocket: WebSocket, message: A2AMessage):
        """Send message through WebSocket"""
        try:
            await websocket.send_json(message.to_dict())
        except Exception as e:
            logger.error("Error sending message: %s", e)

    async def receive_message(
        self, session_id: str, data: dict[str, Any]
    ) -> A2AMessage | None:
        """Process received message"""
        try:
            message = A2AMessage.from_dict(data)
            await self.session_manager.update_activity(session_id)

            handler = self._message_handlers.get(message.type)
            if handler:
                return await handler(message, session_id)

            return message
        except Exception as e:
            logger.error("Error processing message: %s", e)
            return A2AMessage(
                type=MessageType.ERROR,
                content=str(e),
                metadata={"session_id": session_id},
            )

    async def _handle_task(self, message: A2AMessage, session_id: str) -> A2AMessage:
        """Handle task message"""
        logger.info("Task received: %s from %s", message.id, message.sender)
        # Task handling logic - route to appropriate agent
        return message

    async def _handle_response(
        self, message: A2AMessage, session_id: str
    ) -> A2AMessage:
        """Handle response message"""
        logger.info("Response received: %s", message.id)
        return message

    async def _handle_status(self, message: A2AMessage, session_id: str) -> A2AMessage:
        """Handle status message"""
        logger.info("Status update: %s", message.content)
        return message

    async def _handle_error(self, message: A2AMessage, session_id: str) -> A2AMessage:
        """Handle error message"""
        logger.error("Error from %s: %s", message.sender, message.content)
        return message

    async def _handle_heartbeat(
        self, message: A2AMessage, session_id: str
    ) -> A2AMessage:
        """Handle heartbeat - respond with pong"""
        return A2AMessage(
            type=MessageType.HEARTBEAT, content="pong", context_id=message.context_id
        )

    async def _handle_file(self, message: A2AMessage, session_id: str) -> A2AMessage:
        """Handle file attachment message"""
        logger.info("File received: %s", message.attachments)
        return message

    async def send_to_agent(self, agent_id: str, message: A2AMessage) -> bool:
        """Route message to specific agent"""
        agent = self.agent_registry.get_agent(agent_id)
        if not agent:
            logger.warning("Agent not found: %s", agent_id)
            return False

        # Find active session for agent
        sessions = await self.session_manager.list_sessions(agent.get("url", ""))
        for session in sessions:
            if session.state == SessionState.ACTIVE and session.id in self._connections:
                await self._send_message(self._connections[session.id], message)
                return True

        return False

    async def broadcast(self, message: A2AMessage, exclude_session: str | None = None):
        """Broadcast message to all connected sessions"""
        for session_id, websocket in self._connections.items():
            if session_id != exclude_session:
                await self._send_message(websocket, message)


# Global server instance
_a2a_server: A2AServer | None = None


def get_a2a_server() -> A2AServer:
    """Get or create global A2A server instance"""
    global _a2a_server
    if _a2a_server is None:
        _a2a_server = A2AServer()
    return _a2a_server
