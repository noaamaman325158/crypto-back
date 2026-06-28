"""Unit tests for the gRPC JWT auth interceptor — pure logic, no live server."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token, create_refresh_token
from app.grpc_server.auth_interceptor import (
    JWTAuthInterceptor,
    _extract_bearer,
    _is_public,
)


def test_extract_bearer_valid():
    assert _extract_bearer("Bearer abc.def.ghi") == "abc.def.ghi"
    assert _extract_bearer("bearer abc.def.ghi") == "abc.def.ghi"  # case-insensitive


def test_extract_bearer_invalid():
    assert _extract_bearer("") is None
    assert _extract_bearer("abc.def.ghi") is None          # no scheme
    assert _extract_bearer("Token abc") is None            # wrong scheme
    assert _extract_bearer("Bearer a b c") is None         # too many parts


def test_reflection_methods_are_public():
    assert _is_public("/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo")
    assert not _is_public("/crypto.insight.v1.InsightService/GetInsight")


def _call_details(method: str, metadata: tuple):
    d = MagicMock()
    d.method = method
    d.invocation_metadata = metadata
    return d


@pytest.mark.asyncio
async def test_valid_access_token_passes_through():
    interceptor = JWTAuthInterceptor()
    token = create_access_token("user-123", role="user")
    continuation = AsyncMock(return_value="real_handler")

    details = _call_details(
        "/crypto.insight.v1.InsightService/GetInsight",
        (("authorization", f"Bearer {token}"),),
    )
    result = await interceptor.intercept_service(continuation, details)

    assert result == "real_handler"
    continuation.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_token_is_rejected():
    interceptor = JWTAuthInterceptor()
    continuation = AsyncMock(return_value="real_handler")

    details = _call_details("/crypto.insight.v1.InsightService/GetInsight", ())
    result = await interceptor.intercept_service(continuation, details)

    # An abort handler is returned instead of the real handler.
    assert result != "real_handler"
    continuation.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_token_is_rejected():
    """A refresh token must not be accepted where an access token is required."""
    interceptor = JWTAuthInterceptor()
    refresh = create_refresh_token("user-123")
    continuation = AsyncMock(return_value="real_handler")

    details = _call_details(
        "/crypto.insight.v1.InsightService/GetInsight",
        (("authorization", f"Bearer {refresh}"),),
    )
    result = await interceptor.intercept_service(continuation, details)

    assert result != "real_handler"
    continuation.assert_not_awaited()


@pytest.mark.asyncio
async def test_reflection_passes_without_token():
    interceptor = JWTAuthInterceptor()
    continuation = AsyncMock(return_value="reflection_handler")

    details = _call_details(
        "/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo", ()
    )
    result = await interceptor.intercept_service(continuation, details)

    assert result == "reflection_handler"
    continuation.assert_awaited_once()
