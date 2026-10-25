"""Unit tests for Pydantic v2 schemas and payload sanitization."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import (
    BudgetItem,
    EventRequest,
    Plan,
    Task,
    VendorItem,
)


def valid_event_request_data() -> dict:
    """Return dictionary with valid default event request fields."""
    return {
        "event_type": "wedding",
        "event_date": date.today() + timedelta(days=30),
        "city": "Mumbai",
        "guest_count": 200,
        "total_budget_inr": 500000,
        "theme": "Traditional Royal",
        "dietary": "Vegetarian and Jain options",
        "notes": "Prefers evening functions.",
        "language": "en",
    }


# --- 1. Past Date Rejected ---
@pytest.mark.parametrize(
    "date_offset",
    [-10, -1, 0],  # past days and today
)
def test_past_and_today_event_date_rejected(date_offset: int) -> None:
    """Event date must be strictly in the future; past or today is rejected."""
    data = valid_event_request_data()
    data["event_date"] = date.today() + timedelta(days=date_offset)

    with pytest.raises(ValidationError) as exc_info:
        EventRequest(**data)

    errors = exc_info.value.errors()
    assert any(
        "must be in the future" in err["msg"].lower()
        for err in errors
        if "event_date" in err["loc"]
    )


def test_future_event_date_accepted() -> None:
    """Future event date is accepted without error."""
    data = valid_event_request_data()
    data["event_date"] = date.today() + timedelta(days=1)
    req = EventRequest(**data)
    assert req.event_date == date.today() + timedelta(days=1)


# --- 2. Oversized Notes Rejected ---
def test_oversized_notes_rejected() -> None:
    """Notes exceeding 500 characters must raise ValidationError."""
    data = valid_event_request_data()
    data["notes"] = "A" * 501

    with pytest.raises(ValidationError) as exc_info:
        EventRequest(**data)

    errors = exc_info.value.errors()
    assert any("notes" in err["loc"] for err in errors)


def test_valid_notes_length_accepted() -> None:
    """Notes up to 500 characters are accepted."""
    data = valid_event_request_data()
    data["notes"] = "A" * 500
    req = EventRequest(**data)
    assert len(req.notes or "") == 500


# --- 3. Budget Limits Rejected ---
@pytest.mark.parametrize(
    "invalid_budget",
    [0, 5000, 9999, -100],  # below minimum (10,000 INR)
)
def test_budget_below_minimum_rejected(invalid_budget: int) -> None:
    """Total budget below 10,000 INR must raise ValidationError."""
    data = valid_event_request_data()
    data["total_budget_inr"] = invalid_budget

    with pytest.raises(ValidationError) as exc_info:
        EventRequest(**data)

    errors = exc_info.value.errors()
    assert any("total_budget_inr" in err["loc"] for err in errors)


def test_budget_above_maximum_rejected() -> None:
    """Total budget above 100,000,000 INR must raise ValidationError."""
    data = valid_event_request_data()
    data["total_budget_inr"] = 100000001

    with pytest.raises(ValidationError) as exc_info:
        EventRequest(**data)

    errors = exc_info.value.errors()
    assert any("total_budget_inr" in err["loc"] for err in errors)


@pytest.mark.parametrize("valid_budget", [10000, 500000, 100000000])
def test_boundary_budgets_accepted(valid_budget: int) -> None:
    """Budget boundary values 10,000 and 100,000,000 must be accepted."""
    data = valid_event_request_data()
    data["total_budget_inr"] = valid_budget
    req = EventRequest(**data)
    assert req.total_budget_inr == valid_budget


# --- 4. Bad Enum Rejected ---
@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("event_type", "anniversary"),
        ("event_type", "concert"),
        ("event_type", "random_event"),
        ("language", "fr"),
        ("language", "de"),
        ("language", "es"),
    ],
)
def test_bad_enum_rejected(field: str, bad_value: str) -> None:
    """Unsupported enum values for event_type and language are rejected."""
    data = valid_event_request_data()
    data[field] = bad_value

    with pytest.raises(ValidationError) as exc_info:
        EventRequest(**data)

    errors = exc_info.value.errors()
    assert any(field in err["loc"] for err in errors)


# --- 5. Control Characters and Sanitization ---
def test_control_character_in_city_rejected() -> None:
    """Control characters (like null byte or bell) in city must be rejected."""
    data = valid_event_request_data()
    data["city"] = "Mumbai\x00"

    with pytest.raises(ValidationError) as exc_info:
        EventRequest(**data)

    assert any(
        "control characters are prohibited" in err["msg"].lower()
        for err in exc_info.value.errors()
    )


def test_whitespace_stripped_on_request() -> None:
    """Whitespace on string fields must be automatically stripped."""
    data = valid_event_request_data()
    data["city"] = "   Pune   "
    data["theme"] = "   Rustic Garden   "
    req = EventRequest(**data)
    assert req.city == "Pune"
    assert req.theme == "Rustic Garden"


# --- 6. Plan Schema Validations ---
def test_plan_requires_exactly_five_ideas() -> None:
    """Plan schema must enforce exactly 5 ideas."""
    base_budget = [
        BudgetItem(category="Venue", amount_inr=90000, note="Hall"),
        BudgetItem(category="Contingency", amount_inr=10000, note="Contingency"),
    ]
    base_timeline = [
        Task(
            title="Book venue",
            due_date=date(2026, 11, 10),
            category="Planning",
        )
    ]
    base_vendors = [
        VendorItem(
            category="Venue",
            questions=["Capacity?", "Deposit amount?"],
            book_by=date(2026, 11, 10),
        )
    ]

    # 4 ideas should fail
    with pytest.raises(ValidationError):
        Plan(
            budget=base_budget,
            timeline=base_timeline,
            vendors=base_vendors,
            ideas=["Idea 1", "Idea 2", "Idea 3", "Idea 4"],
            warnings=[],
        )

    # 6 ideas should fail
    with pytest.raises(ValidationError):
        Plan(
            budget=base_budget,
            timeline=base_timeline,
            vendors=base_vendors,
            ideas=["1", "2", "3", "4", "5", "6"],
            warnings=[],
        )

    # Exactly 5 ideas must pass
    plan = Plan(
        budget=base_budget,
        timeline=base_timeline,
        vendors=base_vendors,
        ideas=["1", "2", "3", "4", "5"],
        warnings=[],
    )
    assert len(plan.ideas) == 5


def test_vendor_item_questions_count_limits() -> None:
    """Vendor questions list must contain between 2 and 4 items."""
    # 1 question should fail
    with pytest.raises(ValidationError):
        VendorItem(
            category="Venue",
            questions=["Single question?"],
            book_by=date(2026, 11, 10),
        )

    # 5 questions should fail
    with pytest.raises(ValidationError):
        VendorItem(
            category="Venue",
            questions=["Q1?", "Q2?", "Q3?", "Q4?", "Q5?"],
            book_by=date(2026, 11, 10),
        )

    # 3 questions must pass
    vendor = VendorItem(
        category="Venue",
        questions=["Q1?", "Q2?", "Q3?"],
        book_by=date(2026, 11, 10),
    )
    assert len(vendor.questions) == 3
