from __future__ import annotations

import ipaddress
import logging
import socket
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.models.byok_models import UserAPIKey
from app.schemas.byok import BYOKValidateRequest, BYOKValidateResponse, ModelInfo
from app.utils.encryption import validate_provider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

# ── SSRF protection ────────────────────────────────────────────────────────
# Default-deny: custom base_urls are only allowed when they resolve to a
# PUBLIC (globally routable) IP and use an http(s) scheme. Provider default
# base URLs are always allowed (see _PROVIDER_BASE_URLS).
_BLOCKED_SCHEMES = frozenset({"file", "ftp", "data", "javascript", "gopher", "dict"})
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "0.0.0.0",
        "::1",
        "127.0.0.1",
        "::",
        "169.254.169.254",
    }
)
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",  # link-local / cloud metadata
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::1/128",
        "::/128",
        "fc00::/7",  # IPv6 ULA
        "fe80::/10",  # IPv6 link-local
        "ff00::/8",  # IPv6 multicast
    )
)

# Per-user API-key quota. Mirrors byok.py's "one active key per provider"
# intent by bounding total stored keys a single user can create. Tune here.
MAX_USER_API_KEYS = 20


def _is_safe_outbound_url(url: str) -> tuple[bool, str | None]:
    """Validate a custom base_url against SSRF rules (default-deny).

    Returns (ok, error). The destination must use http/https, must not be a
    blocked hostname, and — critically — must RESOLVE to a publicly routable
    IP address. This blocks private/loopback/link-local/metadata ranges and
    guards against DNS-rebinding by validating the resolved IP, not just the
    literal host (and by pinning the resolved IP via the httpx client in the
    caller).
    """
    if not url:
        return False, "base_url is required"
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        return False, f"Invalid base_url: {exc}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"base_url scheme '{scheme}://' is not allowed (http/https only)"
    if scheme in _BLOCKED_SCHEMES:
        return False, f"base_url scheme '{scheme}://' is blocked"

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "base_url has no valid hostname"
    if hostname in _BLOCKED_HOSTNAMES:
        return False, f"base_url host '{hostname}' is blocked"

    # Reject a literal private/loopback/link-local IP.
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # Not a literal IP — resolve it below.
        pass
    else:
        if not addr.is_global or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            return False, f"base_url host '{hostname}' is not a public address"
        return True, None

    # Hostname: resolve and reject names that point at non-public ranges.
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        return False, f"base_url host '{hostname}' could not be resolved: {exc}"

    if not infos:
        return False, f"base_url host '{hostname}' resolved to no addresses"

    for family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            resolved = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"base_url host '{hostname}' resolved to an invalid address '{ip_str}'"
        if not resolved.is_global or resolved.is_loopback or resolved.is_link_local or resolved.is_reserved or resolved.is_multicast:
            return False, (
                f"base_url host '{hostname}' resolves to a non-public address '{ip_str}'"
            )
    return True, None


class _PinnedNetworkBackend:
    """Wrap an httpcore network backend to pin the connect-time IP.

    Stops DNS-rebinding: the caller resolves ``host`` once (and verifies it is
    public), then we force every TCP connect for this request to that pinned IP
    while leaving the original hostname in place for TLS SNI / HTTP Host.
    """

    def __init__(self, backend: object, pin_ip: str) -> None:
        self._backend = backend
        self._pin_ip = pin_ip

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        return await self._backend.connect_tcp(self._pin_ip, port, timeout, local_address, socket_options)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        return await self._backend.connect_unix_socket(path, timeout, socket_options)

    async def sleep(self, seconds):
        return await self._backend.sleep(seconds)


def _mask_key(encrypted: str) -> str:
    """Return a masked representation of an encrypted key for display."""
    if len(encrypted) <= 8:
        return "****"
    return f"{encrypted[:4]}...{encrypted[-4:]}"


user_keys_router = APIRouter(prefix="/user/keys", tags=["user-keys"])

# In-module cache: {provider_key: (timestamp, List[ModelInfo])}
_model_cache: dict[str, tuple[float, list[ModelInfo]]] = {}
_CACHE_TTL = 300  # 5 minutes

_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

_NON_CHAT_KEYWORDS = ("embedding", "whisper", "dall-e", "tts", "moderation")


def _is_chat_model(model_id: str) -> bool:
    lower_id = model_id.lower()
    return not any(kw in lower_id for kw in _NON_CHAT_KEYWORDS)


def _get_base_url(provider: str, base_url: str | None = None) -> str:
    if base_url:
        return base_url.rstrip("/")
    return _PROVIDER_BASE_URLS.get(provider.lower(), _PROVIDER_BASE_URLS["openai"])


_MODEL_CATALOG: dict[str, list[dict]] = {
    "openai": [
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "provider": "openai",
            "context_window": 128000,
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "provider": "openai",
            "context_window": 128000,
        },
        {
            "id": "gpt-4-turbo",
            "name": "GPT-4 Turbo",
            "provider": "openai",
            "context_window": 128000,
        },
        {
            "id": "gpt-3.5-turbo",
            "name": "GPT-3.5 Turbo",
            "provider": "openai",
            "context_window": 16385,
        },
    ],
    "openai-compatible": [
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "provider": "openai-compatible",
            "context_window": 128000,
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "provider": "openai-compatible",
            "context_window": 128000,
        },
        {
            "id": "gpt-4-turbo",
            "name": "GPT-4 Turbo",
            "provider": "openai-compatible",
            "context_window": 128000,
        },
        {
            "id": "gpt-3.5-turbo",
            "name": "GPT-3.5 Turbo",
            "provider": "openai-compatible",
            "context_window": 16385,
        },
    ],
}

_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"


@router.post("/validate", response_model=BYOKValidateResponse)
async def validate_api_key(request: BYOKValidateRequest) -> BYOKValidateResponse:
    provider = request.provider.lower()
    api_key = request.api_key

    if provider not in ("openai", "openai-compatible"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {provider}. Only 'openai' and 'openai-compatible' are supported.",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _OPENAI_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.TimeoutException:
        return BYOKValidateResponse(
            status="invalid",
            models=[],
            error="Request timed out while validating API key",
        )
    except httpx.RequestError as exc:
        logger.warning("HTTP request error during BYOK validation: %s", exc)
        return BYOKValidateResponse(
            status="invalid",
            models=[],
            error=f"Network error: {exc}",
        )

    if response.status_code in (401, 403):
        error_detail = "Invalid API key"
        try:
            body = response.json()
            error_detail = body.get("error", {}).get("message", error_detail)
        except Exception:
            logger.debug("byok_error_body_parse_failed", exc_info=True)
        return BYOKValidateResponse(status="invalid", models=[], error=error_detail)

    if not response.is_success:
        logger.warning(
            "Unexpected status %s from provider during BYOK validation",
            response.status_code,
        )
        return BYOKValidateResponse(
            status="invalid",
            models=[],
            error=f"Provider returned HTTP {response.status_code}",
        )

    models: list[ModelInfo] = []
    try:
        data = response.json()
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if model_id:
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_id,
                        provider=provider,
                        context_window=None,
                    )
                )
    except Exception as exc:
        logger.warning("Failed to parse models from provider response: %s", exc)
        return BYOKValidateResponse(status="valid", models=[], error=None)

    return BYOKValidateResponse(status="valid", models=models, error=None)


@router.get("/models/{provider}", response_model=list[ModelInfo])
async def get_provider_models(provider: str) -> list[ModelInfo]:
    catalog = _MODEL_CATALOG.get(provider.lower())
    if catalog is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No model catalog found for provider: {provider}",
        )
    return [
        ModelInfo(
            id=m["id"],
            name=m["name"],
            provider=m["provider"],
            context_window=m.get("context_window"),
        )
        for m in catalog
    ]


@router.post("/discover-models", response_model=list[ModelInfo])
async def discover_models(request: BYOKValidateRequest) -> list[ModelInfo]:
    provider = request.provider.lower()
    cache_key = provider
    if cache_key in _model_cache:
        ts, models = _model_cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return models

    base_url = _get_base_url(provider)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {request.api_key}"},
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timed out while fetching models",
        )
    except httpx.RequestError as exc:
        logger.warning("HTTP request error during model discovery: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Network error: {exc}",
        )

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if not response.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider returned HTTP {response.status_code}",
        )

    filtered_models: list[ModelInfo] = []
    try:
        data = response.json()
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if model_id and _is_chat_model(model_id):
                filtered_models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_id,
                        provider=provider,
                        context_window=None,
                    )
                )
    except Exception as exc:
        logger.warning("Failed to parse models from provider response: %s", exc)
        return []

    _model_cache[cache_key] = (time.time(), filtered_models)
    return filtered_models


@router.get("")
async def list_keys(
    user=Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(UserAPIKey).where(UserAPIKey.user_id == user.id)
    if workspace_id:
        query = query.where((UserAPIKey.workspace_id == workspace_id) | (UserAPIKey.workspace_id.is_(None)))
    query = query.order_by(UserAPIKey.id)
    result = await db.execute(query)
    keys = result.scalars().all()
    return {
        "keys": [
            {
                "id": k.id,
                "provider": k.provider,
                "key_name": k.key_label or k.provider,
                "masked_key": _mask_key(k.encrypted_key),
                "base_url": k.base_url,
                "is_active": k.is_active,
                "models": k.get_models_list(),
                "created_at": k.created_at.isoformat() if k.created_at else "",
                "last_used_at": None,
            }
            for k in keys
        ]
    }


@router.post("")
async def add_key(
    data: dict,
    user=Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    from app.utils.encryption import encrypt_api_key

    api_key = data.get("api_key") or data.get("key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    provider = (data.get("provider") or "openai").lower()
    if not validate_provider(provider):
        logger.warning("api_keys add_key: unsupported provider=%s user=%s", provider, user.id)
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    base_url = data.get("base_url")
    if base_url:
        ok, err = _is_safe_outbound_url(base_url)
        if not ok:
            logger.warning("api_keys add_key: unsafe base_url rejected user=%s url=%s err=%s", user.id, base_url, err)
            raise HTTPException(status_code=400, detail=f"Invalid base_url: {err}")

    # Enforce per-user API-key quota (consistent with byok.py's constraints).
    existing = await db.execute(
        select(func.count()).select_from(UserAPIKey).where(UserAPIKey.user_id == user.id)
    )
    if (existing.scalar_one() or 0) >= MAX_USER_API_KEYS:
        logger.warning("api_keys add_key: quota exceeded user=%s", user.id)
        raise HTTPException(
            status_code=429,
            detail=f"API key limit reached (max {MAX_USER_API_KEYS} per user).",
        )

    encrypted = encrypt_api_key(api_key)
    db_key = UserAPIKey(
        user_id=user.id,
        workspace_id=workspace_id,
        provider=provider,
        encrypted_key=encrypted,
        key_label=data.get("key_name") or data.get("label"),
        base_url=base_url,
        is_active=True,
    )
    db.add(db_key)
    await db.flush()
    await db.refresh(db_key)
    return {
        "key": {
            "id": db_key.id,
            "provider": db_key.provider,
            "key_name": db_key.key_label or db_key.provider,
            "masked_key": _mask_key(db_key.encrypted_key),
            "base_url": db_key.base_url,
            "is_active": db_key.is_active,
            "models": db_key.get_models_list(),
            "created_at": db_key.created_at.isoformat() if db_key.created_at else "",
            "last_used_at": None,
        }
    }


@router.delete("/{key_id}")
async def delete_key(
    key_id: int,
    user=Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(UserAPIKey).where(UserAPIKey.id == key_id, UserAPIKey.user_id == user.id)
    if workspace_id:
        query = query.where((UserAPIKey.workspace_id == workspace_id) | (UserAPIKey.workspace_id.is_(None)))
    result = await db.execute(query)
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    await db.delete(key)
    return {"detail": "Deleted"}


@router.post("/{key_id}/test")
async def test_key(
    key_id: int,
    user=Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(UserAPIKey).where(UserAPIKey.id == key_id, UserAPIKey.user_id == user.id)
    if workspace_id:
        query = query.where((UserAPIKey.workspace_id == workspace_id) | (UserAPIKey.workspace_id.is_(None)))
    result = await db.execute(query)
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    # Test the key by calling the provider's models endpoint.
    # Guard against stored SSRF: a custom base_url must have passed write-time
    # validation, but re-validate defensively and never follow redirects into
    # private ranges. We resolve + pin the target IP so a DNS-rebinding response
    # cannot redirect the credented request to an internal host.
    api_key = key.get_api_key()
    requested_base_url = key.base_url or _PROVIDER_BASE_URLS.get(key.provider.lower(), _PROVIDER_BASE_URLS["openai"])
    ok, err = _is_safe_outbound_url(requested_base_url)
    if not ok:
        logger.warning("api_keys test_key: unsafe stored base_url user=%s key=%s err=%s", user.id, key_id, err)
        return {
            "provider": key.provider,
            "key_name": key.key_label,
            "valid": False,
            "message": f"Refusing to test: {err}",
        }

    parsed = urlparse(requested_base_url)
    # Re-resolve and re-check the resolved IP right before the request. This
    # limits DNS-rebinding: even if the stored value was safe at write time, a
    # rebind to a non-public address here is refused (fail-closed).
    target_ip: str | None = None
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
        for _family, _type, _proto, _canon, sockaddr in infos:
            try:
                resolved = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if not resolved.is_global or resolved.is_loopback or resolved.is_link_local or resolved.is_reserved or resolved.is_multicast:
                logger.warning("api_keys test_key: base_url %s resolved to non-public %s", requested_base_url, sockaddr[0])
                return {
                    "provider": key.provider,
                    "key_name": key.key_label,
                    "valid": False,
                    "message": f"Refusing to test: base_url resolves to a non-public address {sockaddr[0]}",
                }
        target_ip = infos[0][4][0] if infos else None
    except (socket.gaierror, UnicodeError, OSError, IndexError):
        # If we can't resolve, fall back to the scheme/host checks already done.
        target_ip = None

    try:
        # follow_redirects=False => a redirect to a private/loopback host cannot
        # leak the user's Authorization header. Combined with the write-time and
        # pre-request IP checks above, this closes the stored-SSRF + credential-
        # exfiltration vector (R-8).
        client = httpx.AsyncClient(timeout=10.0, follow_redirects=False)
        # Pin the resolved IP so a second (rebind) DNS lookup at connect time
        # cannot re-point the credentialed request at an internal host. The
        # connection still uses the URL's hostname for TLS SNI / Host header.
        if target_ip:
            client._transport._pool._network_backend = _PinnedNetworkBackend(
                client._transport._pool._network_backend, target_ip
            )
        async with client:
            resp = await client.get(
                f"{requested_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code in (401, 403):
            return {
                "provider": key.provider,
                "key_name": key.key_label,
                "valid": False,
                "message": "Invalid API key",
            }
        if resp.is_success:
            return {
                "provider": key.provider,
                "key_name": key.key_label,
                "valid": True,
                "message": "Key is valid",
            }
        return {
            "provider": key.provider,
            "key_name": key.key_label,
            "valid": False,
            "message": f"HTTP {resp.status_code}",
        }
    except Exception as e:
        return {
            "provider": key.provider,
            "key_name": key.key_label,
            "valid": False,
            "message": str(e),
        }


@user_keys_router.get("")
async def user_list_keys(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_keys(user=user, db=db)


@user_keys_router.post("")
async def user_add_key(
    data: dict,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await add_key(data=data, user=user, db=db)


@user_keys_router.delete("/{key_id}")
async def user_delete_key(
    key_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_key(key_id=key_id, user=user, db=db)


@user_keys_router.post("/{key_id}/test")
async def user_test_key(
    key_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await test_key(key_id=key_id, user=user, db=db)
