import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router
from app.config import settings
from app.core.cache import close_redis
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestLoggingMiddleware
from app.core.rate_limit import limiter
from app.grpc_server.server import serve as grpc_serve

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run Alembic migrations in a thread executor — psycopg2 is sync and would
    # block the event loop if called directly from an async context.
    try:
        import asyncio as _asyncio

        from alembic import command
        from alembic.config import Config

        def _migrate():
            command.upgrade(Config("alembic.ini"), "head")

        loop = _asyncio.get_event_loop()
        await loop.run_in_executor(None, _migrate)
        logger.info("alembic_migrations_applied")
    except Exception as e:
        logger.warning("alembic_migration_failed", error=str(e))

    # Start gRPC server in background alongside FastAPI (REST :8000, gRPC :50051).
    # Same process, two transports — mirrors the Dataminr agentic-search pattern.
    grpc_task = asyncio.create_task(grpc_serve())

    yield

    # Shutdown
    grpc_task.cancel()
    await asyncio.gather(grpc_task, return_exceptions=True)
    await close_redis()


app = FastAPI(
    title="Crypto Dashboard API",
    description=(
        "A production-grade cryptocurrency dashboard backend.\n\n"
        "## Auth\n"
        "Use `POST /api/v1/auth/login` to get a JWT, then click **Authorize** above.\n\n"
        "## Service-to-service\n"
        "The `/refresh` endpoint requires an `X-API-Key` header."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
register_exception_handlers(app)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    # Never use wildcard — explicit origin list configured via CORS_ORIGINS env var.
    # Default allows localhost for local dev; override with real domains in production.
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

app.include_router(router)

# Expose Prometheus metrics at GET /metrics.
# Instruments every HTTP endpoint automatically: request count, latency
# histogram, in-flight requests. Custom business metrics (cache, auth, etc.)
# are defined in app/core/metrics.py and incremented in service code.
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.get("/health", tags=["Health"])
async def health():
    """Liveness + readiness check — verifies DB and Redis are reachable."""
    import time

    from sqlalchemy import text

    from app.core.cache import get_redis
    from app.db.database import AsyncSessionLocal

    checks: dict[str, str] = {}

    # DB check
    try:
        t0 = time.perf_counter()
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = f"{round((time.perf_counter() - t0) * 1000)}ms"
    except Exception as e:
        checks["db"] = f"error: {e}"

    # Redis check
    try:
        t0 = time.perf_counter()
        r = await get_redis()
        await r.ping()
        checks["redis"] = f"{round((time.perf_counter() - t0) * 1000)}ms"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    status = "ok" if all("error" not in v for v in checks.values()) else "degraded"
    return {"status": status, "environment": settings.environment, "checks": checks}
