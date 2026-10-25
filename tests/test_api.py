"""Integration and security tests for FastAPI endpoints, headers, and rate limiting."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.llm import PlanGenerationError, get_plan_cache
from app.main import app
from app.schemas import (
    BudgetItem,
    EventRequest,
    Plan,
    Task,
    VendorItem,
)


def make_mock_plan(total_budget: int = 100000) -> Plan:
    """Helper creating a fully populated valid Plan."""
    contingency = int(total_budget * 0.08)
    venue = total_budget - contingency
    return Plan(
        budget=[
            BudgetItem(category="Venue", amount_inr=venue, note="Grand Hall"),
            BudgetItem(
                category="Contingency",
                amount_inr=contingency,
                note="Reserve 8%",
            ),
        ],
        timeline=[
            Task(
                title="Book Banquet Hall",
                due_date=date(2026, 11, 10),
                category="Venue",
            ),
            Task(
                title="Confirm Catering Menu",
                due_date=date(2026, 11, 15),
                category="Catering",
            ),
            Task(
                title="Finalize Photographer",
                due_date=date(2026, 11, 20),
                category="Media",
            ),
        ],
        vendors=[
            VendorItem(
                category="Venue",
                questions=["Capacity limit?", "Curfew time?"],
                book_by=date(2026, 11, 10),
            )
        ],
        ideas=[
            "Idea 1: Royal Marigold Entrance",
            "Idea 2: Live Classical Sitar Recital",
            "Idea 3: Artisan Mithai Favors",
            "Idea 4: Candlelit Evening Courtyard",
            "Idea 5: Instant Polaroid Memory Wall",
        ],
        warnings=["Check outdoor noise permits after 10:00 PM."],
    )


@pytest.fixture
def valid_request_payload() -> dict[str, Any]:
    """Valid event planning JSON payload."""
    return {
        "event_type": "wedding",
        "event_date": (date.today() + timedelta(days=30)).isoformat(),
        "city": "Jaipur",
        "guest_count": 150,
        "total_budget_inr": 100000,
        "theme": "Royal Rajasthani",
        "dietary": "Pure vegetarian",
        "notes": "Evening banquet preferred.",
        "language": "en",
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """TestClient fixture with test settings and fresh plan cache."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    get_plan_cache().clear()
    app.state.limiter.reset()
    yield TestClient(app, raise_server_exceptions=False)
    app.state.limiter.reset()


# --- 1. Successful Plan Generation ---
def test_create_plan_success(
    client: TestClient,
    valid_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/plan returns HTTP 200 and structured Plan response."""
    mock_plan = make_mock_plan(valid_request_payload["total_budget_inr"])
    monkeypatch.setattr("app.main.generate_plan", lambda _payload: mock_plan)

    response = client.post("/api/plan", json=valid_request_payload)

    assert response.status_code == 200
    data = response.json()
    assert len(data["budget"]) == 2
    assert len(data["timeline"]) == 3
    assert len(data["ideas"]) == 5
    assert data["ideas"][0] == "Idea 1: Royal Marigold Entrance"


# --- 2. 422 on Bad Input ---
@pytest.mark.parametrize(
    ("bad_payload", "error_field"),
    [
        (
            {
                "event_type": "wedding",
                "event_date": "2020-01-01",  # Past date
                "city": "Mumbai",
                "guest_count": 50,
                "total_budget_inr": 50000,
            },
            "event_date",
        ),
        (
            {
                "event_type": "invalid_festival",  # Bad enum
                "event_date": (date.today() + timedelta(days=20)).isoformat(),
                "city": "Mumbai",
                "guest_count": 50,
                "total_budget_inr": 50000,
            },
            "event_type",
        ),
        (
            {
                "event_type": "birthday",
                "event_date": (date.today() + timedelta(days=20)).isoformat(),
                "city": "Mumbai",
                "guest_count": 50,
                "total_budget_inr": 5000,  # Below min (10,000)
            },
            "total_budget_inr",
        ),
    ],
)
def test_create_plan_validation_error_format(
    client: TestClient, bad_payload: dict[str, Any], error_field: str
) -> None:
    """POST /api/plan with invalid payload returns 422 with friendly JSON errors without stack trace."""
    response = client.post("/api/plan", json=bad_payload)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert "errors" in data
    assert any(error_field in err["field"] for err in data["errors"])
    # Ensure no internal stack trace leaked
    assert "Traceback" not in response.text


# --- 3. 429 After Rate Limit ---
def test_rate_limit_exceeded(
    client: TestClient,
    valid_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exceeding configured rate limit triggers 429 Too Many Requests."""
    mock_plan = make_mock_plan(valid_request_payload["total_budget_inr"])
    monkeypatch.setattr("app.main.generate_plan", lambda _payload: mock_plan)

    # Config has rate_limit="10/minute" or "5/minute". Submitting 15 calls:
    statuses = []
    for _ in range(15):
        res = client.post("/api/plan", json=valid_request_payload)
        statuses.append(res.status_code)

    assert 429 in statuses
    last_res = client.post("/api/plan", json=valid_request_payload)
    assert last_res.status_code == 429
    assert last_res.json()["error_type"] == "RateLimitExceeded"


# --- 4. Security Headers Present ---
def test_security_headers_present(client: TestClient) -> None:
    """All HTTP responses must enforce required security and isolation headers."""
    response = client.get("/")

    assert response.status_code == 200
    headers = response.headers

    # Content-Security-Policy (default-src 'self', no inline scripts)
    assert "Content-Security-Policy" in headers
    csp = headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]

    # X-Content-Type-Options: nosniff
    assert headers.get("X-Content-Type-Options") == "nosniff"

    # X-Frame-Options: DENY
    assert headers.get("X-Frame-Options") == "DENY"

    # Referrer-Policy: no-referrer
    assert headers.get("Referrer-Policy") == "no-referrer"

    # Permissions-Policy
    assert "Permissions-Policy" in headers
    assert "camera=()" in headers["Permissions-Policy"]


# --- 5. .ics Parses and Has Correct Event Count ---
def test_export_ics_parses_and_event_count(
    client: TestClient,
    valid_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/plan/ics produces a valid RFC 5545 .ics stream with correct event count."""
    mock_plan = make_mock_plan(valid_request_payload["total_budget_inr"])
    # Seed the cache so export_plan_ics can fetch it
    cache = get_plan_cache()
    cache.set("mock-cache-key", mock_plan)

    monkeypatch.setattr("app.main.generate_plan", lambda _payload: mock_plan)

    response = client.get("/api/plan/ics")

    assert response.status_code == 200
    assert "text/calendar" in response.headers["Content-Type"]
    assert (
        'attachment; filename="utsav_timeline.ics"'
        in response.headers["Content-Disposition"]
    )

    content = response.text
    # RFC 5545 structural requirements
    assert content.startswith("BEGIN:VCALENDAR\r\n")
    assert content.endswith("END:VCALENDAR\r\n")
    assert "\r\n" in content  # Strict CRLF verification

    # Count of VEVENT must match timeline length
    event_count = content.count("BEGIN:VEVENT")
    assert event_count == len(mock_plan.timeline)
    assert content.count("END:VEVENT") == len(mock_plan.timeline)

    # Verify task contents are present
    assert "SUMMARY:Book Banquet Hall" in content
    assert "SUMMARY:Confirm Catering Menu" in content


def test_export_ics_404_when_no_plan_cached(client: TestClient) -> None:
    """GET /api/plan/ics returns 404 when no plan is found in cache."""
    get_plan_cache().clear()
    response = client.get("/api/plan/ics")
    assert response.status_code == 404
    assert "No event plan found" in response.json()["detail"]


# --- 6. Error Response Leaks Nothing ---
def test_global_exception_handler_leaks_nothing(
    client: TestClient,
    valid_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unhandled exceptions must return generic 500 error with request_id and leak no traces."""

    def broken_generator(_payload: EventRequest) -> Plan:
        raise RuntimeError(
            "SensitiveDatabaseSecret: jdbc://admin:supersecret@10.0.0.1:5432"
        )

    monkeypatch.setattr("app.main.generate_plan", broken_generator)

    response = client.post("/api/plan", json=valid_request_payload)

    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "An unexpected error occurred. Please try again later."
    assert "request_id" in data
    # Ensure confidential details / stack trace are never returned
    assert "SensitiveDatabaseSecret" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


def test_plan_generation_error_handled_safely(
    client: TestClient,
    valid_request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Domain PlanGenerationError returns friendly 422 with validation errors."""

    def failing_generator(_payload: EventRequest) -> Plan:
        raise PlanGenerationError(
            "Plan failed constraints",
            errors=["Budget sum does not match", "Contingency line missing"],
        )

    monkeypatch.setattr("app.main.generate_plan", failing_generator)

    response = client.post("/api/plan", json=valid_request_payload)

    assert response.status_code == 422
    data = response.json()
    assert "Unable to generate a plan satisfying all criteria." in data["detail"]
    assert "Budget sum does not match" in data["errors"]
    assert "Contingency line missing" in data["errors"]


# --- 7. Request Body Size Limit ---
def test_request_body_size_limit_exceeded(client: TestClient) -> None:
    """Requests exceeding 64KB are rejected with 413 Payload Too Large."""
    oversized_headers = {"Content-Length": str(65 * 1024)}
    response = client.post("/api/plan", headers=oversized_headers, content=b"x" * 100)
    assert response.status_code == 413
    assert "Request body too large" in response.json()["detail"]


# --- 8. Health Check Endpoint ---
def test_healthz_endpoint(client: TestClient) -> None:
    """GET /healthz returns status 200 OK."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
