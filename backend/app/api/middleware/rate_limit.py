"""Global rate limiting middleware for non-auth API endpoints."""

import logging
import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limits all API endpoints by client IP."""

    LIMITS = {
        "/api/v1/chat": 30,
        "/api/v1/missions": 60,
        "/api/v1/agents": 60,
        "/api/v1/auth": 20,
        "/api/v1/llm": 30,
        "/api/v1/browser": 30,
    }
    DEFAULT_LIMIT = 100
    WINDOW_SECONDS = 60
    MAX_KEYS = 50000

    # Private/internal IP prefixes exempt from rate limiting (Docker, homelab, dev)
    _PRIVATE_NETS = (
        "127.",      # 127.0.0.0/8 – localhost
        "10.",       # 10.0.0.0/8 – private
        "192.168.",  # 192.168.0.0/16 – private
        "172.",      # 172.16.0.0/12 – private (Docker)
        "::1",        # IPv6 localhost
    )

    @classmethod
    def _is_private_ip(cls, ip: str) -> bool:
        if ip in ("127.0.0.1", "::1"):
            return True
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
                return 16 <= second <= 31
            except (ValueError, IndexError):
                return False
        return any(ip.startswith(prefix) for prefix in ("10.", "192.168."))

    def __init__(self, app):
        super().__init__(app)
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _get_limit(self, path: str) -> int:
        for prefix, limit in self.LIMITS.items():
            if path.startswith(prefix):
                return limit
        return self.DEFAULT_LIMIT

    def _cleanup(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.WINDOW_SECONDS
        with self._lock:
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]
            if len(self._windows) > self.MAX_KEYS:
                sorted_keys = sorted(
                    self._windows.keys(),
                    key=lambda k: self._windows[k][-1] if self._windows[k] else 0,
                )
                for old_key in sorted_keys[:len(self._windows) - self.MAX_KEYS]:
                    del self._windows[old_key]

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path in ("/api/health", "/api/v1/health"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if self._is_private_ip(client_ip):
            return await call_next(request)

        # Phase 8.2: Key by workspace_id when available, fall back to IP
        workspace_id = request.headers.get("X-Workspace-Id")
        key = f"ratelimit:ws:{workspace_id}" if workspace_id else f"ratelimit:{client_ip}"
        self._cleanup(key)
        limit = self._get_limit(request.url.path)

        with self._lock:
            current = len(self._windows[key])
            if current >= limit:
                oldest = self._windows[key][0]
                retry_after = int(oldest + self.WINDOW_SECONDS - time.monotonic()) + 1
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please slow down."},
                    headers={
                        "Retry-After": str(max(retry_after, 1)),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + self.WINDOW_SECONDS),
                    },
                )
            self._windows[key].append(time.monotonic())
            remaining = limit - current - 1

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + self.WINDOW_SECONDS)
        return response


def get_rate_limit_status() -> dict:
    return {
        "limits": dict(GlobalRateLimitMiddleware.LIMITS),
        "default_limit": GlobalRateLimitMiddleware.DEFAULT_LIMIT,
        "window_seconds": GlobalRateLimitMiddleware.WINDOW_SECONDS,
        "backend": "in_memory",
    }
