"""Test suite configuration and default environment variables."""

import os

os.environ.setdefault("GEMINI_API_KEY", "mock-conftest-key")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")
os.environ.setdefault("MAX_OUTPUT_TOKENS", "4096")
os.environ.setdefault("RATE_LIMIT", "10/minute")
os.environ.setdefault("CACHE_TTL_SECONDS", "3600")
os.environ.setdefault("CACHE_MAX_ITEMS", "100")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
