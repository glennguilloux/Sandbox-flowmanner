#!/usr/bin/env python3
"""
Webhook Signature Verification

Supports multiple signature verification methods:
- HMAC SHA256 (GitHub, Stripe, generic)
- HMAC SHA1 (legacy)
- Timestamp-based signatures (Slack)
"""

import hashlib
import hmac
import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SignatureVerifier(ABC):
    """Abstract base class for signature verifiers"""

    @abstractmethod
    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify the signature of a webhook payload"""
        pass

    @abstractmethod
    def extract_signature(self, header_value: str) -> str | None:
        """Extract signature from header value"""
        pass


class HMACSHA256Verifier(SignatureVerifier):
    """HMAC SHA256 signature verification (GitHub, generic)"""

    def __init__(self, prefix: str = "sha256="):
        self.prefix = prefix

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify HMAC SHA256 signature"""
        try:
            expected_sig = hmac.new(
                secret.encode("utf-8"), payload, hashlib.sha256
            ).hexdigest()

            # Remove prefix if present
            sig = signature
            if self.prefix and sig.startswith(self.prefix):
                sig = sig[len(self.prefix) :]

            return hmac.compare_digest(sig.lower(), expected_sig.lower())
        except Exception as e:
            logger.error('HMAC SHA256 verification failed: %s', e)
            return False

    def extract_signature(self, header_value: str) -> str | None:
        """Extract signature from header"""
        if not header_value:
            return None
        if self.prefix and header_value.startswith(self.prefix):
            return header_value
        return header_value


class HMACSHA1Verifier(SignatureVerifier):
    """HMAC SHA1 signature verification (legacy systems)"""

    def __init__(self, prefix: str = "sha1="):
        self.prefix = prefix

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify HMAC SHA1 signature"""
        try:
            expected_sig = hmac.new(
                secret.encode("utf-8"), payload, hashlib.sha1
            ).hexdigest()

            sig = signature
            if self.prefix and sig.startswith(self.prefix):
                sig = sig[len(self.prefix) :]

            return hmac.compare_digest(sig.lower(), expected_sig.lower())
        except Exception as e:
            logger.error('HMAC SHA1 verification failed: %s', e)
            return False

    def extract_signature(self, header_value: str) -> str | None:
        if not header_value:
            return None
        if self.prefix and header_value.startswith(self.prefix):
            return header_value
        return header_value


class StripeVerifier(SignatureVerifier):
    """Stripe webhook signature verification with timestamp"""

    def __init__(self, tolerance_seconds: int = 300):
        self.tolerance_seconds = tolerance_seconds
        self.prefix = "t="

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify Stripe signature with timestamp"""
        try:
            # Parse the signature header
            # Format: t=1234567890,v1=abc123...
            elements = signature.split(",")
            timestamp = None
            v1_signature = None

            for element in elements:
                if element.startswith("t="):
                    timestamp = int(element[2:])
                elif element.startswith("v1="):
                    v1_signature = element[3:]

            if not timestamp or not v1_signature:
                logger.error("Invalid Stripe signature format")
                return False

            # Check timestamp tolerance
            current_time = int(time.time())
            if abs(current_time - timestamp) > self.tolerance_seconds:
                logger.warning('Stripe webhook timestamp outside tolerance: %s', timestamp)
                return False

            # Compute expected signature
            signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
            expected_sig = hmac.new(
                secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(v1_signature.lower(), expected_sig.lower())
        except Exception as e:
            logger.error('Stripe signature verification failed: %s', e)
            return False

    def extract_signature(self, header_value: str) -> str | None:
        return header_value


class SlackVerifier(SignatureVerifier):
    """Slack webhook signature verification"""

    def __init__(self, tolerance_seconds: int = 300):
        self.tolerance_seconds = tolerance_seconds

    def verify(
        self, payload: bytes, signature: str, secret: str, timestamp: str | None = None
    ) -> bool:
        """Verify Slack signature"""
        try:
            if not timestamp:
                logger.error("Slack verification requires timestamp")
                return False

            # Check timestamp tolerance
            try:
                ts = int(timestamp)
                current_time = int(time.time())
                if abs(current_time - ts) > self.tolerance_seconds:
                    logger.warning('Slack webhook timestamp outside tolerance: %s', ts)
                    return False
            except ValueError:
                logger.error('Invalid Slack timestamp: %s', timestamp)
                return False

            # Compute signature
            # Slack uses: "v0:" + timestamp + ":" + body
            basestring = f"v0:{timestamp}:{payload.decode('utf-8')}"
            expected_sig = (
                "v0="
                + hmac.new(
                    secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256
                ).hexdigest()
            )

            return hmac.compare_digest(signature, expected_sig)
        except Exception as e:
            logger.error('Slack signature verification failed: %s', e)
            return False

    def extract_signature(self, header_value: str) -> str | None:
        return header_value


class TwilioVerifier(SignatureVerifier):
    """Twilio webhook signature verification"""

    def __init__(self, url: str):
        self.url = url

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify Twilio signature"""
        try:
            import urllib.parse

            # Parse the payload as form data
            params = urllib.parse.parse_qs(payload.decode("utf-8"))

            # Sort and concatenate parameters
            sorted_params = sorted(params.items())
            param_str = "".join(f"{k}{v[0]}" for k, v in sorted_params)

            # Compute signature
            url_with_params = self.url + param_str
            expected_sig = hmac.new(
                secret.encode("utf-8"), url_with_params.encode("utf-8"), hashlib.sha1
            ).digest()

            import base64

            expected_sig_b64 = base64.b64encode(expected_sig).decode("utf-8")

            return hmac.compare_digest(signature, expected_sig_b64)
        except Exception as e:
            logger.error('Twilio signature verification failed: %s', e)
            return False

    def extract_signature(self, header_value: str) -> str | None:
        return header_value


class ShopifyVerifier(SignatureVerifier):
    """Shopify webhook signature verification"""

    def verify(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify Shopify HMAC SHA256 signature"""
        try:
            expected_sig = hmac.new(
                secret.encode("utf-8"), payload, hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature.lower(), expected_sig.lower())
        except Exception as e:
            logger.error('Shopify signature verification failed: %s', e)
            return False

    def extract_signature(self, header_value: str) -> str | None:
        return header_value


def get_verifier(source: str, **kwargs) -> SignatureVerifier:
    """Get the appropriate verifier for a webhook source"""
    verifiers = {
        "github": HMACSHA256Verifier(prefix="sha256="),
        "stripe": StripeVerifier(),
        "slack": SlackVerifier(),
        "twilio": TwilioVerifier(url=kwargs.get("url", "")),
        "shopify": ShopifyVerifier(),
        "generic": HMACSHA256Verifier(prefix=""),
    }

    return verifiers.get(source.lower(), HMACSHA256Verifier())
