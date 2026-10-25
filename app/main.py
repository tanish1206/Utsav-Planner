"""FastAPI application entrypoint, security middlewares, and route handlers."""

import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.exporters import export_ics
from app.llm import PlanGenerationError, generate_plan, get_plan_cache
from app.schemas import EventRequest, Plan

logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI App
app = FastAPI(
    title="Utsav Planner",
    description="GenAI planning assistant for weddings, birthdays, and community events",
    version="0.1.0",
)
app.state.limiter = limiter

# Base Paths for Static & Templates
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 2. Maximum Payload Size Limit (64 KB)
MAX_BODY_SIZE = 64 * 1024


@app.middleware("http")
async def body_size_limit_middleware(request: Request, call_next: Any) -> Response:
    """Reject requests with payloads exceeding maximum body size limit."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_SIZE:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large. Maximum size is 64KB."},
        )
    return await call_next(request)


# 3. Security Headers Middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next: Any) -> Response:
    """Enforce strict security headers across all responses."""
    response: Response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    return response


# --- Exception Handlers ---
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(
    _request: Request, _exc: RateLimitExceeded
) -> JSONResponse:
    """Return friendly rate limit exceeded response."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please wait before submitting more requests.",
            "error_type": "RateLimitExceeded",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return clean, friendly validation errors without internal trace leakage."""
    error_list = []
    for err in exc.errors():
        field_path = " -> ".join(str(elem) for elem in err.get("loc", []))
        message = err.get("msg", "Validation error")
        error_list.append({"field": field_path, "message": message})

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Invalid input provided.",
            "errors": error_list,
        },
    )


@app.exception_handler(PlanGenerationError)
async def plan_generation_exception_handler(
    _request: Request, exc: PlanGenerationError
) -> JSONResponse:
    """Handle domain plan generation errors safely without user data leakage."""
    req_id = str(uuid.uuid4())
    logger.error("PlanGenerationError [request_id=%s]: %s", req_id, type(exc).__name__)
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Unable to generate a plan satisfying all criteria.",
            "errors": exc.errors if exc.errors else [str(exc)],
            "request_id": req_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    """Global exception handler returning generic message and logging only metadata."""
    req_id = str(uuid.uuid4())
    logger.error("Unhandled exception [request_id=%s]: %s", req_id, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred. Please try again later.",
            "request_id": req_id,
        },
    )


# --- Routes ---
@app.get("/", response_class=HTMLResponse)
def index_view(request: Request) -> Response:
    """Render the accessible planning form landing page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/healthz")
def health_check() -> dict[str, str]:
    """Lightweight health check endpoint for monitoring."""
    return {"status": "ok", "app": "Utsav Planner", "version": "0.1.0"}


@app.post("/api/plan", response_model=Plan)
@limiter.limit(settings.rate_limit)
def create_plan(request: Request, payload: EventRequest) -> Plan:
    """Generate a validated celebration plan from user requirements.

    Args:
        request: FastAPI HTTP request for rate-limiting.
        payload: Validated event planning input payload.

    Returns:
        Plan: Structured celebration plan.
    """
    _ = request  # consumed by slowapi rate limiter
    return generate_plan(payload)


@app.get("/api/plan/ics", response_class=Response)
def export_plan_ics(
    cache_key: str | None = Query(
        default=None, description="Cache key of the generated plan"
    ),
    event_title: str = Query(
        default="Utsav Event", description="Title for exported calendar items"
    ),
) -> Response:
    """Export the event plan timeline as an RFC 5545 .ics calendar file.

    Args:
        cache_key: Optional hash key of the generated plan.
        event_title: Contextual headline for calendar events.

    Returns:
        Response: iCalendar file stream with attachment disposition.
    """
    cache = get_plan_cache()
    plan: Plan | None = cache.get(cache_key) if cache_key else cache.get_latest()

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="No event plan found. Please generate a plan before exporting.",
        )

    ics_content = export_ics(plan.timeline, event_title=event_title)
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": 'attachment; filename="utsav_timeline.ics"',
            "Cache-Control": "no-cache",
        },
    )
