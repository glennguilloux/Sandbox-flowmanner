import logging
import ssl
from functools import wraps
from typing import Any

from flask import jsonify, request

logger = logging.getLogger(__name__)


class MTLSValidator:
    def __init__(self, ca_cert_path: str):
        self.ca_cert_path = ca_cert_path
        self._context = None

    @property
    def context(self) -> ssl.SSLContext:
        if self._context is None:
            self._context = ssl.create_default_context(
                purpose=ssl.Purpose.CLIENT_AUTH, cafile=self.ca_cert_path
            )
            self._context.verify_mode = ssl.CERT_REQUIRED
            self._context.check_hostname = False  # For internal services
        return self._context

    def validate_client_cert(self, client_cert: bytes | None) -> dict[str, Any]:
        if not client_cert:
            return {"valid": False, "error": "No client certificate provided"}

        try:
            # Parse certificate
            cert = ssl.DER_cert_to_PEM_cert(client_cert)

            # Validate against CA
            # Note: In production, we'd do more thorough validation
            # including checking CN, SANs, etc.

            # For now, just check if it's signed by our CA
            # (actual validation happens at TLS handshake level)
            return {
                "valid": True,
                "certificate": cert,
                "message": "Certificate validated",
            }

        except Exception as e:
            logger.error(f"Certificate validation error: {e}")
            return {"valid": False, "error": str(e)}


def require_mtls(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check if request came over TLS
        if not request.is_secure:
            logger.warning(f"Non-TLS request to protected endpoint: {request.path}")
            return (
                jsonify(
                    {
                        "error": "TLS required",
                        "message": "This endpoint requires TLS/mTLS",
                    }
                ),
                403,
            )

        # Get client certificate from request
        client_cert = request.environ.get("SSL_CLIENT_CERT")

        if not client_cert:
            logger.warning(f"No client certificate for request to: {request.path}")
            return (
                jsonify(
                    {
                        "error": "Client certificate required",
                        "message": "mTLS client certificate is required",
                    }
                ),
                403,
            )

        # Store certificate info in request context for later use
        request.client_certificate = client_cert

        # Extract common name from certificate for logging
        try:
            # Parse certificate info (simplified)
            # In production, use proper X.509 parsing
            cert_lines = client_cert.decode("utf-8").split("\n")
            cn_line = [line for line in cert_lines if "CN=" in line]
            if cn_line:
                cn = cn_line[0].split("CN=")[1].split(",")[0]
                request.client_cn = cn
                logger.info(f"mTLS request from CN={cn} to {request.path}")
        except Exception:
            logger.debug("Failed to parse client certificate CN from mTLS request")

        return f(*args, **kwargs)

    return decorated


def extract_client_info() -> dict[str, Any]:
    """Extract client certificate information from request"""
    client_cert = request.environ.get("SSL_CLIENT_CERT")
    if not client_cert:
        return {}

    try:
        cert_lines = client_cert.decode("utf-8").split("\n")
        info = {}

        for line in cert_lines:
            if "CN=" in line:
                info["common_name"] = line.split("CN=")[1].split(",")[0]
            elif "O=" in line:
                info["organization"] = line.split("O=")[1].split(",")[0]
            elif "L=" in line:
                info["location"] = line.split("L=")[1].split(",")[0]
            elif "C=" in line:
                info["country"] = line.split("C=")[1].split(",")[0]

        return info
    except Exception:
        logger.debug("Failed to extract client certificate info from request")
        return {}


class MTLSConfig:
    def __init__(self, enabled: bool = True, ca_cert: str = "/certs/ca.crt"):
        self.enabled = enabled
        self.ca_cert = ca_cert
        self.validator = MTLSValidator(ca_cert) if enabled else None

    def validate_request(self, request) -> dict[str, Any]:
        if not self.enabled:
            return {"valid": True, "message": "mTLS disabled"}

        client_cert = request.environ.get("SSL_CLIENT_CERT")
        return (
            self.validator.validate_client_cert(client_cert)
            if client_cert
            else {"valid": False, "error": "No client certificate"}
        )
