import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Minimum viable: 1 active session + 1 headroom for a concurrent run.
# Each session is a full headless Chromium (~300-500 MB RSS), so we keep
# this low to stay within the backend container's 4g mem_limit.
MAX_SESSIONS = 2


class SessionCapacityError(Exception):
    pass


class BrowserManager:
    _instance = None
    _sessions: dict[str, Any] = {}
    _user_sessions: dict[str, str] = {}
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._sessions = {}
            cls._user_sessions = {}
            cls._lock = asyncio.Lock()
        return cls._instance

    @property
    def active_count(self) -> int:
        count = 0
        for session in self._sessions.values():
            if session.is_active():
                count += 1
        return count

    @property
    def is_full(self) -> bool:
        return self.active_count >= MAX_SESSIONS

    async def get_or_create_session(self, user_id: str) -> Any:
        async with self._lock:
            existing = self._user_sessions.get(user_id)
            if existing and existing in self._sessions:
                session = self._sessions[existing]
                if session.is_active():
                    return session
                else:
                    del self._user_sessions[user_id]

            if self.is_full:
                raise SessionCapacityError(f"Browser session capacity reached ({MAX_SESSIONS} max)")

            from app.services.browser_session import BrowserSession

            session_id = str(uuid.uuid4())
            session = BrowserSession(session_id=session_id, user_id=user_id)
            session.on_timeout_callback = self._handle_session_timeout

            await session.start(on_timeout_callback=self._handle_session_timeout)

            self._sessions[session_id] = session
            self._user_sessions[user_id] = session_id

            logger.info("Created browser session %s for user %s", session_id, user_id)
            return session

    def get_session(self, session_id: str) -> Any:
        return self._sessions.get(session_id)

    def get_user_session(self, user_id: str) -> Any:
        session_id = self._user_sessions.get(user_id)
        if session_id:
            return self._sessions.get(session_id)
        return None

    async def close_session(self, session_id: str):
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                await session.close()
                user_id = session.user_id
                if self._user_sessions.get(user_id) == session_id:
                    del self._user_sessions[user_id]
                del self._sessions[session_id]
                logger.info("Closed browser session %s", session_id)

    async def close_user_session(self, user_id: str):
        session_id = self._user_sessions.get(user_id)
        if session_id:
            await self.close_session(session_id)

    async def close_all_sessions(self):
        async with self._lock:
            for session in list(self._sessions.values()):
                await session.close()
            self._sessions.clear()
            self._user_sessions.clear()
            logger.info("All browser sessions closed")

    def get_stats(self) -> dict[str, Any]:
        return {
            "max_sessions": MAX_SESSIONS,
            "active_sessions": self.active_count,
            "available_slots": MAX_SESSIONS - self.active_count,
            "total_sessions": len(self._sessions),
        }

    async def _handle_session_timeout(self, session_id: str):
        logger.info("Session %s timed out, cleaning up", session_id)
        await self._cleanup_timed_out_session(session_id)

    async def _cleanup_timed_out_session(self, session_id: str):
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                try:
                    await session.close()
                except Exception as e:
                    logger.warning("Error closing timed out session %s: %s", session_id, e)
                user_id = session.user_id
                if self._user_sessions.get(user_id) == session_id:
                    del self._user_sessions[user_id]
                if session_id in self._sessions:
                    del self._sessions[session_id]
                logger.info("Cleaned up timed out session %s", session_id)

    async def cleanup_on_startup(self):
        logger.info("Cleaning up orphan Chromium processes on startup")
        import subprocess

        try:
            result = subprocess.run(
                ["pkill", "-f", "chromium"],
                capture_output=True,
            )
            if result.returncode == 0:
                logger.info("Killed orphan Chromium processes")
        except Exception as e:
            logger.debug("No orphan Chromium to clean up: %s", e)


_browser_manager_instance = None


def get_browser_manager() -> BrowserManager:
    global _browser_manager_instance
    if _browser_manager_instance is None:
        _browser_manager_instance = BrowserManager()
    return _browser_manager_instance
