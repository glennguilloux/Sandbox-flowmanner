"""Regression tests for app/api/middleware/rate_limit.py.

Proves remediation of three defects that left the global rate limiter
effectively OFF in production (P0 SEC card t_14b485a1):

* R-1  Prefix mismatch -- LIMITS keys must match REAL mounted paths.
* R-2  Proxy exemption + no X-Forwarded-For -- client IP must be resolved
       from a TRUSTED proxy chain, and XFF must NOT be spoofable.
* R-3  Spoofable bucket key -- buckets must key on a verified identity /
       resolved client IP, never the client-supplied X-Workspace-Id header.

These tests assert behavior that FAILS against the pre-fix code and PASSES
after the fix:

  R-1  /api/chat returns 429 only after its real cap (30), not after 100.
  R-2  A public client behind a trusted proxy IS throttled (not exempt);
       a direct client spoofing XFF: 127.0.0.1 cannot claim exemption;
       spoofing XFF: 127.0.0.1 *through* a trusted proxy still gets limited.
  R-3  Rotating X-Workspace-Id yields no fresh bucket; a verified Bearer
       token shares one bucket across different source IPs.

NOTE: use GENUINELY public IPs (e.g. 23.45.x.x). Python's ``ipaddress``
treats the RFC-5737 documentation ranges (203.0.113.0/24, 198.51.100.0/24)
as private, which would skew these tests.
"""

from unittest.mock import MagicMock

import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse

# Force the full SQLAlchemy model graph to register BEFORE the middleware
# lazily imports app.services.auth_service inside _resolve_principal. In
# production the app loads app.models at startup, so the auth_service <->
# app.models circular edge (RefreshToken) is already resolved before any
# request reaches the middleware. In an isolated test process the Bearer-token
# path would otherwise be the FIRST importer and hit a partial-init ImportError.
import app.models  # noqa: F401  (import-order side effect, mirrors app startup)
from app.api.middleware.rate_limit import GlobalRateLimitMiddleware
from app.config import settings

# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_request(path: str, client_host: str = "23.45.67.1", headers: dict | None = None):
    req = MagicMock(spec=Request)
    req.url.path = path
    client = MagicMock()
    client.host = client_host
    req.client = client
    req.headers = headers or {}
    return req


async def _dispatch(
    mw: GlobalRateLimitMiddleware, path: str, client_host: str = "23.45.67.1", headers: dict | None = None
):
    """Dispatch one request through the middleware; return (response, calls)."""
    req = _make_request(path, client_host, headers)
    state = {"calls": 0}

    async def call_next(request):
        state["calls"] += 1
        return JSONResponse(content={"ok": True}, status_code=200)

    resp = await mw.dispatch(req, call_next)
    return resp, state["calls"]


def _make_mw() -> GlobalRateLimitMiddleware:
    # Fresh instance == fresh in-memory windows (buckets reset between tests).
    return GlobalRateLimitMiddleware(app=MagicMock())


def _valid_bearer(sub: str = "42") -> str:
    return jwt.encode({"sub": sub, "type": "access"}, settings.JWT_SECRET_KEY, algorithm="HS256")


# ── R-1: prefix match against REAL mounted paths ────────────────────────────


class TestR1PrefixMatch:
    async def test_chat_uses_real_cap_not_default(self):
        """/api/chat is mounted at /api/chat (not /api/v1/chat). Cap 30 applies."""
        mw = _make_mw()
        assert mw._get_limit("/api/chat") == 30  # sanity: real cap, not DEFAULT 100

        for _ in range(30):
            resp, _ = await _dispatch(mw, "/api/chat")
            assert resp.status_code == 200
        # 31st request must be throttled at the REAL cap (pre-fix used 100).
        resp, _ = await _dispatch(mw, "/api/chat")
        assert resp.status_code == 429

    async def test_missions_uses_real_cap(self):
        mw = _make_mw()
        assert mw._get_limit("/api/missions") == 60
        for _ in range(60):
            resp, _ = await _dispatch(mw, "/api/missions")
            assert resp.status_code == 200
        resp, _ = await _dispatch(mw, "/api/missions")
        assert resp.status_code == 429

    async def test_llm_router_uses_ai_mount(self):
        """llm router is remounted at /api/ai (see app/api/v1/__init__.py)."""
        mw = _make_mw()
        assert mw._get_limit("/api/ai/models") == 30

    async def test_playground_sandboxes_uses_real_cap(self):
        mw = _make_mw()
        assert mw._get_limit("/api/playground/sandboxes") == 5
        for _ in range(5):
            resp, _ = await _dispatch(mw, "/api/playground/sandboxes")
            assert resp.status_code == 200
        resp, _ = await _dispatch(mw, "/api/playground/sandboxes")
        assert resp.status_code == 429

    async def test_v1_prefix_normalized_to_api(self):
        """Future-proof: a /api/v1/ mount maps onto the same caps."""
        mw = _make_mw()
        assert mw._get_limit("/api/v1/chat") == 30
        for _ in range(30):
            resp, _ = await _dispatch(mw, "/api/v1/chat")
            assert resp.status_code == 200
        resp, _ = await _dispatch(mw, "/api/v1/chat")
        assert resp.status_code == 429


# ── R-2: trusted-proxy-aware client IP resolution ───────────────────────────


class TestR2ProxyIp:
    async def test_public_client_behind_trusted_proxy_is_throttled(self):
        """Peer is a trusted private proxy; XFF carries the public client.
        The limiter must apply to the PUBLIC client, not exempt it."""
        mw = _make_mw()
        cap = mw._get_limit("/api/chat")
        for _ in range(cap):
            resp, _ = await _dispatch(
                mw,
                "/api/chat",
                client_host="10.99.0.1",
                headers={"X-Forwarded-For": "23.45.67.1"},
            )
            assert resp.status_code == 200
        # Exceeding the cap from the public client -> 429 (pre-fix: exempted).
        resp, _ = await _dispatch(
            mw,
            "/api/chat",
            client_host="10.99.0.1",
            headers={"X-Forwarded-For": "23.45.67.1"},
        )
        assert resp.status_code == 429

    async def test_direct_client_cannot_spoof_ip_via_xff(self):
        """Peer is a PUBLIC (untrusted) host claiming XFF: 127.0.0.1.
        XFF must be ignored; the client keeps its real (public) IP and is
        throttled on that bucket, NOT the spoofed 127.0.0.1 bucket."""
        mw = _make_mw()
        cap = mw._get_limit("/api/chat")
        for _ in range(cap):
            resp, _ = await _dispatch(
                mw,
                "/api/chat",
                client_host="23.45.67.99",
                headers={"X-Forwarded-For": "127.0.0.1"},
            )
            assert resp.status_code == 200
        # The 127.0.0.1 spoof did NOT create a fresh/exempt bucket.
        resp, _ = await _dispatch(
            mw,
            "/api/chat",
            client_host="23.45.67.99",
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
        assert resp.status_code == 429

    async def test_spoofed_xff_127_via_trusted_proxy_not_exempt(self):
        """Closing the hole: attacker sends XFF: 127.0.0.1 THROUGH the trusted
        proxy. Even though fully-trusted, the client must remain throttled
        (we never exempt once XFF was honored)."""
        mw = _make_mw()
        cap = mw._get_limit("/api/chat")
        for _ in range(cap):
            resp, _ = await _dispatch(
                mw,
                "/api/chat",
                client_host="10.99.0.1",
                headers={"X-Forwarded-For": "127.0.0.1"},
            )
            assert resp.status_code == 200
        resp, _ = await _dispatch(
            mw,
            "/api/chat",
            client_host="10.99.0.1",
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
        assert resp.status_code == 429

    async def test_internal_direct_connection_still_exempt(self):
        """Direct internal (private peer, no XFF) remains exempt -- dev/Docker."""
        mw = _make_mw()
        for _ in range(200):
            resp, calls = await _dispatch(mw, "/api/chat", client_host="192.168.1.5", headers={})
            assert resp.status_code == 200
            assert calls == 1  # call_next reached -> not throttled


# ── R-3: non-spoofable bucket partition key ─────────────────────────────────


class TestR3BucketKey:
    async def test_rotating_workspace_id_grants_no_fresh_bucket(self):
        """Same IP, no auth, a NEW X-Workspace-Id each request. The header must
        be ignored, so all requests share ONE IP bucket and get throttled."""
        mw = _make_mw()
        cap = mw._get_limit("/api/chat")
        for i in range(cap):
            resp, _ = await _dispatch(
                mw,
                "/api/chat",
                client_host="23.45.67.50",
                headers={"X-Workspace-Id": f"ws-{i}"},
            )
            assert resp.status_code == 200
        resp, _ = await _dispatch(
            mw,
            "/api/chat",
            client_host="23.45.67.50",
            headers={"X-Workspace-Id": "ws-brand-new"},
        )
        assert resp.status_code == 429  # header ignored -> shared IP bucket

    async def test_verified_principal_shared_across_ips(self):
        """A verified Bearer token shares ONE bucket regardless of source IP."""
        mw = _make_mw()
        token = _valid_bearer("42")
        cap = mw._get_limit("/api/chat")
        for i in range(cap):
            resp, _ = await _dispatch(
                mw,
                "/api/chat",
                client_host=f"23.45.{i}.1",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
        # Different IP but same verified user -> same bucket -> throttled.
        resp, _ = await _dispatch(
            mw,
            "/api/chat",
            client_host="185.199.108.1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 429

    async def test_distinct_principals_get_distinct_buckets(self):
        """Two different verified users are throttled independently."""
        mw = _make_mw()
        cap = mw._get_limit("/api/chat")
        for _ in range(cap):
            resp, _ = await _dispatch(
                mw,
                "/api/chat",
                client_host="23.45.67.1",
                headers={"Authorization": f"Bearer {_valid_bearer('1')}"},
            )
            assert resp.status_code == 200
        # User 2 from the same IP still has a fresh bucket.
        resp, _ = await _dispatch(
            mw,
            "/api/chat",
            client_host="23.45.67.1",
            headers={"Authorization": f"Bearer {_valid_bearer('2')}"},
        )
        assert resp.status_code == 200
