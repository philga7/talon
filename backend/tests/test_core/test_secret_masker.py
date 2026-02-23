"""SecretMasker processor tests."""

from app.core.logging import SecretMasker


def test_masks_api_key() -> None:
    """Fields containing 'api_key' are redacted."""
    masker = SecretMasker()
    event_dict = {"event": "test", "api_key": "sk-secret123"}
    result = masker(None, "info", event_dict)
    assert result["api_key"] == "***REDACTED***"
    assert result["event"] == "test"


def test_masks_password() -> None:
    """Fields containing 'password' are redacted."""
    masker = SecretMasker()
    event_dict = {"db_password": "secret"}
    result = masker(None, "info", event_dict)
    assert result["db_password"] == "***REDACTED***"


def test_preserves_non_secret_fields() -> None:
    """Non-secret fields are unchanged."""
    masker = SecretMasker()
    event_dict = {"user_id": "abc", "count": 42}
    result = masker(None, "info", event_dict)
    assert result["user_id"] == "abc"
    assert result["count"] == 42
