"""Identity API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class UserResponse(BaseModel):
    id: UUID
    email: str
    token_version: int
    created_at: datetime


class AuthMeUserResponse(BaseModel):
    id: UUID
    email: str


class AuthMeMemberResponse(BaseModel):
    id: UUID
    display_name: str | None
    country: str
    screening_state: str


class AuthMeResponse(BaseModel):
    user: AuthMeUserResponse
    member: AuthMeMemberResponse


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900
    user: UserResponse
