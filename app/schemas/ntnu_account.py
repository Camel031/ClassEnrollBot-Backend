from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NTNUAccountCreate(BaseModel):
    """Schema for creating NTNU account."""

    student_id: str = Field(min_length=5, max_length=20)
    password: str = Field(min_length=1)


class NTNUAccountUpdate(BaseModel):
    """Schema for updating NTNU account."""

    password: str | None = None
    is_active: bool | None = None


class NTNUAccountOut(BaseModel):
    """Schema for NTNU account response."""

    id: UUID
    student_id: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class NTNULoginRequest(BaseModel):
    """Schema for NTNU login request."""

    ntnu_account_id: UUID


class NTNULoginResponse(BaseModel):
    """Schema for NTNU login response."""

    success: bool
    message: str
    session_valid_until: datetime | None = None
