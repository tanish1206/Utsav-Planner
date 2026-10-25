"""Export utilities for event plans including RFC 5545 iCalendar (.ics)."""

import uuid
from datetime import datetime, timezone

from app.schemas import Task


def escape_ics_text(value: str) -> str:
    """Escape text according to RFC 5545 Section 3.3.11.

    Special characters in TEXT values (comma, semicolon, backslash, newlines)
    must be escaped with a backslash.

    Args:
        value: Raw text string.

    Returns:
        str: Escaped RFC 5545 compliant text string.
    """
    if not value:
        return ""
    # Backslash must be escaped first to prevent double-escaping
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace(";", "\\;")
    escaped = escaped.replace(",", "\\,")
    escaped = escaped.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return escaped


def export_ics(tasks: list[Task], event_title: str = "Utsav Event") -> str:
    """Generate a valid RFC 5545 iCalendar string from a timeline of tasks.

    Requirements:
    - Escapes commas, semicolons, backslashes, and newlines.
    - Uses strict CRLF (\\r\\n) line endings.
    - Generates unique UIDs for every VEVENT item.
    - Formats all dates as ISO YYYYMMDD.

    Args:
        tasks: Milestone tasks to export as calendar events.
        event_title: Contextual event title.

    Returns:
        str: RFC 5545 formatted .ics payload with CRLF endings.
    """
    crlf = "\r\n"
    # Using timezone.utc for runtime compatibility across Python versions
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Utsav Planner//Timeline Exporter//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(event_title)} Timeline",
    ]

    for task in tasks:
        event_uid = f"{uuid.uuid4()}@utsavplanner.local"
        dtstart = task.due_date.strftime("%Y%m%d")
        summary = escape_ics_text(task.title)
        description = escape_ics_text(f"Phase: {task.category} | Event: {event_title}")

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event_uid}",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                "STATUS:CONFIRMED",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    lines.append("")  # Trailing CRLF
    return crlf.join(lines)
