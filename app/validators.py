"""Domain validation rules and text sanitization for Utsav Planner."""

import re
import unicodedata
from datetime import date

from app.schemas import EventRequest, EventType, Plan

ALLOWED_VENDOR_CATEGORIES: dict[EventType, set[str]] = {
    EventType.wedding: {
        "venue",
        "catering",
        "photography",
        "videography",
        "decoration",
        "florist",
        "music_dj",
        "makeup_hair",
        "mehendi",
        "invitations",
        "priest_officiant",
        "transport",
        "attire",
    },
    EventType.birthday: {
        "venue",
        "catering",
        "cake_bakery",
        "decoration",
        "entertainment",
        "photography",
        "music_dj",
        "party_favors",
        "invitations",
    },
    EventType.community: {
        "venue",
        "catering",
        "sound_av",
        "decoration",
        "security",
        "stage_seating",
        "sanitation",
        "photography",
        "permits",
        "waste_management",
    },
}

CATEGORY_ALIASES: dict[str, str] = {
    "decor": "decoration",
    "cake": "cake_bakery",
    "bakery": "cake_bakery",
    "dj": "music_dj",
    "music": "music_dj",
    "sound": "sound_av",
    "av": "sound_av",
    "sound_lighting": "sound_av",
    "makeup": "makeup_hair",
    "hair": "makeup_hair",
    "priest": "priest_officiant",
    "officiant": "priest_officiant",
    "pandit": "priest_officiant",
    "seating": "stage_seating",
    "stage": "stage_seating",
}


def sanitize_text(s: str) -> str:
    """Strip control characters and normalize internal whitespace.

    Args:
        s: Raw input text.

    Returns:
        str: Sanitized text with control characters removed and normalized spaces.
    """
    if not s:
        return ""
    s_spaced = s.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    cleaned_chars = [
        char
        for char in s_spaced
        if not (
            unicodedata.category(char) in ("Cc", "Cf")
            or ord(char) < 32
            or ord(char) == 127
        )
    ]
    return " ".join("".join(cleaned_chars).split())


def _normalize_category(category: str) -> str:
    """Normalize category name for robust lookup.

    Args:
        category: Raw category string.

    Returns:
        str: Normalized category identifier.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "_", category.strip().lower()).strip("_")
    return CATEGORY_ALIASES.get(cleaned, cleaned)


def validate_budget_sum(plan: Plan, total: int) -> list[str]:
    """Validate that budget items sum to total and contain a valid contingency line.

    Requirements:
    - Sum of all BudgetItem amount_inr must equal total exactly.
    - A 'contingency' category item must be present.
    - Contingency must be between 5% and 10% of total budget inclusive.

    Args:
        plan: Event plan containing budget allocations.
        total: Expected total budget in INR.

    Returns:
        list[str]: Validation error messages, empty if valid.
    """
    errors: list[str] = []

    if not plan.budget:
        errors.append("Budget allocation list cannot be empty.")
        return errors

    actual_sum = sum(item.amount_inr for item in plan.budget)
    if actual_sum != total:
        errors.append(
            f"Budget sum of {actual_sum} INR does not match required total of {total} INR."
        )

    contingency_items = [
        item
        for item in plan.budget
        if "contingency" in item.category.strip().lower()
        or item.category.strip().lower() == "contingency"
    ]

    if not contingency_items:
        errors.append("A contingency allocation is required in the budget.")
    else:
        contingency_sum = sum(item.amount_inr for item in contingency_items)
        # 5% to 10% using integer arithmetic
        min_allowed = (total * 5) // 100
        max_allowed = (total * 10) // 100
        if contingency_sum * 100 < total * 5 or contingency_sum * 100 > total * 10:
            errors.append(
                f"Contingency allocation ({contingency_sum} INR) must be between "
                f"5% ({min_allowed} INR) and 10% ({max_allowed} INR) of total budget."
            )

    return errors


def validate_timeline(plan: Plan, event_date: date, today: date) -> list[str]:
    """Validate timeline milestone constraints and ascending order.

    Requirements:
    - All task due dates must be >= today.
    - All task due dates must be <= event_date.
    - Tasks must be sorted in ascending chronological order.

    Args:
        plan: Event plan containing timeline tasks.
        event_date: Target event date.
        today: Reference current date.

    Returns:
        list[str]: Validation error messages, empty if valid.
    """
    errors: list[str] = []

    if not plan.timeline:
        errors.append("Timeline tasks list cannot be empty.")
        return errors

    for task in plan.timeline:
        if task.due_date < today:
            errors.append(
                f"Task '{task.title}' due date ({task.due_date}) cannot be in the past before {today}."
            )
        if task.due_date > event_date:
            errors.append(
                f"Task '{task.title}' due date ({task.due_date}) cannot be after event date {event_date}."
            )

    for i in range(len(plan.timeline) - 1):
        if plan.timeline[i].due_date > plan.timeline[i + 1].due_date:
            errors.append(
                "Timeline tasks must be sorted in ascending order by due date."
            )
            break

    return errors


def validate_vendors(
    plan: Plan,
    event_type: EventType | str,
    event_date: date | None = None,
) -> list[str]:
    """Validate vendor categories for event type and booking deadlines.

    Requirements:
    - Vendor categories must belong to the allowed categories for event_type.
    - If event_date is provided, book_by must be <= event_date.

    Args:
        plan: Event plan containing vendor checklist.
        event_type: Event category (wedding, birthday, or community).
        event_date: Optional event date for deadline verification.

    Returns:
        list[str]: Validation error messages, empty if valid.
    """
    errors: list[str] = []

    if not plan.vendors:
        errors.append("Vendor checklist cannot be empty.")
        return errors

    if isinstance(event_type, str):
        try:
            event_type = EventType(event_type)
        except ValueError:
            errors.append(f"Invalid event type: '{event_type}'.")
            return errors

    allowed_categories = ALLOWED_VENDOR_CATEGORIES.get(event_type, set())

    for vendor in plan.vendors:
        norm_cat = _normalize_category(vendor.category)
        if norm_cat not in allowed_categories:
            errors.append(
                f"Vendor category '{vendor.category}' is not permitted for {event_type.value} events."
            )

        if event_date is not None and vendor.book_by > event_date:
            errors.append(
                f"Vendor '{vendor.category}' booking deadline ({vendor.book_by}) "
                f"cannot be after event date {event_date}."
            )

    return errors


def validate_plan(plan: Plan, request: EventRequest, today: date) -> list[str]:
    """Validate an entire generated plan against user request constraints.

    Args:
        plan: Generated event plan.
        request: Original event request.
        today: Reference current date.

    Returns:
        list[str]: Combined validation error messages.
    """
    errors: list[str] = []
    errors.extend(validate_budget_sum(plan, request.total_budget_inr))
    errors.extend(validate_timeline(plan, request.event_date, today))
    errors.extend(validate_vendors(plan, request.event_type, request.event_date))

    if len(plan.ideas) != 5:
        errors.append(f"Plan must contain exactly 5 ideas, found {len(plan.ideas)}.")

    return errors
