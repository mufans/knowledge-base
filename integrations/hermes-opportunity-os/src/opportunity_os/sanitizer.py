"""Content-level checks and redaction for public-safe payloads."""

import re
from typing import Any


SENSITIVE_FIELDS = {
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "cash_amount",
    "private_contact",
    "application_message",
}
REDACTED = "[REDACTED]"
SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
    re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[=:]\s*\S+"),
    re.compile(r"\b(?:sk|go)-[A-Za-z0-9_-]{12,}\b"),
)
SENSITIVE_KEY_TERMS = {"password", "secret", "cookie", "credential", "credentials"}
SENSITIVE_KEY_CONTEXTS = {"api", "auth", "access", "gateway", "private", "provider", "refresh"}


def is_sensitive_key(key: object) -> bool:
    """Recognize credential keys while preserving aggregate token metrics."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
    if normalized in SENSITIVE_FIELDS:
        return True
    parts = normalized.split("_")
    if any(part in SENSITIVE_KEY_TERMS for part in parts):
        return True
    return parts[-1:] in (["key"], ["token"]) and any(
        part in SENSITIVE_KEY_CONTEXTS for part in parts[:-1]
    )


def contains_secret(value: object) -> bool:
    """Return whether a nested value contains a sensitive field or secret-like text."""
    if isinstance(value, dict):
        return any(is_sensitive_key(key) or contains_secret(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item) for item in value)
    return isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_PATTERNS)


def sanitize_public(value: object) -> object:
    """Recursively preserve safe structure while redacting sensitive content."""
    if isinstance(value, dict):
        return {
            key: REDACTED if is_sensitive_key(key) else sanitize_public(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_public(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_public(item) for item in value)
    if isinstance(value, str) and contains_secret(value):
        return REDACTED
    return value
