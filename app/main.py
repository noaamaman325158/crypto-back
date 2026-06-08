import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router
from app.config import settings
from app.core.cache import close_redis
from app.core.rate_limit import limiter
from app.grpc_server.server import serve as grpc_serve


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    logger = logging.getLogger(__name__)

    # Run Alembic migrations on startup.
    # In CI the integration test job runs migrations separately before starting
    # the server — this is a safety net for production deployments.
    try:
        from alembic import command
        from alembic.config import Config
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied")
    except Exception as e:
        logger.warning("Alembic migration skipped or failed: %s", e)

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


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "environment": settings.environment}
