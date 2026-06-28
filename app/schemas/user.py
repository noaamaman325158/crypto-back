import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegisterRequest(BaseModel):
    email: EmailStr
    # min 8 chars for basic strength; max 72 because bcrypt silently truncates
    # input beyond 72 bytes — rejecting longer passwords avoids a confusing
    # "password works truncated" footgun.
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_not_trivial(cls, v: str) -> str:
        if v.isdigit():
            raise ValueError("Password must not be all digits")
        if len(v.strip()) < 8:
            raise ValueError("Password must be at least 8 non-whitespace characters")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {"email": "user@example.com", "password": "strongpassword123"}
        }
    }


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {"email": "user@example.com", "password": "strongpassword123"}
        }
    }


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
            }
        }
    }


class RefreshRequest(BaseModel):
    refresh_token: str

    model_config = {
        "json_schema_extra": {
            "example": {"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}
        }
    }


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "308bf1ea-9b00-4d59-9c87-e9c2e5c68b27",
                "email": "user@example.com",
                "role": "user",
                "created_at": "2024-01-15T10:30:00Z",
            }
        },
    }
