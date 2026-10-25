"""Unit tests for application configuration management."""

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_settings_loaded_from_direct_values() -> None:
    """Verify that settings initialize correctly with provided parameters."""
    settings = Settings(
        gemini_api_key="test-api-key",
        gemini_model="gemini-2.5-flash",
        max_output_tokens=2048,
        rate_limit="20/minute",
        cache_ttl_seconds=1800,
        cache_max_items=50,
        allowed_origins=["https://utsav.example.com"],
    )
    assert settings.gemini_api_key == "test-api-key"
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.max_output_tokens == 2048
    assert settings.rate_limit == "20/minute"
    assert settings.cache_ttl_seconds == 1800
    assert settings.cache_max_items == 50
    assert settings.allowed_origins == ["https://utsav.example.com"]


def test_settings_requires_gemini_api_key_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings must raise ValidationError if GEMINI_API_KEY or GEMINI_MODEL is absent."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("raw_origin", "expected"),
    [
        ("https://a.com, https://b.com", ["https://a.com", "https://b.com"]),
        ('["https://a.com", "https://b.com"]', ["https://a.com", "https://b.com"]),
        ("", ["*"]),
        (["https://direct.com"], ["https://direct.com"]),
    ],
)
def test_allowed_origins_parsing(raw_origin: object, expected: list[str]) -> None:
    """Verify parsing of allowed_origins from string, json array, and lists."""
    settings = Settings(
        gemini_api_key="key",
        gemini_model="model",
        allowed_origins=raw_origin,  # type: ignore[arg-type]
    )
    assert settings.allowed_origins == expected


def test_get_settings_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_settings returns a cached instance."""
    monkeypatch.setenv("GEMINI_API_KEY", "singleton-key")
    monkeypatch.setenv("GEMINI_MODEL", "singleton-model")
    get_settings.cache_clear()

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    assert s1.gemini_api_key == "singleton-key"
    get_settings.cache_clear()
