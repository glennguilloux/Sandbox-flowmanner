import logging
from datetime import UTC, datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class PipelineWSManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, pipeline_id: str) -> None:
        await websocket.accept()
        if pipeline_id not in self._connections:
            self._connections[pipeline_id] = set()
        self._connections[pipeline_id].add(websocket)

    def disconnect(self, websocket: WebSocket, pipeline_id: str) -> None:
        if pipeline_id in self._connections:
            self._connections[pipeline_id].discard(websocket)
            if not self._connections[pipeline_id]:
                del self._connections[pipeline_id]

    async def broadcast(self, pipeline_id: str, message: dict) -> None:
        if pipeline_id in self._connections:
            dead = set()
            for ws in self._connections[pipeline_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self.disconnect(ws, pipeline_id)

    async def send_event(self, pipeline_id: str, event_type: str, data: dict) -> None:
        if pipeline_id not in self._connections:
            return
        message = {
            "type": event_type,
            "pipeline_id": pipeline_id,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self.broadcast(pipeline_id, message)


ws_manager = PipelineWSManager()
