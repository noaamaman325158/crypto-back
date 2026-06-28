"""Unit tests for registration password-strength validation (schema layer)."""
import pytest
from pydantic import ValidationError

from app.schemas.user import UserRegisterRequest


def test_valid_password_accepted():
    req = UserRegisterRequest(email="a@example.com", password="password123")
    assert req.password == "password123"


@pytest.mark.parametrize("bad", ["short", "abc", "1234567"])
def test_too_short_password_rejected(bad):
    with pytest.raises(ValidationError):
        UserRegisterRequest(email="a@example.com", password=bad)


def test_all_digits_password_rejected():
    with pytest.raises(ValidationError):
        UserRegisterRequest(email="a@example.com", password="123456789")


def test_whitespace_padded_password_rejected():
    # 8 chars but only whitespace padding around a short core
    with pytest.raises(ValidationError):
        UserRegisterRequest(email="a@example.com", password="  ab    ")


def test_over_bcrypt_limit_rejected():
    with pytest.raises(ValidationError):
        UserRegisterRequest(email="a@example.com", password="x" * 73)
