"""Google Gemini LLM service integration, structured generation, caching, and retry handling."""

import hashlib
import logging
import time
from datetime import date
from functools import lru_cache
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.prompts import SYSTEM_PROMPT, build_user_message
from app.schemas import EventRequest, Plan
from app.validators import validate_plan

logger = logging.getLogger(__name__)


class PlanGenerationError(Exception):
    """Raised when event plan generation fails or fails validation after retry."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class PlanCache:
    """Thread-safe in-memory TTL cache for generated event plans."""

    def __init__(self, ttl_seconds: int = 3600, max_items: int = 100) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._store: dict[str, tuple[Plan, float]] = {}

    def get(self, key: str) -> Plan | None:
        """Retrieve a cached plan if it has not expired."""
        now = time.time()
        if key in self._store:
            plan, expiry = self._store[key]
            if now < expiry:
                return plan
            del self._store[key]
        return None

    def set(self, key: str, plan: Plan) -> None:
        """Cache a plan with TTL and enforce max capacity through FIFO eviction."""
        now = time.time()
        if len(self._store) >= self.max_items and key not in self._store:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
        self._store[key] = (plan, now + self.ttl_seconds)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._store.clear()


@lru_cache(maxsize=1)
def get_plan_cache() -> PlanCache:
    """Return singleton instance of in-memory PlanCache."""
    settings = get_settings()
    return PlanCache(
        ttl_seconds=settings.cache_ttl_seconds,
        max_items=settings.cache_max_items,
    )


def compute_request_hash(request: EventRequest) -> str:
    """Compute a deterministic SHA-256 hash of the sanitized request payload.

    Args:
        request: Validated event request.

    Returns:
        str: Hexadecimal SHA-256 digest string.
    """
    serialized = request.model_dump_json(by_alias=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _parse_response_to_plan(response: Any) -> Plan:
    """Extract and validate Plan from Gemini response object.

    Args:
        response: Response object from client.models.generate_content.

    Returns:
        Plan: Validated Plan instance.

    Raises:
        PlanGenerationError: If the output cannot be parsed into a Plan.
    """
    if hasattr(response, "parsed") and isinstance(response.parsed, Plan):
        return response.parsed

    if hasattr(response, "text") and response.text:
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return Plan.model_validate_json(text)
        except Exception as exc:
            raise PlanGenerationError(
                f"Failed to parse LLM response into Plan schema: {exc}"
            ) from exc

    raise PlanGenerationError("LLM response did not contain text or structured output.")


def generate_plan(
    request: EventRequest,
    client: Any = None,
    today: date | None = None,
    cache: PlanCache | None = None,
) -> Plan:
    """Generate and validate an event plan with retry on validation errors.

    Args:
        request: User event planning request.
        client: Injected Google GenAI client (optional, uses real client if None).
        today: Reference planning date (defaults to date.today()).
        cache: Optional PlanCache instance (defaults to singleton get_plan_cache()).

    Returns:
        Plan: Validated event plan.

    Raises:
        PlanGenerationError: If generation fails twice or encounters network/model errors.
    """
    today_date = today or date.today()
    cache_instance = cache if cache is not None else get_plan_cache()
    cache_key = compute_request_hash(request)

    # 1. Check TTL cache
    cached_plan = cache_instance.get(cache_key)
    if cached_plan is not None:
        logger.info("Serving event plan from cache key=%s", cache_key[:8])
        return cached_plan

    # 2. Initialize client and configuration
    settings = get_settings()
    active_client = client
    if active_client is None:
        active_client = genai.Client(api_key=settings.gemini_api_key)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=Plan,
        max_output_tokens=settings.max_output_tokens,
        http_options=types.HttpOptions(timeout=30000),  # 30-second timeout
    )

    # 3. Attempt 1
    logger.info(
        "Dispatching LLM plan generation: type=%s, lang=%s",
        request.event_type.value,
        request.language.value,
    )
    first_prompt = build_user_message(request, today=today_date)
    try:
        response = active_client.models.generate_content(
            model=settings.gemini_model,
            contents=first_prompt,
            config=config,
        )
        plan = _parse_response_to_plan(response)
    except PlanGenerationError:
        raise
    except Exception as exc:
        raise PlanGenerationError(f"LLM API request failed: {exc}") from exc

    errors = validate_plan(plan, request, today_date)
    if not errors:
        cache_instance.set(cache_key, plan)
        return plan

    # 4. Retry Attempt (Single retry with validation feedback)
    logger.warning(
        "Attempt 1 validation failed with %d error(s). Retrying with feedback.",
        len(errors),
    )
    retry_prompt = build_user_message(request, today=today_date, retry_errors=errors)
    try:
        retry_response = active_client.models.generate_content(
            model=settings.gemini_model,
            contents=retry_prompt,
            config=config,
        )
        retry_plan = _parse_response_to_plan(retry_response)
    except PlanGenerationError:
        raise
    except Exception as exc:
        raise PlanGenerationError(f"LLM API retry request failed: {exc}") from exc

    retry_errors = validate_plan(retry_plan, request, today_date)
    if not retry_errors:
        cache_instance.set(cache_key, retry_plan)
        return retry_plan

    raise PlanGenerationError(
        f"Plan generation failed validation after retry: {'; '.join(retry_errors)}",
        errors=retry_errors,
    )
