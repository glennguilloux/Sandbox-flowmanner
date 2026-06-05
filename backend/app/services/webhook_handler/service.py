#!/usr/bin/env python3
"""
Webhook Handler Service

Main service for webhook processing, coordinating signature verification,
event routing, and retry logic.
"""

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from .retry import RetryManager
from .router import WebhookRouter, webhook_router
from .signature import get_verifier

logger = logging.getLogger(__name__)


class WebhookHandlerService:
    """Main service for handling webhooks"""
    
    def __init__(self, router: WebhookRouter = None, retry_manager: RetryManager = None):
        self.router = router or webhook_router
        self.retry_manager = retry_manager or retry_manager
        self._session_factory = None
    
    def set_session_factory(self, session_factory):
        """Set the database session factory"""
        self._session_factory = session_factory
    
    def _get_session(self) -> Session:
        """Get a database session"""
        if self._session_factory:
            return self._session_factory()
        raise RuntimeError("Session factory not set")
    
    async def register_endpoint(
        self,
        name: str,
        source: str,
        path: str,
        secret: str | None = None,
        description: str | None = None,
        verify_signature: bool = True,
        signature_header: str | None = None,
        signature_prefix: str | None = None,
        handler_module: str | None = None,
        handler_function: str | None = None,
        retry_count: int = 3,
        retry_delay_seconds: int = 60,
        timeout_seconds: int = 30,
        created_by: int | None = None
    ) -> dict[str, Any]:
        """Register a new webhook endpoint"""
        from app.models.webhook_models import WebhookEndpoint
        
        session = self._get_session()
        try:
            # Check if endpoint already exists
            existing = session.query(WebhookEndpoint).filter(
                WebhookEndpoint.name == name
            ).first()
            
            if existing:
                return {
                    "success": False,
                    "error": f"Endpoint '{name}' already exists",
                    "endpoint_id": existing.id
                }
            
            endpoint = WebhookEndpoint(
                name=name,
                source=source,
                path=path,
                secret=secret,
                description=description,
                verify_signature=verify_signature,
                signature_header=signature_header,
                signature_prefix=signature_prefix,
                handler_module=handler_module,
                handler_function=handler_function,
                retry_count=retry_count,
                retry_delay_seconds=retry_delay_seconds,
                timeout_seconds=timeout_seconds,
                created_by=created_by
            )
            
            session.add(endpoint)
            session.commit()
            session.refresh(endpoint)
            
            logger.info(f"Registered webhook endpoint '{name}' for source '{source}'")
            
            return {
                "success": True,
                "endpoint": endpoint.to_dict()
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to register endpoint: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            session.close()
    
    def get_endpoint(self, path: str) -> dict[str, Any] | None:
        """Get endpoint by path"""
        from app.models.webhook_models import WebhookEndpoint
        
        session = self._get_session()
        try:
            endpoint = session.query(WebhookEndpoint).filter(
                WebhookEndpoint.path == path,
                WebhookEndpoint.is_active == True
            ).first()
            
            return endpoint.to_dict() if endpoint else None
        finally:
            session.close()
    
    def get_endpoint_by_name(self, name: str) -> dict[str, Any] | None:
        """Get endpoint by name"""
        from app.models.webhook_models import WebhookEndpoint
        
        session = self._get_session()
        try:
            endpoint = session.query(WebhookEndpoint).filter(
                WebhookEndpoint.name == name
            ).first()
            
            return endpoint.to_dict() if endpoint else None
        finally:
            session.close()
    
    def list_endpoints(self, source: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
        """List all registered endpoints"""
        from app.models.webhook_models import WebhookEndpoint
        
        session = self._get_session()
        try:
            query = session.query(WebhookEndpoint)
            
            if source:
                query = query.filter(WebhookEndpoint.source == source)
            
            if active_only:
                query = query.filter(WebhookEndpoint.is_active == True)
            
            endpoints = query.all()
            return [e.to_dict() for e in endpoints]
        finally:
            session.close()
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
        source: str,
        timestamp: str | None = None
    ) -> bool:
        """Verify webhook signature"""
        verifier = get_verifier(source)
        
        # Special handling for Slack which needs timestamp
        if source.lower() == 'slack' and timestamp:
            return verifier.verify(payload, signature, secret, timestamp=timestamp)
        
        return verifier.verify(payload, signature, secret)
    
    def extract_event_type(self, source: str, payload: dict[str, Any], headers: dict[str, str]) -> str | None:
        """Extract event type from webhook payload based on source"""
        source_lower = source.lower()
        
        if source_lower == 'github':
            return headers.get('x-github-event') or payload.get('action')
        
        elif source_lower == 'stripe':
            return payload.get('type')
        
        elif source_lower == 'slack':
            return payload.get('type') or payload.get('event', {}).get('type')
        
        elif source_lower == 'twilio':
            return payload.get('MessageStatus') or payload.get('CallStatus')
        
        elif source_lower == 'shopify':
            return headers.get('x-shopify-topic')
        
        return payload.get('event_type') or payload.get('type')
    
    async def process_webhook(
        self,
        path: str,
        payload: bytes,
        headers: dict[str, str]
    ) -> dict[str, Any]:
        """Process an incoming webhook"""
        from app.models.webhook_models import WebhookLog, WebhookStatus
        
        start_time = time.time()
        
        # Get endpoint configuration
        endpoint = self.get_endpoint(path)
        if not endpoint:
            logger.warning(f"No active endpoint found for path: {path}")
            return {
                "success": False,
                "error": "Endpoint not found",
                "status_code": 404
            }
        
        
        session = self._get_session()
        webhook_log = None
        
        try:
            # Parse payload
            try:
                payload_json = json.loads(payload.decode('utf-8'))
            except json.JSONDecodeError:
                payload_json = {"raw": payload.decode('utf-8', errors='replace')}
            
            # Extract event type
            event_type = self.extract_event_type(
                endpoint['source'],
                payload_json,
                headers
            )
            
            # Create webhook log entry
            webhook_log = WebhookLog(
                endpoint_id=endpoint['id'],
                source=endpoint['source'],
                event_type=event_type,
                status=WebhookStatus.PENDING.value,
                headers=headers,
                payload=payload_json,
                raw_body=payload.decode('utf-8', errors='replace'),
                max_retries=endpoint.get('retry_count', 3)
            )
            session.add(webhook_log)
            session.commit()
            session.refresh(webhook_log)
            
            # Verify signature if required
            if endpoint.get('verify_signature', True):
                signature_header = endpoint.get('signature_header', 'x-signature')
                signature = headers.get(signature_header) or headers.get(signature_header.lower())
                
                if not signature:
                    logger.warning(f"Missing signature header: {signature_header}")
                    webhook_log.status = WebhookStatus.FAILED.value
                    webhook_log.last_error = "Missing signature header"
                    webhook_log.last_error_at = datetime.now(UTC)
                    session.commit()
                    
                    return {
                        "success": False,
                        "error": "Missing signature",
                        "status_code": 401,
                        "webhook_id": webhook_log.id
                    }
                
                
                # Get timestamp for Slack
                timestamp = headers.get('x-slack-request-timestamp') if endpoint['source'].lower() == 'slack' else None
                
                if not self.verify_signature(
                    payload,
                    signature,
                    endpoint['secret'],
                    endpoint['source'],
                    timestamp
                ):
                    logger.warning(f"Invalid signature for endpoint: {endpoint['name']}")
                    webhook_log.status = WebhookStatus.FAILED.value
                    webhook_log.last_error = "Invalid signature"
                    webhook_log.last_error_at = datetime.now(UTC)
                    session.commit()
                    
                    return {
                        "success": False,
                        "error": "Invalid signature",
                        "status_code": 401,
                        "webhook_id": webhook_log.id
                    }
            
            # Update status to processing
            webhook_log.status = WebhookStatus.PROCESSING.value
            webhook_log.processing_started_at = datetime.now(UTC)
            session.commit()
            
            # Route to handlers
            result = await self.router.route(
                endpoint['source'],
                event_type,
                payload_json,
                headers
            )
            
            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Update webhook log
            webhook_log.processing_completed_at = datetime.now(UTC)
            webhook_log.processing_time_ms = processing_time_ms
            webhook_log.response_code = 200 if result.get('success') else 500
            webhook_log.response_body = result
            
            if result.get('success'):
                webhook_log.status = WebhookStatus.SUCCESS.value
            else:
                webhook_log.status = WebhookStatus.FAILED.value
                webhook_log.last_error = str(result.get('errors', 'Unknown error'))
                webhook_log.last_error_at = datetime.now(UTC)
            
            session.commit()
            
            return {
                "success": result.get('success', False),
                "webhook_id": webhook_log.id,
                "processing_time_ms": processing_time_ms,
                "handlers_executed": result.get('handlers_executed', 0),
                "status_code": 200 if result.get('success') else 500
            }
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            
            if webhook_log:
                webhook_log.status = WebhookStatus.FAILED.value
                webhook_log.last_error = str(e)
                webhook_log.last_error_at = datetime.now(UTC)
                webhook_log.processing_time_ms = int((time.time() - start_time) * 1000)
                session.commit()
            
            return {
                "success": False,
                "error": str(e),
                "status_code": 500,
                "webhook_id": webhook_log.id if webhook_log else None
            }
