"""Unit tests for migration fail-fast behavior in the app lifespan.

A failed Alembic migration must crash the app in production (so an ECS task
never serves traffic against a stale schema), but stay lenient in dev.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.main import app, lifespan


async def _run_lifespan_once():
    """Enter and exit the lifespan context manager once."""
    cm = lifespan(app)
    await cm.__aenter__()
    await cm.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_migration_failure_raises_in_production():
    with patch("alembic.command.upgrade", side_effect=RuntimeError("migration boom")), \
         patch("app.main.grpc_serve", new=AsyncMock()), \
         patch("app.main.close_redis", new=AsyncMock()), \
         patch("app.main.settings.environment", "production"):
        with pytest.raises(RuntimeError, match="migration boom"):
            await _run_lifespan_once()


@pytest.mark.asyncio
async def test_migration_failure_is_swallowed_in_development():
    with patch("alembic.command.upgrade", side_effect=RuntimeError("migration boom")), \
         patch("app.main.grpc_serve", new=AsyncMock()), \
         patch("app.main.close_redis", new=AsyncMock()), \
         patch("app.main.settings.environment", "development"):
        # Should NOT raise — dev continues serving so a developer can fix it.
        await _run_lifespan_once()
