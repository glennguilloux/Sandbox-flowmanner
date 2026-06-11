"""
Base Connector Framework

Provides abstract base class for all external API connectors with:
- Authentication handling (API key, OAuth2, Basic Auth, Bearer Token)
- Rate limiting with configurable strategies
- Error handling with retries and exponential backoff
- Response parsing and validation
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import aiohttp
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class AuthType(str, Enum):
    """Supported authentication types"""

    NONE = "none"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    OAUTH2 = "oauth2"
    CUSTOM = "custom"


class ConnectorStatus(str, Enum):
    """Connector operational status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    AUTH_EXPIRED = "auth_expired"


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""

    requests_per_second: float = 10.0
    requests_per_minute: int = 600
    requests_per_hour: int = 36000
    burst_size: int = 20
    retry_after_header: str = "Retry-After"


@dataclass
class RetryConfig:
    """Retry configuration for failed requests"""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retry_on_status_codes: list[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])


class ConnectorConfig(BaseModel):
    """Base configuration for a connector"""

    name: str
    connector_type: str
    base_url: str | None = None
    auth_type: AuthType = AuthType.NONE
    auth_config: dict[str, Any] = Field(default_factory=dict)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    timeout: float = 30.0
    verify_ssl: bool = True
    headers: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ConnectorError(Exception):
    """Base exception for connector errors"""

    def __init__(
        self,
        message: str,
        connector_name: str,
        status_code: int | None = None,
        response_data: dict | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.connector_name = connector_name
        self.status_code = status_code
        self.response_data = response_data or {}
        self.retry_after = retry_after


class RateLimitError(ConnectorError):
    """Rate limit exceeded error"""

    pass


class AuthenticationError(ConnectorError):
    """Authentication failed error"""

    pass


# Alias for backwards compatibility
RateLimitExceeded = RateLimitError


class ConnectorResponse(BaseModel):
    """Standardized connector response"""

    success: bool
    data: Any = None
    error: str | None = None
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    response_time_ms: float = 0.0
    rate_limit_remaining: int | None = None
    rate_limit_reset: datetime | None = None


class RateLimiter:
    """Token bucket rate limiter with sliding window"""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._tokens = float(config.burst_size)
        self._last_update = time.monotonic()
        self._minute_requests: list[float] = []
        self._hour_requests: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> tuple[bool, float | None]:
        """Acquire a token, returns (success, wait_time_if_failed)"""
        async with self._lock:
            now = time.monotonic()

            # Refill tokens based on per-second rate
            elapsed = now - self._last_update
            self._tokens = min(
                self.config.burst_size,
                self._tokens + elapsed * self.config.requests_per_second,
            )
            self._last_update = now

            # Clean old requests from windows
            self._minute_requests = [t for t in self._minute_requests if now - t < 60]
            self._hour_requests = [t for t in self._hour_requests if now - t < 3600]

            # Check limits
            if len(self._minute_requests) >= self.config.requests_per_minute:
                wait_time = 60 - (now - self._minute_requests[0])
                return False, wait_time

            if len(self._hour_requests) >= self.config.requests_per_hour:
                wait_time = 3600 - (now - self._hour_requests[0])
                return False, wait_time

            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self.config.requests_per_second
                return False, wait_time

            # Consume token
            self._tokens -= 1
            self._minute_requests.append(now)
            self._hour_requests.append(now)
            return True, None

    async def wait_and_acquire(self, max_wait: float = 60.0) -> bool:
        """Wait if necessary and acquire a token"""
        start = time.monotonic()
        while True:
            success, wait_time = await self.acquire()
            if success:
                return True

            if wait_time is None:
                wait_time = 0.1

            elapsed = time.monotonic() - start
            if elapsed + wait_time > max_wait:
                return False

            await asyncio.sleep(min(wait_time, 1.0))


class AuthHandler:
    """Handles authentication for API requests"""

    @staticmethod
    def build_auth_headers(auth_type: AuthType, auth_config: dict[str, Any]) -> dict[str, str]:
        """Build authentication headers based on auth type"""
        headers = {}

        if auth_type == AuthType.API_KEY:
            key_name = auth_config.get("key_name", "X-API-Key")
            key_value = auth_config.get("key_value", "")
            key_location = auth_config.get("key_location", "header")

            if key_location == "header":
                headers[key_name] = key_value
            # Query param handling done in request building

        elif auth_type == AuthType.BEARER_TOKEN:
            token = auth_config.get("token", "")
            prefix = auth_config.get("token_prefix", "Bearer")
            headers["Authorization"] = f"{prefix} {token}"

        elif auth_type == AuthType.BASIC_AUTH:
            import base64

            username = auth_config.get("username", "")
            password = auth_config.get("password", "")
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"

        elif auth_type == AuthType.OAUTH2:
            token = auth_config.get("access_token", "")
            headers["Authorization"] = f"Bearer {token}"

        return headers

    @staticmethod
    def build_query_params(auth_type: AuthType, auth_config: dict[str, Any]) -> dict[str, str]:
        """Build query parameters for authentication"""
        params = {}

        if auth_type == AuthType.API_KEY:
            key_location = auth_config.get("key_location", "header")
            if key_location == "query":
                key_name = auth_config.get("key_name", "api_key")
                key_value = auth_config.get("key_value", "")
                params[key_name] = key_value

        return params


class BaseConnector(ABC):
    """
    Abstract base class for all external API connectors.

    Provides:
    - Authentication handling
    - Rate limiting
    - Error handling with retries
    - Response parsing
    - Connection management
    """

    def __init__(self, config: ConnectorConfig):
        self.config = config
        self._rate_limiter = RateLimiter(config.rate_limit)
        self._session: aiohttp.ClientSession | None = None
        self._status = ConnectorStatus.INACTIVE
        self._last_error: str | None = None
        self._request_count = 0
        self._error_count = 0

    @property
    @abstractmethod
    def connector_type(self) -> str:
        """Return the connector type identifier"""
        pass

    @property
    @abstractmethod
    def available_actions(self) -> list[str]:
        """Return list of available actions for this connector"""
        pass

    @property
    def status(self) -> ConnectorStatus:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._session is not None and not self._session.closed

    async def connect(self) -> bool:
        """Initialize connection and validate credentials"""
        try:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(ssl=self.config.verify_ssl)
                timeout = aiohttp.ClientTimeout(total=self.config.timeout)
                self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)

            # Validate credentials if needed
            if self.config.auth_type != AuthType.NONE:
                is_valid = await self._validate_credentials()
                if not is_valid:
                    self._status = ConnectorStatus.AUTH_EXPIRED
                    return False

            self._status = ConnectorStatus.ACTIVE
            return True

        except Exception as e:
            self._last_error = str(e)
            self._status = ConnectorStatus.ERROR
            logger.error("Failed to connect %s: %s", self.config.name, e)
            return False

    async def disconnect(self) -> None:
        """Close connection and cleanup resources"""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._status = ConnectorStatus.INACTIVE

    async def _validate_credentials(self) -> bool:
        """Validate credentials - override in subclass for specific validation"""
        return True

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from base URL and endpoint"""
        if not self.config.base_url:
            return endpoint
        base = self.config.base_url.rstrip("/")
        path = endpoint.lstrip("/")
        return f"{base}/{path}"

    def _build_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        """Build request headers including auth"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "WorkflowsPlatform/1.0",
        }
        headers.update(self.config.headers)
        headers.update(AuthHandler.build_auth_headers(self.config.auth_type, self.config.auth_config))
        if extra_headers:
            headers.update(extra_headers)
        return headers

    async def _execute_with_retry(self, method: str, endpoint: str, **kwargs) -> ConnectorResponse:
        """Execute request with retry logic"""
        last_error = None
        retry_config = self.config.retry

        for attempt in range(retry_config.max_retries + 1):
            try:
                # Wait for rate limit
                acquired = await self._rate_limiter.wait_and_acquire()
                if not acquired:
                    raise RateLimitError("Rate limit exceeded", self.config.name, retry_after=60.0)

                # Execute request
                response = await self._execute_request(method, endpoint, **kwargs)

                # Handle rate limit response
                if response.status_code == 429:
                    retry_after = self._parse_retry_after(response.headers)
                    raise RateLimitError(
                        "Rate limited by API",
                        self.config.name,
                        status_code=429,
                        retry_after=retry_after,
                    )

                # Handle auth errors
                if response.status_code in (401, 403):
                    self._status = ConnectorStatus.AUTH_EXPIRED
                    raise AuthenticationError(
                        f"Authentication failed: {response.error}",
                        self.config.name,
                        status_code=response.status_code,
                    )

                # Check for retry-able errors
                if response.status_code in retry_config.retry_on_status_codes:
                    if attempt < retry_config.max_retries:
                        delay = min(
                            retry_config.base_delay * (retry_config.exponential_base**attempt),
                            retry_config.max_delay,
                        )
                        logger.warning(
                            "Retry %s/%s for %s after %ss",
                            attempt + 1,
                            retry_config.max_retries,
                            self.config.name,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                self._request_count += 1
                return response

            except (RateLimitError, AuthenticationError):
                raise
            except Exception as e:
                last_error = e
                self._error_count += 1

                if attempt < retry_config.max_retries:
                    delay = min(
                        retry_config.base_delay * (retry_config.exponential_base**attempt),
                        retry_config.max_delay,
                    )
                    logger.warning("Retry %s for %s: %s", attempt + 1, self.config.name, e)
                    await asyncio.sleep(delay)
                else:
                    logger.error("All retries exhausted for %s: %s", self.config.name, e)

        return ConnectorResponse(success=False, error=str(last_error), status_code=0)

    async def _execute_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
        data: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> ConnectorResponse:
        """Execute a single HTTP request"""
        if not self.is_connected:
            await self.connect()

        url = self._build_url(endpoint)
        request_headers = self._build_headers(headers)

        # Add auth query params if needed
        auth_params = AuthHandler.build_query_params(self.config.auth_type, self.config.auth_config)
        params = {**params, **auth_params} if params else auth_params if auth_params else None

        start_time = time.monotonic()

        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json_data,
                data=data,
                headers=request_headers,
            ) as response:
                response_time = (time.monotonic() - start_time) * 1000  # Parse response
                try:
                    response_data = await response.json()
                except Exception as e:
                    response_data = await response.text()

                success = 200 <= response.status < 300
                data = response_data if response.status < 400 else None

                # Only populate error for non-success status codes
                error = None
                if response.status >= 400:
                    error = response_data if isinstance(response_data, str) else str(response_data)

                # Extract rate limit info
                rate_remaining = response.headers.get("X-RateLimit-Remaining")
                rate_reset = response.headers.get("X-RateLimit-Reset")

                return ConnectorResponse(
                    success=success,
                    data=data,
                    error=error,
                    status_code=response.status,
                    headers=dict(response.headers),
                    response_time_ms=response_time,
                    rate_limit_remaining=(int(rate_remaining) if rate_remaining else None),
                    rate_limit_reset=(datetime.fromtimestamp(int(rate_reset)) if rate_reset else None),
                )

        except TimeoutError:
            return ConnectorResponse(
                success=False,
                error="Request timeout",
                status_code=0,
                response_time_ms=(time.monotonic() - start_time) * 1000,
            )
        except aiohttp.ClientError as e:
            return ConnectorResponse(
                success=False,
                error=f"Connection error: {e!s}",
                status_code=0,
                response_time_ms=(time.monotonic() - start_time) * 1000,
            )

    def _parse_retry_after(self, headers: dict[str, str]) -> float:
        """Parse Retry-After header"""
        retry_after = headers.get(self.config.rate_limit.retry_after_header)
        if not retry_after:
            return 60.0

        try:
            # Try parsing as seconds
            return float(retry_after)
        except ValueError:
            # Try parsing as date
            try:
                from email.utils import parsedate_to_datetime

                dt = parsedate_to_datetime(retry_after)
                return max(0, (dt - datetime.now(UTC)).total_seconds())
            except Exception as e:
                return 60.0

    @abstractmethod
    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        """Execute a connector-specific action"""
        pass

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics"""
        return {
            "name": self.config.name,
            "type": self.connector_type,
            "status": self._status.value,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
            "is_connected": self.is_connected,
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check"""
        try:
            if not self.is_connected:
                await self.connect()

            return {
                "healthy": self._status == ConnectorStatus.ACTIVE,
                "status": self._status.value,
                "stats": self.get_stats(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": ConnectorStatus.ERROR.value,
                "error": str(e),
            }
