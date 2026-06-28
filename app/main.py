import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
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
        # Fail fast in production: a task that can't migrate must NOT serve
        # traffic against a stale schema (runtime SQL errors / data corruption).
        # In local/dev we log and continue so the app is still usable while a
        # developer fixes the migration.
        logger.error("alembic_migration_failed", error=str(e))
        if settings.environment == "production":
            raise

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
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "Idempotency-Key"],
)

app.include_router(router)

# Expose Prometheus metrics at GET /metrics.
# Instruments every HTTP endpoint automatically: request count, latency
# histogram, in-flight requests. Custom business metrics (cache, auth, etc.)
# are defined in app/core/metrics.py and incremented in service code.
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.get("/health", tags=["Health"])
async def health(response: Response):
    """Deep liveness + readiness check — probes DB and Redis on every call.

    Returns 200 when all dependencies pass, 503 when any is unreachable, so
    load balancers and orchestrators can branch on the status code alone.
    """
    import time

    from sqlalchemy import text

    from app.core.cache import get_redis
    from app.db.database import AsyncSessionLocal

    checks: dict[str, dict] = {}

    # DB check
    try:
        t0 = time.perf_counter()
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:
        # Log the real error server-side; expose only a generic status so an
        # unauthenticated caller can't learn hostnames / auth-failure details.
        logger.error("health_db_check_failed", error=str(e))
        checks["database"] = {"status": "error", "error": "unavailable"}

    # Redis check
    try:
        t0 = time.perf_counter()
        r = await get_redis()
        await r.ping()
        checks["redis"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:
        logger.error("health_redis_check_failed", error=str(e))
        checks["redis"] = {"status": "error", "error": "unavailable"}

    healthy = all(c["status"] == "ok" for c in checks.values())
    if not healthy:
        response.status_code = 503
    return {
        "status": "ok" if healthy else "degraded",
        "environment": settings.environment,
        "checks": checks,
    }
