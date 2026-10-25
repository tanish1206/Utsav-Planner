# Stage 1: Build virtual environment and install production dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Minimal secure runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Copy pre-built virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create a dedicated non-root system group and user (UID/GID 10001)
RUN groupadd --gid 10001 utsav && \
    useradd --uid 10001 --gid utsav --shell /bin/false --no-create-home utsav

# Copy application source code with non-root ownership
COPY --chown=utsav:utsav app/ app/
COPY --chown=utsav:utsav pyproject.toml README.md ./

# Drop root privileges
USER utsav

EXPOSE 8000

# Periodic health check verifying server responsiveness
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').getcode() == 200 else 1)"

# Start production server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
