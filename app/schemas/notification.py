from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationOut(BaseModel):
    """Schema for notification response."""

    id: UUID
    title: str
    message: str
    notification_type: str  # success, warning, error, info
    related_course_id: UUID | None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
