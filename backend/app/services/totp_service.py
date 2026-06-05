"""TOTP (Time-based One-Time Password) service for 2FA."""

import base64
import hashlib
import hmac
import json
import logging
import struct
import time
from io import BytesIO
from urllib.parse import quote

import bcrypt as _bcrypt

logger = logging.getLogger(__name__)

# Try to import pyotp and qrcode; provide fallback if not available
try:
    import pyotp
    HAS_PYOTP = True
except ImportError:
    HAS_PYOTP = False
    logger.warning("pyotp not installed — TOTP features will use fallback implementation")

try:
    import qrcode
    from qrcode.image.pil import PilImage
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False
    logger.warning("qrcode not installed — QR code generation unavailable")


def _base32_encode(data: bytes) -> str:
    """Encode bytes to base32 string."""
    import base64
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _base32_decode(data: str) -> bytes:
    """Decode base32 string to bytes."""
    import base64
    # Add padding
    padding = 8 - len(data) % 8
    if padding != 8:
        data += "=" * padding
    return base64.b32decode(data.upper())


def _hotp(secret: bytes, counter: int, digits: int = 6) -> str:
    """Generate HOTP value."""
    msg = struct.pack(">Q", counter)
    h = hmac.new(secret, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    binary = ((h[offset] & 0x7F) << 24 |
              (h[offset + 1] << 16) |
              (h[offset + 2] << 8) |
              h[offset + 3])
    return str(binary % (10 ** digits)).zfill(digits)


def _totp_counter(period: int = 30) -> int:
    """Get current TOTP time counter."""
    return int(time.time()) // period


def generate_secret(length: int = 20) -> str:
    """Generate a random base32-encoded TOTP secret."""
    import os
    random_bytes = os.urandom(length)
    return _base32_encode(random_bytes)


def get_provisioning_uri(secret: str, email: str, issuer: str = "FlowManner") -> str:
    """Generate otpauth:// URI for QR code."""
    label = quote(f"{issuer}:{email}")
    issuer_param = quote(issuer)
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer_param}&algorithm=SHA1&digits=6&period=30"


def get_qr_code_base64(uri: str) -> str:
    """Generate QR code as base64-encoded PNG."""
    if HAS_QRCODE:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    else:
        # Fallback: return empty string if qrcode not installed
        return ""


def verify_code(secret: str, code: str, window: int = 1, period: int = 30) -> bool:
    """Verify a TOTP code with clock skew tolerance.

    Args:
        secret: Base32-encoded TOTP secret
        code: 6-digit code to verify
        window: Number of time steps to check in each direction (default: 1 = ±30s)
        period: Time step in seconds (default: 30)
    """
    if HAS_PYOTP:
        totp = pyotp.TOTP(secret, interval=period)
        return totp.verify(code, valid_window=window)

    # Fallback implementation
    try:
        key = _base32_decode(secret)
        counter = _totp_counter(period)
        for offset in range(-window, window + 1):
            expected = _hotp(key, counter + offset)
            if hmac.compare_digest(expected, code):
                return True
        return False
    except Exception as e:
        logger.error(f"TOTP verification error: {e}")
        return False


def generate_backup_codes(count: int = 10) -> tuple[list[str], list[str]]:
    """Generate backup codes.

    Returns:
        Tuple of (plain_codes, hashed_codes) — plain for display, hashed for storage.
    """
    import secrets
    plain_codes = []
    hashed_codes = []
    for _ in range(count):
        code = secrets.token_hex(4)  # 8 hex chars
        formatted = f"{code[:4]}-{code[4:]}"
        plain_codes.append(formatted)
        hashed = _bcrypt.hashpw(formatted.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
        hashed_codes.append(hashed)
    return plain_codes, hashed_codes


def verify_backup_code(code: str, hashed_codes: list[str]) -> int:
    """Verify a backup code against hashed list.

    Returns:
        Index of matched code, or -1 if not found.
    """
    for i, hashed in enumerate(hashed_codes):
        if _bcrypt.checkpw(code.encode("utf-8"), hashed.encode("utf-8")):
            return i
    return -1


def consume_backup_code(code: str, hashed_codes_json: str) -> tuple[bool, str]:
    """Verify and consume a backup code (remove from list).

    Args:
        code: The backup code to verify
        hashed_codes_json: JSON string of hashed backup codes

    Returns:
        Tuple of (success, new_hashed_codes_json)
    """
    try:
        hashed_codes = json.loads(hashed_codes_json)
    except (json.JSONDecodeError, TypeError):
        return False, hashed_codes_json

    idx = verify_backup_code(code, hashed_codes)
    if idx < 0:
        return False, hashed_codes_json

    # Remove the used code
    hashed_codes.pop(idx)
    return True, json.dumps(hashed_codes)
