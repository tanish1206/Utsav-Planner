"""Unit tests for domain validation rules and text sanitization."""

from datetime import date, timedelta

import pytest

from app.schemas import (
    BudgetItem,
    EventRequest,
    EventType,
    Language,
    Plan,
    Task,
    VendorItem,
)
from app.validators import (
    sanitize_text,
    validate_budget_sum,
    validate_plan,
    validate_timeline,
    validate_vendors,
)


def make_dummy_plan(
    budget: list[BudgetItem] | None = None,
    timeline: list[Task] | None = None,
    vendors: list[VendorItem] | None = None,
    ideas: list[str] | None = None,
) -> Plan:
    """Helper factory generating a minimal valid or customized Plan instance."""
    return Plan(
        budget=budget
        if budget is not None
        else [
            BudgetItem(category="Venue", amount_inr=92000, note="Main hall"),
            BudgetItem(category="Contingency", amount_inr=8000, note="Contingency 8%"),
        ],
        timeline=timeline
        if timeline is not None
        else [
            Task(
                title="Book Venue",
                due_date=date(2026, 11, 10),
                category="Logistics",
            ),
            Task(
                title="Send Invites",
                due_date=date(2026, 11, 20),
                category="Guest Mgmt",
            ),
        ],
        vendors=vendors
        if vendors is not None
        else [
            VendorItem(
                category="Venue",
                questions=["Capacity?", "Parking availability?"],
                book_by=date(2026, 11, 10),
            )
        ],
        ideas=ideas
        if ideas is not None
        else [
            "Idea 1: Royal floral arches",
            "Idea 2: Live acoustic sitar player",
            "Idea 3: Custom mithai box favors",
            "Idea 4: Candlelit evening seating",
            "Idea 5: Interactive polaroid guestbook",
        ],
        warnings=[],
    )


# --- 1. sanitize_text Tests ---
@pytest.mark.parametrize(
    ("raw_input", "expected_output"),
    [
        ("Simple clean text", "Simple clean text"),
        ("   Spaced   out   words  \n\t  ", "Spaced out words"),
        ("Hello\x00\x08World\x07!", "HelloWorld!"),
        ("\x1b[31mRed\x1b[0m Alert", "[31mRed[0m Alert"),
        ("", ""),
        ("   \t\r\n   ", ""),
    ],
)
def test_sanitize_text(raw_input: str, expected_output: str) -> None:
    """Verify that control characters are stripped and whitespace normalized."""
    assert sanitize_text(raw_input) == expected_output


# --- 2. validate_budget_sum Tests ---
@pytest.mark.parametrize(
    ("total", "items", "expected_valid", "error_fragment"),
    [
        # Passing: sum matches, contingency = 8%
        (
            100000,
            [
                BudgetItem(category="Venue", amount_inr=92000, note="Hall"),
                BudgetItem(category="Contingency", amount_inr=8000, note="Reserve"),
            ],
            True,
            None,
        ),
        # Exact-boundary passing: contingency is exactly 5% (5000)
        (
            100000,
            [
                BudgetItem(category="Venue", amount_inr=95000, note="Hall"),
                BudgetItem(category="Contingency", amount_inr=5000, note="Min reserve"),
            ],
            True,
            None,
        ),
        # Exact-boundary passing: contingency is exactly 10% (10000)
        (
            100000,
            [
                BudgetItem(category="Venue", amount_inr=90000, note="Hall"),
                BudgetItem(
                    category="Contingency", amount_inr=10000, note="Max reserve"
                ),
            ],
            True,
            None,
        ),
        # Failing: Off-by-one rupee high (100001 != 100000)
        (
            100000,
            [
                BudgetItem(category="Venue", amount_inr=92001, note="Hall"),
                BudgetItem(category="Contingency", amount_inr=8000, note="Reserve"),
            ],
            False,
            "does not match required total",
        ),
        # Failing: Off-by-one rupee low (99999 != 100000)
        (
            100000,
            [
                BudgetItem(category="Venue", amount_inr=91999, note="Hall"),
                BudgetItem(category="Contingency", amount_inr=8000, note="Reserve"),
            ],
            False,
            "does not match required total",
        ),
        # Failing: Missing contingency line
        (
            100000,
            [BudgetItem(category="Venue", amount_inr=100000, note="Full budget")],
            False,
            "contingency allocation is required",
        ),
        # Failing: Contingency off-by-one low (4999 < 5000 = 5%)
        (
            100000,
            [
                BudgetItem(category="Venue", amount_inr=95001, note="Hall"),
                BudgetItem(category="Contingency", amount_inr=4999, note="Under min"),
            ],
            False,
            "must be between 5%",
        ),
        # Failing: Contingency off-by-one high (10001 > 10000 = 10%)
        (
            100000,
            [
                BudgetItem(category="Venue", amount_inr=89999, note="Hall"),
                BudgetItem(category="Contingency", amount_inr=10001, note="Over max"),
            ],
            False,
            "must be between 5%",
        ),
        # Edge case: Empty budget list
        (
            100000,
            [],
            False,
            "cannot be empty",
        ),
    ],
)
def test_validate_budget_sum(
    total: int,
    items: list[BudgetItem],
    expected_valid: bool,
    error_fragment: str | None,
) -> None:
    """Parametrized testing of budget sum, boundaries, and contingency rules."""
    plan = make_dummy_plan(budget=items)
    errors = validate_budget_sum(plan, total)
    if expected_valid:
        assert not errors
    else:
        assert len(errors) >= 1
        assert any(error_fragment.lower() in err.lower() for err in errors)


# --- 3. validate_timeline Tests ---
@pytest.mark.parametrize(
    ("due_dates", "event_offset", "expected_valid", "error_fragment"),
    [
        # Passing: all dates between today and event_date, sorted ascending
        ([5, 15, 25], 30, True, None),
        # Exact-boundary passing: first task on today, last task on event_date
        ([0, 15, 30], 30, True, None),
        # Failing: due date in the past (before today)
        ([-1, 10, 20], 30, False, "cannot be in the past"),
        # Failing: due date after event date
        ([10, 20, 35], 30, False, "cannot be after event date"),
        # Failing: unsorted dates (20 before 10)
        ([20, 10, 25], 30, False, "must be sorted in ascending order"),
        # Edge case: empty timeline
        ([], 30, False, "cannot be empty"),
    ],
)
def test_validate_timeline(
    due_dates: list[int],
    event_offset: int,
    expected_valid: bool,
    error_fragment: str | None,
) -> None:
    """Parametrized testing of timeline milestones, order, and boundaries."""
    today = date(2026, 11, 1)
    event_date = today + timedelta(days=event_offset)

    tasks = [
        Task(
            title=f"Task {i}",
            due_date=today + timedelta(days=offset),
            category="Planning",
        )
        for i, offset in enumerate(due_dates)
    ]
    plan = make_dummy_plan(timeline=tasks)
    errors = validate_timeline(plan, event_date, today)

    if expected_valid:
        assert not errors
    else:
        assert len(errors) >= 1
        assert any(error_fragment.lower() in err.lower() for err in errors)


# --- 4. validate_vendors Tests ---
@pytest.mark.parametrize(
    ("event_type", "category", "book_by_offset", "expected_valid", "error_fragment"),
    [
        # Passing cases for each event type
        (EventType.wedding, "Venue", 10, True, None),
        (EventType.wedding, "Catering", 20, True, None),
        (EventType.wedding, "Mehendi", 25, True, None),
        (EventType.birthday, "Cake & Bakery", 15, True, None),
        (EventType.birthday, "Entertainment", 20, True, None),
        (EventType.community, "Sound & AV", 10, True, None),
        (EventType.community, "Security", 15, True, None),
        # Exact-boundary passing: book_by exactly on event date
        (EventType.wedding, "Photography", 30, True, None),
        # Failing: Invalid category for wedding (e.g. sanitation)
        (EventType.wedding, "Sanitation", 10, False, "not permitted for wedding"),
        # Failing: Invalid category for birthday (e.g. priest/officiant)
        (
            EventType.birthday,
            "Priest / Officiant",
            10,
            False,
            "not permitted for birthday",
        ),
        # Failing: book_by deadline after event date (offset 35 > 30)
        (EventType.wedding, "Venue", 35, False, "cannot be after event date"),
        # Failing: Unknown event type string
        ("space_party", "Venue", 10, False, "Invalid event type"),
    ],
)
def test_validate_vendors(
    event_type: EventType | str,
    category: str,
    book_by_offset: int,
    expected_valid: bool,
    error_fragment: str | None,
) -> None:
    """Parametrized testing of vendor category rules and booking deadlines."""
    event_date = date(2026, 12, 1)
    vendors = [
        VendorItem(
            category=category,
            questions=["What packages do you offer?", "Cancellation policy?"],
            book_by=date(2026, 11, 1) + timedelta(days=book_by_offset),
        )
    ]
    plan = make_dummy_plan(vendors=vendors)
    errors = validate_vendors(plan, event_type, event_date)

    if expected_valid:
        assert not errors
    else:
        assert len(errors) >= 1
        assert any(error_fragment.lower() in err.lower() for err in errors)


def test_validate_vendors_empty_list() -> None:
    """Verify that an empty vendor list generates a validation error."""
    plan = make_dummy_plan(vendors=[])
    errors = validate_vendors(plan, EventType.wedding, date(2026, 12, 1))
    assert len(errors) == 1
    assert "cannot be empty" in errors[0].lower()


# --- 5. validate_plan Integration Tests ---
def test_validate_plan_success() -> None:
    """Verify valid complete plan against a matching EventRequest."""
    today = date(2026, 11, 1)
    event_date = date(2026, 12, 1)
    request = EventRequest(
        event_type=EventType.wedding,
        event_date=event_date,
        city="Mumbai",
        guest_count=150,
        total_budget_inr=100000,
        theme="Traditional Royal",
        language=Language.en,
    )
    plan = make_dummy_plan()
    errors = validate_plan(plan, request, today)
    assert not errors


def test_validate_plan_combined_failures() -> None:
    """Verify that validate_plan aggregates multiple validation errors."""
    today = date(2026, 11, 1)
    event_date = date(2026, 12, 1)
    request = EventRequest(
        event_type=EventType.wedding,
        event_date=event_date,
        city="Mumbai",
        guest_count=150,
        total_budget_inr=200000,  # plan only sums to 100000
    )
    plan = make_dummy_plan(
        timeline=[
            Task(
                title="Past task",
                due_date=date(2026, 10, 15),  # before today
                category="Old",
            )
        ],
        vendors=[
            VendorItem(
                category="Sanitation",  # disallowed for wedding
                questions=["Price?", "Timeline?"],
                book_by=date(2026, 12, 5),  # after event date
            )
        ],
    )
    errors = validate_plan(plan, request, today)
    assert len(errors) >= 3
    joined = " ".join(errors)
    assert "does not match required total" in joined
    assert "cannot be in the past" in joined
    assert "not permitted for wedding" in joined
    assert "cannot be after event date" in joined


def test_validate_vendors_without_event_date() -> None:
    """Verify validate_vendors functions when event_date is omitted."""
    plan = make_dummy_plan()
    errors = validate_vendors(plan, EventType.wedding, event_date=None)
    assert not errors


def test_validate_plan_ideas_count_mismatch() -> None:
    """Verify that validate_plan catches plans with an invalid idea count."""
    today = date(2026, 11, 1)
    request = EventRequest(
        event_type=EventType.wedding,
        event_date=date(2026, 12, 1),
        city="Mumbai",
        guest_count=100,
        total_budget_inr=100000,
    )
    # Using model_construct to simulate unexpected LLM payload bypassing schema limits
    plan = Plan.model_construct(
        budget=make_dummy_plan().budget,
        timeline=make_dummy_plan().timeline,
        vendors=make_dummy_plan().vendors,
        ideas=["Idea 1", "Idea 2"],
        warnings=[],
    )
    errors = validate_plan(plan, request, today)
    assert any("must contain exactly 5 ideas" in err for err in errors)
