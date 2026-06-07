from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1.router import router
from app.config import settings
from app.core.cache import close_redis

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run Alembic migrations programmatically
    from alembic import command
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield
    # Shutdown
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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "environment": settings.environment}
