"""Course monitoring and enrollment tasks."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NTNUClientError, NTNUSessionExpiredError
from app.db.database import async_session_maker
from app.db.models import EnrollmentLog, Notification, TrackedCourse
from app.services.ntnu_client import NTNUClient


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(bind=True, max_retries=3)
def check_course_availability(self, tracked_course_id: str) -> Dict[str, Any]:
    """
    Check if a course has available slots.
    If available and auto_enroll is enabled, trigger enrollment.

    Args:
        tracked_course_id: UUID of the tracked course

    Returns:
        Dict with check result
    """
    return run_async(_check_course_availability(tracked_course_id))


async def _check_course_availability(tracked_course_id: str) -> Dict[str, Any]:
    """Async implementation of course availability check."""
    course_uuid = UUID(tracked_course_id)

    async with async_session_maker() as db:
        # Get tracked course
        result = await db.execute(
            select(TrackedCourse).where(TrackedCourse.id == course_uuid)
        )
        course = result.scalar_one_or_none()

        if not course:
            return {"error": "Course not found"}

        if not course.is_enabled:
            return {"skipped": True, "reason": "Course monitoring disabled"}

        # Create NTNU client
        client = NTNUClient(course.ntnu_account_id)

        try:
            # Check availability
            availability = await client.check_course_availability(
                course.course_code,
                course.class_code,
            )

            # Update course status
            course.current_enrolled = availability.get("current_enrolled", 0)
            course.max_capacity = availability.get("max_capacity", 0)
            course.last_checked_at = datetime.now(timezone.utc)

            await db.commit()

            # Check if there's vacancy and auto_enroll is enabled
            has_vacancy = availability.get("has_vacancy", False)

            if has_vacancy and course.auto_enroll:
                # Trigger enrollment task
                auto_enroll_course.delay(tracked_course_id)

                return {
                    "success": True,
                    "has_vacancy": True,
                    "enrollment_triggered": True,
                    "current": course.current_enrolled,
                    "capacity": course.max_capacity,
                }

            return {
                "success": True,
                "has_vacancy": has_vacancy,
                "current": course.current_enrolled,
                "capacity": course.max_capacity,
            }

        except NTNUSessionExpiredError:
            return {"error": "Session expired", "needs_login": True}

        except NTNUClientError as e:
            return {"error": str(e)}

        finally:
            client.close()


@shared_task(bind=True, max_retries=5, queue="high_priority")
def auto_enroll_course(self, tracked_course_id: str) -> Dict[str, Any]:
    """
    Attempt to enroll in a course when slot becomes available.
    Uses retry with exponential backoff.

    Args:
        tracked_course_id: UUID of the tracked course

    Returns:
        Dict with enrollment result
    """
    return run_async(_auto_enroll_course(tracked_course_id))


async def _auto_enroll_course(tracked_course_id: str) -> Dict[str, Any]:
    """Async implementation of auto enrollment."""
    course_uuid = UUID(tracked_course_id)

    async with async_session_maker() as db:
        # Get tracked course
        result = await db.execute(
            select(TrackedCourse).where(TrackedCourse.id == course_uuid)
        )
        course = result.scalar_one_or_none()

        if not course:
            return {"error": "Course not found"}

        if not course.auto_enroll:
            return {"skipped": True, "reason": "Auto-enroll disabled"}

        # Create NTNU client
        client = NTNUClient(course.ntnu_account_id)

        try:
            # Attempt enrollment
            enrollment_result = await client.enroll_course(
                course.course_code,
                course.class_code,
            )

            # Log the result
            log = EnrollmentLog(
                user_id=course.user_id,
                tracked_course_id=course.id,
                action_type="auto_enroll",
                course_code=course.course_code,
                course_name=course.course_name,
                status="success" if enrollment_result.get("success") else "failed",
                error_message=enrollment_result.get("message") if not enrollment_result.get("success") else None,
                response_data=enrollment_result.get("data"),
                enrolled_count=course.current_enrolled,
                capacity=course.max_capacity,
            )
            db.add(log)

            # Create notification
            if enrollment_result.get("success"):
                notification = Notification(
                    user_id=course.user_id,
                    title="Course Enrolled Successfully",
                    message=f"Successfully enrolled in {course.course_name} ({course.course_code})",
                    notification_type="success",
                    related_course_id=course.id,
                )
                # Disable further auto-enroll for this course
                course.auto_enroll = False
            else:
                notification = Notification(
                    user_id=course.user_id,
                    title="Enrollment Failed",
                    message=f"Failed to enroll in {course.course_name}: {enrollment_result.get('message')}",
                    notification_type="error",
                    related_course_id=course.id,
                )

            db.add(notification)
            await db.commit()

            return enrollment_result

        except NTNUSessionExpiredError:
            # Log the failure
            log = EnrollmentLog(
                user_id=course.user_id,
                tracked_course_id=course.id,
                action_type="auto_enroll",
                course_code=course.course_code,
                course_name=course.course_name,
                status="failed",
                error_message="Session expired",
            )
            db.add(log)
            await db.commit()

            return {"error": "Session expired", "needs_login": True}

        except NTNUClientError as e:
            # Log the failure
            log = EnrollmentLog(
                user_id=course.user_id,
                tracked_course_id=course.id,
                action_type="auto_enroll",
                course_code=course.course_code,
                course_name=course.course_name,
                status="failed",
                error_message=str(e),
            )
            db.add(log)
            await db.commit()

            return {"error": str(e)}

        finally:
            client.close()


@shared_task
def batch_check_all_enabled_courses() -> Dict[str, Any]:
    """
    Periodic task to check all enabled tracked courses.
    Distributes individual checks to workers.

    Returns:
        Dict with task distribution summary
    """
    return run_async(_batch_check_all_enabled_courses())


async def _batch_check_all_enabled_courses() -> Dict[str, Any]:
    """Async implementation of batch course check."""
    async with async_session_maker() as db:
        # Get all enabled courses
        result = await db.execute(
            select(TrackedCourse)
            .where(TrackedCourse.is_enabled == True)
            .order_by(TrackedCourse.priority.desc())
        )
        courses = result.scalars().all()

        # Dispatch check tasks
        dispatched = 0
        for course in courses:
            check_course_availability.delay(str(course.id))
            dispatched += 1

        return {
            "dispatched": dispatched,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
