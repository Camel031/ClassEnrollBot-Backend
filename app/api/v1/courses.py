from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.db.models import NTNUAccount, TrackedCourse
from app.schemas import TrackedCourseCreate, TrackedCourseOut, TrackedCourseUpdate

router = APIRouter()


@router.get("", response_model=list[TrackedCourseOut])
async def list_tracked_courses(
    current_user: CurrentUser,
    db: DbSession,
) -> list[TrackedCourse]:
    """List all tracked courses for the current user."""
    result = await db.execute(
        select(TrackedCourse)
        .where(TrackedCourse.user_id == current_user.id)
        .order_by(TrackedCourse.priority.desc(), TrackedCourse.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=TrackedCourseOut, status_code=status.HTTP_201_CREATED)
async def create_tracked_course(
    course_data: TrackedCourseCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> TrackedCourse:
    """Create a new tracked course."""
    # Verify NTNU account belongs to user
    result = await db.execute(
        select(NTNUAccount).where(
            NTNUAccount.id == course_data.ntnu_account_id,
            NTNUAccount.user_id == current_user.id,
        )
    )
    ntnu_account = result.scalar_one_or_none()

    if not ntnu_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NTNU account not found",
        )

    # Check if course already tracked
    result = await db.execute(
        select(TrackedCourse).where(
            TrackedCourse.ntnu_account_id == course_data.ntnu_account_id,
            TrackedCourse.course_code == course_data.course_code,
            TrackedCourse.class_code == course_data.class_code,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This course is already being tracked",
        )

    # Create tracked course
    course = TrackedCourse(
        user_id=current_user.id,
        ntnu_account_id=course_data.ntnu_account_id,
        course_code=course_data.course_code,
        course_name=course_data.course_name,
        class_code=course_data.class_code,
        teacher_name=course_data.teacher_name,
        is_enabled=course_data.is_enabled,
        auto_enroll=course_data.auto_enroll,
        priority=course_data.priority,
    )
    db.add(course)
    await db.flush()
    await db.refresh(course)

    return course


@router.get("/{course_id}", response_model=TrackedCourseOut)
async def get_tracked_course(
    course_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> TrackedCourse:
    """Get a specific tracked course."""
    result = await db.execute(
        select(TrackedCourse).where(
            TrackedCourse.id == course_id,
            TrackedCourse.user_id == current_user.id,
        )
    )
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracked course not found",
        )

    return course


@router.patch("/{course_id}", response_model=TrackedCourseOut)
async def update_tracked_course(
    course_id: UUID,
    course_data: TrackedCourseUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> TrackedCourse:
    """Update a tracked course."""
    result = await db.execute(
        select(TrackedCourse).where(
            TrackedCourse.id == course_id,
            TrackedCourse.user_id == current_user.id,
        )
    )
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracked course not found",
        )

    if course_data.is_enabled is not None:
        course.is_enabled = course_data.is_enabled

    if course_data.auto_enroll is not None:
        course.auto_enroll = course_data.auto_enroll

    if course_data.priority is not None:
        course.priority = course_data.priority

    await db.flush()
    await db.refresh(course)

    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tracked_course(
    course_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete a tracked course."""
    result = await db.execute(
        select(TrackedCourse).where(
            TrackedCourse.id == course_id,
            TrackedCourse.user_id == current_user.id,
        )
    )
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracked course not found",
        )

    await db.delete(course)
