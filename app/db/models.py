import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    pass


class User(Base):
    """System user model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    ntnu_accounts: Mapped[list["NTNUAccount"]] = relationship(
        "NTNUAccount", back_populates="user", cascade="all, delete-orphan"
    )
    tracked_courses: Mapped[list["TrackedCourse"]] = relationship(
        "TrackedCourse", back_populates="user", cascade="all, delete-orphan"
    )
    enrollment_logs: Mapped[list["EnrollmentLog"]] = relationship(
        "EnrollmentLog", back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )


class NTNUAccount(Base):
    """NTNU account credentials (encrypted)."""

    __tablename__ = "ntnu_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(String(20), nullable=False)
    encrypted_password: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="ntnu_accounts")
    tracked_courses: Mapped[list["TrackedCourse"]] = relationship(
        "TrackedCourse", back_populates="ntnu_account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Unique constraint: one student_id per user
        {"sqlite_autoincrement": True},
    )


class TrackedCourse(Base):
    """Course tracking configuration."""

    __tablename__ = "tracked_courses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ntnu_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ntnu_accounts.id", ondelete="CASCADE"), nullable=False
    )

    # Course identification
    # serial_no is the primary identifier in NTNU system (e.g., "0001", "6024")
    serial_no: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # course_code is secondary (e.g., "A0U0004")
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), nullable=False)
    class_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    teacher_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Monitoring settings
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_enroll: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # Status tracking
    current_enrolled: Mapped[int] = mapped_column(Integer, default=0)
    max_capacity: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tracked_courses")
    ntnu_account: Mapped["NTNUAccount"] = relationship(
        "NTNUAccount", back_populates="tracked_courses"
    )
    enrollment_logs: Mapped[list["EnrollmentLog"]] = relationship(
        "EnrollmentLog", back_populates="tracked_course"
    )


class EnrollmentLog(Base):
    """Enrollment operation history."""

    __tablename__ = "enrollment_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tracked_course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracked_courses.id", ondelete="SET NULL"), nullable=True
    )

    # Operation info
    action_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # auto_enroll, manual_enroll, drop, query
    serial_no: Mapped[str] = mapped_column(String(10), nullable=False)
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    course_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Result info
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failed, pending
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Course status at the time
    enrolled_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="enrollment_logs")
    tracked_course: Mapped["TrackedCourse | None"] = relationship(
        "TrackedCourse", back_populates="enrollment_logs"
    )


class Notification(Base):
    """User notifications."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # success, warning, error, info
    related_course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracked_courses.id", ondelete="SET NULL"), nullable=True
    )

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications")
