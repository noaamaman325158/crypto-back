# ── Stage 1: Builder ─────────────────────────────────────────────────────────
# Full slim image — has pip and gcc needed to compile asyncpg C extensions.
# Pinned to bookworm (Debian 12) for reproducible, predictable base.
FROM python:3.10-slim-bookworm AS builder

WORKDIR /app

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
# Distroless: no shell, no package manager, no su — minimal attack surface.
# Only the Python runtime and our app code exist in this layer.
# CVE surface is near-zero compared to slim (~50-80 CVEs).
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install/lib/python3.10/site-packages /usr/local/lib/python3.10/dist-packages

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

EXPOSE 8000

# Distroless has no shell — CMD must be exec form, no shell expansion
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
