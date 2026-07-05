"""Security Headers Middleware - Adds security headers to all HTTP responses."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        path = request.url.path

        # Skip iframe-blocking headers for the Traefik forward-auth endpoint.
        # Traefik returns the auth response (including headers) to the client
        # on 401.  If we set frame-ancestors 'none' on that response, the
        # browser silently blocks the sandbox preview iframe — producing a
        # blank page with no error.  Exempting this path lets the browser
        # render the 401 body (or the sandbox content on 200).
        is_forward_auth = path == "/api/sandbox/forward-auth"

        # Prevent clickjacking (skip for forward-auth to allow iframe embedding)
        if not is_forward_auth:
            response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS filter
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer sharing
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser feature access
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=(), "
            "accelerometer=()"
        )

        # Content Security Policy
        # Allow iframe embedding for the forward-auth endpoint so Traefik's
        # 401 response can be rendered inside the sandbox preview iframe.
        frame_ancestors = "'self' https://*.flowmanner.com" if is_forward_auth else "'none'"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            f"frame-ancestors {frame_ancestors}; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "object-src 'none'; "
            "upgrade-insecure-requests"
        )

        # HSTS
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response
