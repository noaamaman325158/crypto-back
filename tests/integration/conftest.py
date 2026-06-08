from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/crypto_test"


# pytest-asyncio >=1.0 requires explicit loop scope on session-scoped fixtures.
# Use "function" scope throughout to avoid asyncpg "attached to a different loop"
# errors that occur when a session-scoped engine connection is reused across
# function-scoped async fixtures running on different event loops.
@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(setup_db):
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    TestSession = async_sessionmaker(engine, expire_on_commit=False)
    async with TestSession() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Disable rate limiting in tests — tests share the same IP (127.0.0.1)
    # so the tight limits (e.g. 5/min on /refresh) fire across test functions
    # and cause unrelated tests to fail with 429.
    with patch("app.core.rate_limit.limiter.enabled", False), \
         patch("app.core.cache.get_redis", return_value=AsyncMock(
             get=AsyncMock(return_value=None),
             setex=AsyncMock(),
             delete=AsyncMock(),
             keys=AsyncMock(return_value=[]),
         )):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    app.dependency_overrides.clear()
