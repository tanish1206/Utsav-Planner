"""Pydantic v2 schemas and validation models for Utsav Planner."""

import unicodedata
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):  # noqa: UP042
        """Fallback for environments running Python < 3.11."""


class EventType(StrEnum):
    """Supported event categories."""

    wedding = "wedding"
    birthday = "birthday"
    community = "community"


class Language(StrEnum):
    """Supported localization languages."""

    en = "en"
    hi = "hi"
    mr = "mr"


def sanitize_text(value: object, field_name: str) -> str | None:
    """Strip leading and trailing whitespace and reject control characters.

    Args:
        value: Input string to validate and sanitize.
        field_name: The name of the field being validated.

    Returns:
        str | None: Sanitized string or None for empty optional values.

    Raises:
        ValueError: If prohibited control characters are found.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    for char in stripped:
        if field_name == "notes" and char in ("\n", "\r", "\t"):
            continue
        if unicodedata.category(char) == "Cc" or ord(char) < 32 or ord(char) == 127:
            raise ValueError(f"Control characters are prohibited in {field_name}.")

    if field_name in ("theme", "dietary", "notes") and not stripped:
        return None

    return stripped


class EventRequest(BaseModel):
    """User input payload requesting an event plan."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    event_type: EventType = Field(description="Category of the event.")
    event_date: date = Field(description="Date of the event; must be in the future.")
    city: str = Field(min_length=1, max_length=80, description="Host city.")
    guest_count: int = Field(ge=1, le=5000, description="Estimated number of guests.")
    total_budget_inr: int = Field(
        ge=10000,
        le=100000000,
        description="Total allocated budget in Indian Rupees.",
    )
    theme: str | None = Field(
        default=None,
        max_length=200,
        description="Optional thematic preference or style.",
    )
    dietary: str | None = Field(
        default=None,
        max_length=200,
        description="Dietary requirements or catering preferences.",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Additional context or custom requests.",
    )
    language: Language = Field(
        default=Language.en,
        description="Output language choice (en, hi, or mr).",
    )

    @field_validator("event_date")
    @classmethod
    def validate_future_date(cls, v: date) -> date:
        """Validate that the event date is strictly in the future.

        Args:
            v: Input date.

        Returns:
            date: Validated future date.

        Raises:
            ValueError: If the event date is today or in the past.
        """
        if v <= date.today():
            raise ValueError("Event date must be in the future.")
        return v

    @field_validator("city", "theme", "dietary", "notes", mode="before")
    @classmethod
    def sanitize_text_fields(cls, v: object, info: ValidationInfo) -> object:
        """Sanitize text fields by stripping whitespace and rejecting control chars.

        Args:
            v: Raw field input value.
            info: Validation information including field name.

        Returns:
            object: Sanitized string value or None.
        """
        field_name = info.field_name or "field"
        return sanitize_text(v, field_name)


class BudgetItem(BaseModel):
    """Detailed allocation within the overall budget."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category: str = Field(min_length=1, max_length=100, description="Expense category.")
    amount_inr: int = Field(ge=0, description="Estimated cost in INR.")
    note: str = Field(
        min_length=1, max_length=500, description="Allocation breakdown context."
    )


class Task(BaseModel):
    """Milestone or action item on the event timeline."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=200, description="Task headline.")
    due_date: date = Field(description="Target completion date.")
    category: str = Field(
        min_length=1, max_length=100, description="Associated phase or category."
    )


class VendorItem(BaseModel):
    """Vendor hiring guidance and vetting questions."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category: str = Field(min_length=1, max_length=100, description="Vendor category.")
    questions: list[str] = Field(
        min_length=2,
        max_length=4,
        description="Essential vetting questions (2-4 items).",
    )
    book_by: date = Field(description="Recommended deadline for booking.")


class Plan(BaseModel):
    """Complete generated event plan."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    budget: list[BudgetItem] = Field(description="Categorized budget breakdown items.")
    timeline: list[Task] = Field(description="Chronological event milestone timeline.")
    vendors: list[VendorItem] = Field(
        description="Vendor hiring checklist and questions."
    )
    ideas: list[str] = Field(
        min_length=5,
        max_length=5,
        description="Personalized ideas and creative recommendations (strictly 5 items).",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Practical warnings, permits, or seasonal cautions.",
    )
