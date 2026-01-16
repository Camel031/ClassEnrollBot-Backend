"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "enrollbot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.course_tasks",
        "app.tasks.session_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    enable_utc=True,

    # Task routing - different queues for different priorities
    task_routes={
        "app.tasks.course_tasks.auto_enroll_course": {"queue": "high_priority"},
        "app.tasks.course_tasks.check_course_availability": {"queue": "default"},
        "app.tasks.session_tasks.maintain_session": {"queue": "default"},
        "app.tasks.session_tasks.cleanup_expired_sessions": {"queue": "low_priority"},
    },

    # Task retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time for rate limiting
    worker_concurrency=4,
)

# Periodic task schedule (Celery Beat)
celery_app.conf.beat_schedule = {
    # Check all enabled courses every 30 seconds
    "check-all-courses": {
        "task": "app.tasks.course_tasks.batch_check_all_enabled_courses",
        "schedule": 30.0,
    },

    # Maintain sessions every 15 minutes
    "maintain-sessions": {
        "task": "app.tasks.session_tasks.batch_maintain_sessions",
        "schedule": 60.0 * 15,  # 15 minutes
    },

    # Cleanup old logs daily at 3 AM
    "cleanup-old-logs": {
        "task": "app.tasks.session_tasks.cleanup_old_logs",
        "schedule": crontab(hour=3, minute=0),
    },
}
