# Utsav Planner

**Utsav Planner** is a high-assurance, production-grade GenAI planning assistant for Indian weddings, birthdays, and community celebrations. Built with Python 3.12, FastAPI, Pydantic v2, and the official Google Gemini SDK (`google-genai`), the system synthesizes personalized event plans while enforcing strict architectural boundaries: **the LLM proposes, deterministic code verifies**.

---

## Table of Contents
1. [Problem Statement & The 4 Core Outputs](#problem-statement--the-4-core-outputs)
2. [Architectural Principle: LLM Proposes, Code Verifies](#architectural-principle-llm-proposes-code-verifies)
3. [System Architecture Diagram](#system-architecture-diagram)
4. [Security Measures](#security-measures)
5. [Efficiency & Performance Decisions](#efficiency--performance-decisions)
6. [Accessibility & Theme Contrast System](#accessibility--theme-contrast-system)
7. [Installation, Testing & Deployment](#installation-testing--deployment)
8. [Known Limitations](#known-limitations)

---

## Problem Statement & The 4 Core Outputs

Planning cultural and milestone events in India (weddings, milestone birthdays, and community festivals) is fraught with fragmented budgets, unpredictable vendor vetting, and complex schedules. General-purpose LLMs hallucinate inaccurate budget sums, recommend out-of-order milestones, and miss regional logistical nuances.

Utsav Planner solves this by generating **four strictly verified outputs**:

| Output | Description | Deterministic Constraints Enforced |
| :--- | :--- | :--- |
| **1. Budget Breakdown** | Granular financial allocation matching the exact user budget. | &bull; Sum of all items must equal `total_budget_inr` exactly.<br>&bull; A dedicated **Contingency** line is mandatory.<br>&bull; Contingency must account for **5% to 10%** of total budget (computed via integer math). |
| **2. Timeline & Milestones** | Chronological schedule of event milestones. | &bull; Every due date must be on or after today.<br>&bull; Every due date must be on or before the event date.<br>&bull; Milestones must be strictly sorted ascending (earliest first). |
| **3. Vendor Checklist** | Tailored vendor hiring guidance and vetting questions. | &bull; Categories are restricted strictly to the event type (e.g., priests/mehendi for weddings; magicians for birthdays).<br>&bull; Exactly 2 to 4 actionable vetting questions per vendor.<br>&bull; Booking deadline (`book_by`) must precede the event date. |
| **4. Personalized Ideas** | High-impact creative and cultural recommendations. | &bull; Exactly **5 distinct ideas** reflecting theme, city, budget tier, and dietary needs.<br>&bull; Practical logistical/seasonal cautions documented in `warnings`. |

---

## Architectural Principle: LLM Proposes, Code Verifies

Modern LLMs cannot be trusted to perform deterministic arithmetic or enforce strict ordering on their own. Utsav Planner treats the model as an **untrusted generator** and applies a resilient verification pipeline:

```
[ User Input ] ──> [ Pydantic Request Validation ] ──> [ SHA-256 Hash TTL Cache ]
                                                              │
                                       ┌──────────────────────┴──────────────────────┐
                                [ Cache Hit ]                                 [ Cache Miss ]
                                       │                                             │
                                [ Return Plan ]                         [ Structured Gemini Call ]
                                                                                     │
                                                                           [ Pydantic JSON Parse ]
                                                                                     │
                                                                          [ Pure Code Validators ]
                                                                                     │
                                                       ┌─────────────────────────────┴─────────────────────────────┐
                                                   [ Valid ]                                                   [ Invalid ]
                                                       │                                                           │
                                              [ Store in Cache ]                                       [ Single Automated Retry ]
                                                       │                                                (with feedback appended)
                                                [ Return Plan ]                                                    │
                                                                                                      [ Re-validate in Code ]
                                                                                                                   │
                                                                                                       ┌───────────┴───────────┐
                                                                                                   [ Valid ]               [ Invalid ]
                                                                                                       │                       │
                                                                                                [ Cache & Return ]   [ PlanGenerationError ]
```

1. **Structured Output Enforcement**: Calls Gemini with `response_schema = Plan` and `response_mime_type = "application/json"`.
2. **Pure Code Validation**: The generated payload is immediately evaluated by `validate_plan()`:
   - `validate_budget_sum()` verifies exact sum and contingency percentages.
   - `validate_timeline()` verifies date boundaries and chronological order.
   - `validate_vendors()` verifies category whitelists for the selected event type.
3. **Single Automated Retry**: If any validator flags an error on attempt 1, the model is called a second time with the exact validation violations appended in a `<validation_errors>` block.
4. **Hard Failure Mode**: If attempt 2 still violates domain rules, the call raises `PlanGenerationError` rather than serving invalid financial or scheduling data to the user.

---

## System Architecture Diagram

```
+---------------------------------------------------------------------------------------+
|                                    CLIENT TIER                                        |
|  Accessible Web Interface (WCAG AAA)                                                  |
|  - Vanilla JavaScript (Zero innerHTML, strict textContent rendering)                   |
|  - ARIA tablist with Arrow-Key navigation (Budget | Timeline | Vendors | Ideas)       |
|  - Accessible error summary box receiving programmatic focus on validation failure    |
+-------------------------------------------+-------------------------------------------+
                                            |  HTTPS (JSON / Form Data)
                                            v
+---------------------------------------------------------------------------------------+
|                                   FASTAPI SERVER                                      |
|                                                                                       |
|  [Security Headers Middleware]                                                        |
|  - CSP: default-src 'self'; script-src 'self'; (Zero inline scripts)                  |
|  - X-Content-Type-Options: nosniff | X-Frame-Options: DENY | Referrer-Policy: none     |
|                                                                                       |
|  [Body Size Limit Middleware]                                                         |
|  - Rejects payloads > 64 KB (HTTP 413)                                                |
|                                                                                       |
|  [Rate Limiter (slowapi)]                                                             |
|  - Dynamic threshold via RATE_LIMIT env var (HTTP 429 on exhaustion)                   |
|                                                                                       |
|  [Pydantic v2 Ingestion & Sanitization]                                               |
|  - Rejects control characters, strips whitespace, validates future event date         |
+---------------------+-----------------------------------------------------------------+
                      |
        +-------------+-------------+
        |                           |
        v                           v
+------------------+     +--------------------------------------------------------------+
|  PLAN TTL CACHE  |     |                       LLM SERVICE LAYER                      |
|                  |     |                                                              |
|  In-Memory FIFO  |     |  [Prompt Security & Isolation]                               |
|  Key: SHA-256    |     |  - Encloses untrusted inputs in <user_data>                  |
|  Payload Hash    |     |  - Escapes closing </user_data> tags via regex               |
|  Configurable    |     |                                                              |
|  TTL & Capacity  |     |  [Official google-genai SDK]                                 |
+------------------+     |  - Pydantic Response Schema: Plan                            |
                         |  - Timeout: 30,000 ms                                        |
                         |  - Max Output Tokens: 4096 (configurable)                    |
                         +------------------------------+-------------------------------+
                                                        |
                                                        v
                         +--------------------------------------------------------------+
                         |                 DETERMINISTIC VALIDATION                     |
                         |                                                              |
                         |  - validate_budget_sum()  (Integer arithmetic, 5-10% reserve)|
                         |  - validate_timeline()    (Ascending order, bounded dates)   |
                         |  - validate_vendors()     (Whitelisted categories per type)  |
                         +------------------------------+-------------------------------+
                                                        |
                                                        v
+---------------------------------------------------------------------------------------+
|                                    EXPORTERS                                          |
|  RFC 5545 iCalendar (.ics) Generator                                                  |
|  - Strict CRLF line terminations (\r\n)                                               |
|  - Character escaping for commas, semicolons, and newlines                            |
|  - Unique UUIDs generated per event milestone                                         |
+---------------------------------------------------------------------------------------+
```

---

## Security Measures

Implemented in strict accordance with the **OWASP Top 10** and **OWASP LLM Top 10**:

1. **Prompt Injection Boundary Isolation (OWASP LLM01)**:
   - All user inputs are wrapped inside `<user_data>` tags.
   - Any occurrences of `</user_data>` or case/whitespace variations inside user text are escaped to `&lt;/user_data&gt;` prior to prompt assembly.
   - System instructions explicitly forbid following commands or role alterations found within `<user_data>`.
2. **Insecure Output Handling / XSS Prevention (OWASP LLM02)**:
   - The frontend JavaScript does not use `innerHTML` or `outerHTML`. All DOM nodes (tables, cards, text) are constructed via `document.createElement()` and populated with `textContent`.
3. **Sensitive Information Disclosure (OWASP LLM06 / OWASP Top 10)**:
   - Zero hardcoded secrets or model names in source code. All configuration is loaded from environment variables via `pydantic-settings`.
   - Global exception handlers log only the exception type and a randomly generated UUID `request_id`. Raw user text, prompts, and stack traces are never exposed in responses or logs.
4. **Content Security Policy (CSP)**:
   - `default-src 'self'`, `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, with zero inline scripts or inline styles allowed.
5. **Denial of Service Mitigation**:
   - Request body size limit middleware blocks any request exceeding 64 KB with HTTP 413.
   - Endpoint rate limiting via `slowapi` restricts request floods with HTTP 429.
   - Upstream LLM call timeout is fixed at 30 seconds via `types.HttpOptions(timeout=30000)`.
6. **Container Security**:
   - Multi-stage Docker image based on `python:3.12-slim`.
   - Root privileges are completely dropped; the application executes as unprivileged user `utsav` (UID/GID `10001`).
   - `.dockerignore` prevents copying secrets, test artifacts, or local configurations into the image.

---

## Efficiency & Performance Decisions

1. **Single LLM Call with Bounded Retry**:
   Unlike verbose autonomous agent loops that perform dozens of LLM calls, Utsav Planner targets a single generation call, with at most one targeted retry only if validation fails.
2. **Hard Output Token Cap**:
   `MAX_OUTPUT_TOKENS` defaults to 4096 (configured via environment variable), preventing runaway generation costs.
3. **Deterministic SHA-256 Request Cache**:
   Generated plans are cached in-memory using a SHA-256 hash of the sanitized request payload. Redundant requests are served in `< 5ms` with zero LLM API invocations.
4. **Integer Math for Financial Precision**:
   Contingency checks and budget calculations use integer arithmetic (`(total * 5) // 100`), avoiding IEEE-754 floating-point rounding errors.

---

## Accessibility & Theme Contrast System

### WCAG 2.1 AAA Contrast Matrix
Utsav Planner uses a curated three-color palette:
- **Silver**: `#dde3e8`
- **Aubergine**: `#3a0f34`
- **Marigold**: `#eaaa00`

| Foreground Color | Background Color | UI Usage | Contrast Ratio | WCAG Compliance |
| :--- | :--- | :--- | :--- | :--- |
| **Aubergine** (`#3a0f34`) | **Silver** (`#dde3e8`) | Primary body text, labels, card content | **12.05:1** | **Passes AAA** (Exceeds 7.0:1) |
| **Aubergine** (`#3a0f34`) | **Marigold** (`#eaaa00`) | Primary button background, tag badges | **7.52:1** | **Passes AAA** (Passes 7.0:1) |
| **Marigold** (`#eaaa00`) | **Aubergine** (`#3a0f34`) | Header title, active tab text, footer accents | **7.52:1** | **Passes AAA** (Passes 7.0:1) |
| **Silver** (`#dde3e8`) | **Aubergine** (`#3a0f34`) | Header subtitle, footer text | **12.05:1** | **Passes AAA** (Exceeds 7.0:1) |
| **Marigold** (`#eaaa00`) | **Silver** (`#dde3e8`) | *Strictly Prohibited throughout app* | **1.60:1** | **FAILS WCAG** (Never used) |

### Key Accessibility Features
- **Semantic Structure**: Proper HTML5 landmarks (`header`, `main`, `footer`), single `<h1>`, skip-navigation link.
- **Form Association**: Visible `<label>` for every field, hint text linked via `aria-describedby`, errors linked via `aria-describedby` and `aria-invalid`.
- **Keyboard Error Management**: An error summary box (`role="alert"`) automatically receives keyboard focus when submission errors occur.
- **Tab Navigation**: Custom accessible tabs (`role="tablist"`, `role="tab"`, `role="tabpanel"`) supporting Arrow Left/Right, Home, and End navigation.
- **Table Accessibility**: Plan tables include `<caption>`, `<th scope="col">`, and `<th scope="row">` headers.
- **High-Visibility Focus Ring**: Dual focus indicator: 3px aubergine outline + 2px marigold offset ring on all interactive elements.
- **Touch Target & Scaling**: Minimum 44px by 44px touch targets; responsive down to 320px viewport; supports 400% zoom without clipping.
- **Motion & Print**: Respects `prefers-reduced-motion` and includes a dedicated print stylesheet (`@media print`).

---

## Installation, Testing & Deployment

### 1. Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- A Google Gemini API Key

### 2. Local Setup
```bash
# Clone the repository
git clone https://github.com/tanish1206/Utsav-Planner.git
cd Utsav-Planner

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install development and production dependencies
pip install -r requirements-dev.txt

# Create .env configuration file from template
cp .env.example .env
```

Edit `.env` to include your credentials:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
MAX_OUTPUT_TOKENS=4096
RATE_LIMIT=10/minute
CACHE_TTL_SECONDS=3600
CACHE_MAX_ITEMS=100
ALLOWED_ORIGINS=*
```

### 3. Running the Test Suite
The test suite consists of 92 automated tests with a minimum coverage gate of 85%:

```bash
# Run tests with coverage report
pytest --cov=app --cov-fail-under=85 -q

# Run code style & formatting checks
ruff check .
ruff format --check .
black --check .

# Run dependency vulnerability audit
pip-audit
```

### 4. Running the Development Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Access the application at `http://127.0.0.1:8000`.

### 5. Docker Deployment
```bash
# Build the multi-stage slim container
docker build -t utsav-planner:latest .

# Run container as non-root user (pass API key at runtime)
docker run --rm -d -p 8000:8000 --name utsav_app \
  -e GEMINI_API_KEY="your_api_key_here" \
  -e GEMINI_MODEL="gemini-2.5-flash" \
  utsav-planner:latest

# Check container health status
docker inspect --format='{{json .State.Health.Status}}' utsav_app

# Stop container
docker stop utsav_app
```

### 6. Vercel Serverless Deployment
Utsav Planner is pre-configured for Vercel deployment via `api/index.py` and `vercel.json`:
1. Push your code to GitHub.
2. In your [Vercel Dashboard](https://vercel.com/dashboard), import the repository.
3. In **Project Settings > Environment Variables**, add:
   - `GEMINI_API_KEY`: Your Google Gemini API key.
   - `GEMINI_MODEL`: `gemini-2.5-flash` (or your preferred Gemini model).
   - `ALLOWED_ORIGINS`: `*` (or your custom domain).
4. Deploy. Vercel routes all requests to `api/index.py` and packages static assets and templates automatically.

---

## Known Limitations

In the interest of factual accuracy, the following architectural trade-offs exist:

1. **In-Memory Cache Scope**: The plan TTL cache (`PlanCache`) is an in-memory dictionary. It does not synchronize across multi-container horizontal deployments (e.g., Redis would be required for clustered deployments).
2. **In-Memory Rate Limiting**: `slowapi` rate limits are tracked in application memory and reset upon server restart.
3. **No Database Persistence**: Event plans are generated and cached temporarily during the active TTL window. Permanent records must be downloaded as `.ics` or printed by the user.
4. **Live Generation Connectivity**: Offline generation is not supported; generating new event plans requires internet connectivity to Google's Gemini API endpoints.
5. **Fixed Vendor Categories**: Vendor recommendations validate against predefined category sets per event type (`ALLOWED_VENDOR_CATEGORIES`). Unrecognized vendor types are flagged by the validator during retry.
