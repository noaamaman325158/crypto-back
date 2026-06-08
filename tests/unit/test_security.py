"""Unit tests for security.py — no DB, no network, pure logic."""
import jwt
import pytest

from app.config import settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_internal_api_key,
    verify_password,
)


def test_password_hash_and_verify():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_contains_expected_claims():
    token = create_access_token("user-uuid-123", role="admin")
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == "user-uuid-123"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token_contains_expected_claims():
    token = create_refresh_token("user-uuid-456")
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == "user-uuid-456"
    assert payload["type"] == "refresh"


def test_decode_token_invalid_raises():
    with pytest.raises(UnauthorizedError):
        decode_token("not.a.valid.token")


def test_decode_token_tampered_raises():
    token = create_access_token("user-1")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(UnauthorizedError):
        decode_token(tampered)


def test_access_and_refresh_tokens_are_different():
    access = create_access_token("user-1")
    refresh = create_refresh_token("user-1")
    assert access != refresh


def test_internal_api_key_valid():
    verify_internal_api_key(settings.internal_api_key)  # should not raise


def test_internal_api_key_invalid_raises():
    with pytest.raises(ForbiddenError):
        verify_internal_api_key("totally-wrong-key")
