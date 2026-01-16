from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TrackedCourseCreate(BaseModel):
    """Schema for creating a tracked course."""

    ntnu_account_id: UUID
    course_code: str = Field(min_length=1, max_length=20)
    course_name: str = Field(min_length=1, max_length=100)
    class_code: str | None = Field(default=None, max_length=10)
    teacher_name: str | None = Field(default=None, max_length=50)
    is_enabled: bool = True
    auto_enroll: bool = True
    priority: int = 0


class TrackedCourseUpdate(BaseModel):
    """Schema for updating a tracked course."""

    is_enabled: bool | None = None
    auto_enroll: bool | None = None
    priority: int | None = None


class TrackedCourseOut(BaseModel):
    """Schema for tracked course response."""

    id: UUID
    ntnu_account_id: UUID
    course_code: str
    course_name: str
    class_code: str | None
    teacher_name: str | None
    is_enabled: bool
    auto_enroll: bool
    priority: int
    current_enrolled: int
    max_capacity: int
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CourseSearchResult(BaseModel):
    """Schema for course search result from NTNU system."""

    course_code: str
    course_name: str
    class_code: str | None
    teacher_name: str
    credits: int
    current_enrolled: int
    max_capacity: int
    schedule: str  # e.g., "Mon 1-2, Wed 3-4"
    location: str | None
