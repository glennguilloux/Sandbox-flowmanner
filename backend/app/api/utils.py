from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def get_device_name(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    return ua[:100] if ua else "Unknown"


def parse_browser(ua: str) -> str | None:
    if not ua:
        return None
    ua_lower = ua.lower()
    if "firefox" in ua_lower:
        return "Firefox"
    if "chrome" in ua_lower and "edg" not in ua_lower:
        return "Chrome"
    if "safari" in ua_lower and "chrome" not in ua_lower:
        return "Safari"
    if "edg" in ua_lower:
        return "Edge"
    return None


def parse_os(ua: str) -> str | None:
    if not ua:
        return None
    ua_lower = ua.lower()
    if "mac" in ua_lower:
        return "macOS"
    if "windows" in ua_lower:
        return "Windows"
    if "linux" in ua_lower:
        return "Linux"
    if "android" in ua_lower:
        return "Android"
    if "ios" in ua_lower or "iphone" in ua_lower:
        return "iOS"
    return None
