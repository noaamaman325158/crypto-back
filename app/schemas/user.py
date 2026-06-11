import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str

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
