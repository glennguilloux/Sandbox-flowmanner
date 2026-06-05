"""Password strength validation utilities."""

import re

# Common passwords that should be rejected
COMMON_PASSWORDS = {
    "password",
    "password123",
    "123456",
    "12345678",
    "123456789",
    "1234567890",
    "qwerty",
    "abc123",
    "monkey",
    "master",
    "dragon",
    "letmein",
    "login",
    "admin",
    "welcome",
    "princess",
    "football",
    "shadow",
    "sunshine",
    "trustno1",
    "iloveyou",
    "batman",
    "access",
    "hello",
    "charlie",
    "donald",
    "123123",
    "654321",
    "superman",
    "qazwsx",
    "michael",
    "passw0rd",
    "hockey",
    "dallas",
    "killer",
    "george",
    "harley",
    "andrea",
    "joshua",
    "daniel",
    "hannah",
    "jordan",
    "robert",
    "hunter",
    "thomas",
    "andrew",
    "soccer",
    "cheese",
    "butter",
    "abcdef",
    "test123",
    "temp",
    "temp123",
    "changeme",
    "default",
}


def validate_password_strength(password: str) -> list[str]:
    """Validate password strength. Returns list of error messages (empty = valid)."""
    errors: list[str] = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r"[0-9]", password):
        errors.append("Password must contain at least one digit")

    if password.lower() in COMMON_PASSWORDS:
        errors.append("Password is too common — please choose a stronger password")

    return errors
