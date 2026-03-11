from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TrackedCourseCreate(BaseModel):
    """Schema for creating a tracked course."""

    ntnu_account_id: UUID
    # serial_no is the primary identifier in NTNU system (e.g., "0001", "6024")
    serial_no: str = Field(min_length=1, max_length=10)
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
    serial_no: str
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
    """
    Schema for course search result from NTNU system.

    Based on actual API response from CourseQueryCtrl?action=showGrid.
    """

    serial_no: str  # Primary identifier (e.g., "0001")
    course_code: str  # e.g., "A0U0004"
    course_name: str  # Chinese name (chnName)
    course_name_eng: str | None = None  # English name (engName)
    teacher: str
    credits: float
    current_enrolled: int  # v_stfseld
    max_capacity: int  # limitCountH
    time_info: str  # e.g., "三 6-7 和平 體002"
    time_info_eng: str | None = None
    option_code: str | None = None  # 選修/必修
    dept_code: str | None = None
    dept_name: str | None = None  # v_deptChiabbr
    course_kind: str | None = None  # 半/全
    acadm_year: str | None = None
    acadm_term: str | None = None
    is_full: bool = False
    emi: str | None = None  # EMI course flag
    memo: str | None = None  # v_comment
