import pytest

from opportunity_os.sanitizer import contains_secret, sanitize_public


def test_sanitizer_rejects_secret_inside_free_text() -> None:
    assert contains_secret("Authorization: Bearer sk-private-value") is True


def test_sanitizer_detects_sensitive_fields_and_nested_values() -> None:
    assert contains_secret({"safe": ["visible", {"token": "private"}]}) is True


def test_sanitize_public_redacts_sensitive_fields_and_free_text() -> None:
    payload = {
        "label": "Authorization: Bearer sk-private-value",
        "credentials": {"api_key": "private"},
        "count": 2,
    }

    assert sanitize_public(payload) == {
        "label": "[REDACTED]",
        "credentials": "[REDACTED]",
        "count": 2,
    }


@pytest.mark.parametrize(
    "key",
    [
        "provider_key",
        "gateway_token",
        "OPENCODE_GO_API_KEY",
        "DEEPSEEK_API_KEY",
        "Provider-Key",
        "GATEWAY-TOKEN",
        "AUTH_ACCESS_TOKEN",
        "refresh-cookie",
        "user_credential",
    ],
)
def test_sanitizer_redacts_normalized_credential_keys(key: str) -> None:
    payload = {key: "opaque-private-value"}

    assert contains_secret(payload) is True
    assert sanitize_public(payload) == {key: "[REDACTED]"}


@pytest.mark.parametrize("key", ["token_count", "input_tokens", "output_tokens"])
def test_sanitizer_keeps_token_metrics_public(key: str) -> None:
    payload = {key: 42}

    assert contains_secret(payload) is False
    assert sanitize_public(payload) == payload
