"""Global rate limiting middleware for non-auth API endpoints.

Security model (post R-1 / R-2 / R-3 remediation, 2026-07-13):

* R-1 Prefix match -- ``LIMITS`` keys use the REAL mounted paths
  (``/api/chat``, ``/api/missions``, ``/api/ai`` for the LLM router, etc.).
  A normalization step maps a future ``/api/v1/...`` mount onto the same keys
  so a prefix change cannot silently disable the caps.

* R-2 Trusted-proxy-aware client IP -- behind the VPS Nginx -> WireGuard ->
  homelab proxy, ``request.client.host`` is ALWAYS a private proxy IP. We
  only trust ``X-Forwarded-For`` when the immediate TCP peer is a known
  trusted proxy (configured via ``RATE_LIMIT_TRUSTED_PROXIES``), and we take
  the leftmost *untrusted* hop (nginx ``real_ip_recursive`` semantics). A
  client connecting directly cannot spoof its IP via XFF. Internal (direct,
  no-XFF) connections from private addresses remain exempt.

  NOTE: ``app/api/utils.py:get_client_ip`` is intentionally NOT reused here --
  it blindly returns the first XFF hop, which is spoofable and would let any
  client forge its client IP for the limiter.

* R-3 Non-spoofable partition key -- buckets are keyed on the verified
  authenticated principal (JWT ``sub``) when a valid Bearer token is present,
  otherwise on the resolved client IP. The client-supplied ``X-Workspace-Id``
  header is NEVER used as a throttle partition (it was trivially rotatable to
  obtain a fresh bucket per request).
"""

import ipaddress
import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limits all API endpoints by verified client identity / IP."""

    # Keys use the REAL mounted paths (verified against
    # app/api/v1/__init__.py router includes + each router's prefix):
    #   chat      -> /api/chat
    #   missions  -> /api/missions
    #   agents    -> /api/agents
    #   auth      -> /api/auth
    #   llm       -> /api/ai        (llm router remounted at /ai in __init__.py)
    #   browser   -> /api/browser
    #   playground-> /api/playground/sandboxes (+ /claim)
    LIMITS = {
        "/api/chat": 30,
        "/api/missions": 60,
        "/api/agents": 60,
        "/api/auth": 20,
        "/api/ai": 30,
        "/api/browser": 30,
        # Phase 4: Playground (anonymous users -> IP-based)
        "/api/playground/sandboxes": 5,
        "/api/playground/sandboxes/claim": 10,
    }
    DEFAULT_LIMIT = 100
    WINDOW_SECONDS = 60
    MAX_KEYS = 50000

    def __init__(self, app):
        super().__init__(app)
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()
        self._trusted_nets = self._parse_trusted(settings.RATE_LIMIT_TRUSTED_PROXIES)

    # ── Config: trusted proxy CIDRs ─────────────────────────────────────────

    @staticmethod
    def _parse_trusted(raw: str) -> list:
        nets: list = []
        for item in (raw or "").split(","):
            item = item.strip()
            if not item:
                continue
            try:
                nets.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                # Not a CIDR/IP (e.g. a hostname) -- ignore.
                continue
        return nets

    def _ip_in_trusted(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in self._trusted_nets)

    @staticmethod
    def _is_private_ip(ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip).is_private
        except ValueError:
            return False

    # ── R-2: trusted-proxy-aware client IP resolution ───────────────────────

    def _resolve_client_ip(self, request: Request) -> tuple[str, bool]:
        """Return ``(resolved_client_ip, xff_was_honored)``.

        If the immediate TCP peer is a trusted proxy and an ``X-Forwarded-For``
        header is present, walk the chain right-to-left and return the first
        (leftmost) hop that is NOT a trusted proxy -- i.e. the real client
        (nginx ``real_ip_recursive on`` semantics). Otherwise the peer's own
        address is authoritative and XFF is treated as spoofable/untrusted.
        """
        raw_peer = request.client.host if request.client else "unknown"
        xff = request.headers.get("X-Forwarded-For")
        if not (xff and self._ip_in_trusted(raw_peer)):
            # Peer is not a trusted proxy (or no XFF) -> XFF is untrusted.
            return raw_peer, False
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        for hop in reversed(hops):
            if not self._ip_in_trusted(hop):
                return hop, True
        # Entire chain is trusted infra (e.g. internal service mesh) ->
        # fall back to the hop closest to us.
        return hops[-1] if hops else raw_peer, True

    # ── R-3: verified principal resolution (no DB, decode-only) ─────────────

    @staticmethod
    def _resolve_principal(request: Request) -> str | None:
        """Return a stable, verified principal id from a Bearer token.

        Decodes the JWT without touching the DB. Both decoders return ``None``
        on any failure, so an invalid/expired/missing token yields no principal
        and we fall back to IP-based keying. The client-supplied
        ``X-Workspace-Id`` header is intentionally NOT used as a partition key
        (it was trivially rotatable -> a fresh bucket per request).
        """
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[len("Bearer ") :]
        # Lazy import: avoids import-time coupling with auth services.
        from app.services.auth_service import decode_access_token as v1_decode_access_token
        from app.services.auth_v3_service import decode_access_token as v3_decode_access_token

        payload = v3_decode_access_token(token)
        if payload and payload.get("sub") is not None:
            return f"u:{payload['sub']}"
        uid = v1_decode_access_token(token)
        if uid is not None:
            return f"u:{uid}"
        return None

    # ── R-1: robust limit lookup against real mounted paths ─────────────────

    @staticmethod
    def _normalize_path(path: str) -> str:
        # Future-proof: if v1 is ever remounted under /api/v1, map it onto the
        # same keys so the caps don't silently turn off.
        if path.startswith("/api/v1/"):
            return "/api/" + path[len("/api/v1/") :]
        return path

    def _get_limit(self, path: str) -> int:
        norm = self._normalize_path(path)
        for prefix, limit in self.LIMITS.items():
            if norm == prefix or norm.startswith(prefix + "/"):
                return limit
        return self.DEFAULT_LIMIT

    # ── window bookkeeping ──────────────────────────────────────────────────

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
                for old_key in sorted_keys[: len(self._windows) - self.MAX_KEYS]:
                    del self._windows[old_key]

    # ── dispatch ────────────────────────────────────────────────────────────

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        if path in ("/api/health", "/api/v1/health"):
            return await call_next(request)

        client_ip, xff_honored = self._resolve_client_ip(request)
        # Exempt only DIRECT internal connections (private peer, no trusted
        # proxy rewrite). If XFF was honored the client is external -> never
        # exempt, closing the "spoof XFF: 127.0.0.1 via trusted proxy" hole.
        if not xff_honored and self._is_private_ip(client_ip):
            return await call_next(request)

        principal = self._resolve_principal(request)
        key = f"ratelimit:user:{principal}" if principal else f"ratelimit:ip:{client_ip}"

        self._cleanup(key)
        limit = self._get_limit(path)

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
