"""Application configuration module using pydantic-settings."""

import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gemini_api_key: str = Field(
        description="Google Gemini API key required for LLM operations.",
    )
    gemini_model: str = Field(
        description="Google Gemini model identifier loaded from GEMINI_MODEL.",
    )
    max_output_tokens: int = Field(
        default=4096,
        ge=1,
        le=8192,
        description="Maximum token count for LLM response generation.",
    )
    rate_limit: str = Field(
        default="10/minute",
        description="Default rate limiting threshold for public endpoints.",
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        ge=0,
        description="Time-to-live in seconds for cached generated plans.",
    )
    cache_max_items: int = Field(
        default=100,
        ge=1,
        description="Maximum number of items held in the in-memory plan cache.",
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description="List of allowed CORS origins or comma-separated string in env.",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> list[str]:
        """Parse allowed origins from a comma-separated string or list.

        Args:
            value: Raw origin input from environment or direct initialization.

        Returns:
            list[str]: Cleaned list of allowed origin strings.
        """
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return ["*"]
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [
                            str(item).strip() for item in parsed if str(item).strip()
                        ]
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings.

    Returns:
        Settings: Configured settings object.
    """
    return Settings()
