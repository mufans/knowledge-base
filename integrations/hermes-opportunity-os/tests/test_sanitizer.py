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
        "credentials": {"api_key": "[REDACTED]"},
        "count": 2,
    }
