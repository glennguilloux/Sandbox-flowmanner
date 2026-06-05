#!/usr/bin/env python3
"""
Idempotency Middleware

FastAPI middleware for API-level idempotency key handling.
Ensures that duplicate requests are properly handled without duplicate side effects.

Part of Phase 1: SOLID Capabilities Enhancement
"""

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


# Default TTL for idempotency keys (24 hours)
DEFAULT_IDEMPOTENCY_TTL_HOURS = 24
# Maximum TTL allowed (7 days)
MAX_IDEMPOTENCY_TTL_HOURS = 168


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles idempotency keys for API requests.
    
    Usage:
        1. Client sends request with header: `Idempotency-Key: <unique-key>`
        2. Middleware checks if key exists and is completed
        3. If completed, returns cached response
        4. If processing, returns 425 (Too Early)
        5. If new, processes request and caches response
    """
    
    # Headers
    IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
    IDEMPOTENCY_REPLAY_HEADER = "Idempotency-Replay"
    IDEMPOTENCY_ORIGINAL_METHOD_HEADER = "Idempotency-Original-Method"
    IDEMPOTENCY_ORIGINAL_URI_HEADER = "Idempotency-Original-Uri"
    
    def __init__(
        self,
        app: ASGIApp,
        db_session_factory=None,
        ttl_hours: int = DEFAULT_IDEMPOTENCY_TTL_HOURS,
        exclude_paths: list = None,
    ):
        """
        Initialize idempotency middleware.
        
        Args:
            app: The ASGI application
            db_session_factory: Database session factory function
            ttl_hours: Time-to-live for idempotency keys
            exclude_paths: Paths to exclude from idempotency checking
        """
        super().__init__(app)
        self.db_session_factory = db_session_factory
        self.ttl_hours = ttl_hours
        self.exclude_paths = exclude_paths or []
    
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Process request with idempotency handling.
        """
        # Check if path is excluded
        if self._is_excluded(request):
            return await call_next(request)
        
        # Get idempotency key from header
        idempotency_key = request.headers.get(self.IDEMPOTENCY_KEY_HEADER)
        
        # Only apply idempotency to POST, PUT, PATCH methods
        if request.method in ("GET", "HEAD", "DELETE"):
            return await call_next(request)
        
        # If no idempotency key, proceed normally
        if not idempotency_key:
            return await call_next(request)
        
        # Validate idempotency key format
        if not self._validate_key(idempotency_key):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid idempotency key",
                    "detail": "Idempotency key must be a valid string (1-255 characters)",
                }
            )
        
        # Process with idempotency handling
        return await self._handle_idempotent_request(
            request, idempotency_key, call_next
        )
    
    async def _handle_idempotent_request(
        self,
        request: Request,
        idempotency_key: str,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Handle a request with idempotency key.
        """
        if not self.db_session_factory:
            # No DB - use in-memory cache (limited functionality)
            return await call_next(request)
        
        db = self.db_session_factory()
        try:
            from app.models.idempotency import IdempotencyKey
            
            # Check for existing key
            existing = db.query(IdempotencyKey).filter(
                IdempotencyKey.idempotency_key == idempotency_key
            ).first()
            
            now = datetime.now(UTC)
            
            if existing:
                # Check if expired
                if existing.expires_at and existing.expires_at < now:
                    # Key expired, treat as new request
                    db.delete(existing)
                    db.commit()
                    return await self._process_new_request(
                        request, idempotency_key, call_next, db
                    )
                
                # Check if still processing (concurrent duplicate)
                if existing.is_processing:
                    # Check if processing for too long (potential deadlock)
                    processing_time = (now - existing.updated_at).total_seconds()
                    if processing_time > 300:  # 5 minutes
                        # Reset processing status and retry
                        existing.is_processing = False
                        db.commit()
                        return await self._process_new_request(
                            request, idempotency_key, call_next, db
                        )
                    
                    return JSONResponse(
                        status_code=425,
                        content={
                            "error": "Request still processing",
                            "detail": "Another request with the same idempotency key is currently being processed",
                            "retry_after": 5,
                        },
                        headers={"Retry-After": "5"}
                    )
                
                # Return cached response
                existing.cache_hits += 1
                existing.last_accessed_at = now
                db.commit()
                
                # Log duplicate request
                self._log_request(db, request, idempotency_key, existing, was_cached=True)
                
                return self._build_cached_response(existing)
            
            # New request - process it
            return await self._process_new_request(
                request, idempotency_key, call_next, db
            )
            
        except Exception as e:
            logger.error(f"Idempotency middleware error: {e}")
            db.rollback()
            return await call_next(request)
        finally:
            db.close()
    
    async def _process_new_request(
        self,
        request: Request,
        idempotency_key: str,
        call_next: RequestResponseEndpoint,
        db,
    ) -> Response:
        """
        Process a new idempotent request and cache the response.
        """
        from app.models.idempotency import IdempotencyKey
        
        # Create request hash
        request_body = await self._get_request_body(request)
        request_hash = self._hash_request(request.method, request.url.path, request_body)
        
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=self.ttl_hours)
        
        # Create idempotency key record
        idempotency_record = IdempotencyKey(
            idempotency_key=idempotency_key,
            user_id=request.state.user_id if hasattr(request.state, "user_id") else None,
            endpoint=request.url.path,
            request_hash=request_hash,
            is_processing=True,
            expires_at=expires_at,
        )
        
        db.add(idempotency_record)
        db.commit()
        
        try:
            # Process the actual request
            start_time = time.time()
            response = await call_next(request)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Mark as completed
            idempotency_record.is_processing = False
            idempotency_record.is_completed = True
            idempotency_record.response_status = response.status_code
            idempotency_record.response_headers = dict(response.headers)
            
            # Store response body for cacheable statuses
            if response.status_code in (200, 201, 202, 204):
                response_body = await self._get_response_body(response)
                if self._is_cacheable(response_body):
                    idempotency_record.response_body = response_body
            
            db.commit()
            
            # Log successful request
            self._log_request(db, request, idempotency_key, idempotency_record, was_cached=False)
            
            # Add idempotency headers to response
            response.headers[self.IDEMPOTENCY_REPLAY_HEADER] = "original"
            
            return response
            
        except Exception as e:
            # Mark as failed
            idempotency_record.is_processing = False
            idempotency_record.error_message = str(e)
            db.commit()
            
            # Log failed request
            self._log_request(db, request, idempotency_key, idempotency_record, was_cached=False)
            
            raise
    
    def _validate_key(self, key: str) -> bool:
        """Validate idempotency key format."""
        if not key:
            return False
        if len(key) < 1 or len(key) > 255:
            return False
        # Allow alphanumeric, dashes, underscores, and some special characters
        return bool(re.match(r'^[\w\-]+$', key))
    
    def _is_excluded(self, request: Request) -> bool:
        """Check if path should be excluded from idempotency."""
        path = request.url.path
        return any(path.startswith(excl) for excl in self.exclude_paths)
    
    def _hash_request(self, method: str, path: str, body: str) -> str:
        """Create SHA-256 hash of request for comparison."""
        content = f"{method}:{path}:{body}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def _get_request_body(self, request: Request) -> str:
        """Get request body as string."""
        try:
            body = await request.body()
            return body.decode("utf-8") if body else ""
        except Exception:
            return ""
    
    async def _get_response_body(self, response: Response) -> Any:
        """Extract response body for caching."""
        try:
            # For JSONResponse, access the body
            if hasattr(response, "body"):
                body = response.body
                if isinstance(body, bytes):
                    return json.loads(body.decode("utf-8"))
            elif hasattr(response, "json"):
                return response.json
        except Exception:
            logger.debug("idempotency_response_body_failed", exc_info=True)
        return None
    
    def _is_cacheable(self, body: Any) -> bool:
        """Check if response body is cacheable."""
        if body is None:
            return False
        return bool(isinstance(body, dict))
    
    def _build_cached_response(self, record: Any) -> Response:
        """Build response from cached idempotency record."""
        headers = record.response_headers or {}
        headers[self.IDEMPOTENCY_REPLAY_HEADER] = "cache"
        
        if record.response_body:
            return JSONResponse(
                content=record.response_body,
                status_code=record.response_status or 200,
                headers=headers,
            )
        
        return Response(
            status_code=record.response_status or 200,
            headers=headers,
        )
    
    def _log_request(
        self,
        db,
        request: Request,
        idempotency_key: str,
        record: Any,
        was_cached: bool,
    ):
        """Log idempotency request for audit."""
        try:
            from app.models.idempotency import IdempotencyRequestLog
            
            log_entry = IdempotencyRequestLog(
                idempotency_key=idempotency_key,
                user_id=getattr(request.state, "user_id", None),
                request_id=request.headers.get("X-Request-ID"),
                endpoint=request.url.path,
                method=request.method,
                response_status=record.response_status,
                response_time_ms=0,
                was_cached=was_cached,
            )
            
            db.add(log_entry)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to log idempotency request: {e}")


# Helper function to create idempotency key
def create_idempotency_key() -> str:
    """Generate a new idempotency key."""
    return str(uuid4())


# Decorator for easy idempotency handling in endpoints
def idempotent(
    key_param: str = "idempotency_key",
    ttl_hours: int = DEFAULT_IDEMPOTENCY_TTL_HOURS,
):
    """
    Decorator for marking endpoints as idempotent.
    
    Usage:
        @app.post("/items")
        @idempotent(key_param="key")
        async def create_item(request: Request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        # This would need FastAPI's Depends to work properly
        # For now, this is a placeholder for the decorator pattern
        return func
    return decorator
