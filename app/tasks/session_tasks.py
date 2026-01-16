"""Session management tasks."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

from celery import shared_task
from sqlalchemy import delete, select

from app.db.database import async_session_maker
from app.db.models import EnrollmentLog, NTNUAccount, Notification
from app.services.ntnu_client import NTNUClient
from app.services.session_manager import get_session_manager


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task
def maintain_session(ntnu_account_id: str) -> Dict[str, Any]:
    """
    Call Wakeup.do endpoint to keep session alive.

    Args:
        ntnu_account_id: UUID of the NTNU account

    Returns:
        Dict with keepalive result
    """
    return run_async(_maintain_session(ntnu_account_id))


async def _maintain_session(ntnu_account_id: str) -> Dict[str, Any]:
    """Async implementation of session maintenance."""
    account_uuid = UUID(ntnu_account_id)

    # Check if session exists
    session_manager = get_session_manager()
    if not await session_manager.is_session_valid(account_uuid):
        return {"skipped": True, "reason": "No active session"}

    # Create client and send keepalive
    client = NTNUClient(account_uuid)

    try:
        success = await client.keepalive()

        if success:
            return {
                "success": True,
                "message": "Session maintained",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            # Session might have expired
            return {
                "success": False,
                "message": "Keepalive failed - session may have expired",
            }

    except Exception as e:
        return {"error": str(e)}

    finally:
        client.close()


@shared_task
def batch_maintain_sessions() -> Dict[str, Any]:
    """
    Periodic task to maintain all active sessions.

    Returns:
        Dict with maintenance summary
    """
    return run_async(_batch_maintain_sessions())


async def _batch_maintain_sessions() -> Dict[str, Any]:
    """Async implementation of batch session maintenance."""
    async with async_session_maker() as db:
        # Get all active NTNU accounts
        result = await db.execute(
            select(NTNUAccount).where(NTNUAccount.is_active == True)
        )
        accounts = result.scalars().all()

        session_manager = get_session_manager()
        maintained = 0
        skipped = 0

        for account in accounts:
            # Check if account has an active session
            if await session_manager.is_session_valid(account.id):
                # Dispatch maintenance task
                maintain_session.delay(str(account.id))
                maintained += 1
            else:
                skipped += 1

        return {
            "maintained": maintained,
            "skipped": skipped,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@shared_task
def cleanup_old_logs(days_to_keep: int = 30) -> Dict[str, Any]:
    """
    Cleanup old enrollment logs and notifications.

    Args:
        days_to_keep: Number of days to keep logs

    Returns:
        Dict with cleanup summary
    """
    return run_async(_cleanup_old_logs(days_to_keep))


async def _cleanup_old_logs(days_to_keep: int) -> Dict[str, Any]:
    """Async implementation of log cleanup."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    async with async_session_maker() as db:
        # Delete old enrollment logs
        logs_result = await db.execute(
            delete(EnrollmentLog).where(EnrollmentLog.created_at < cutoff_date)
        )
        deleted_logs = logs_result.rowcount

        # Delete old read notifications
        notifications_result = await db.execute(
            delete(Notification).where(
                Notification.created_at < cutoff_date,
                Notification.is_read == True,
            )
        )
        deleted_notifications = notifications_result.rowcount

        await db.commit()

        return {
            "deleted_logs": deleted_logs,
            "deleted_notifications": deleted_notifications,
            "cutoff_date": cutoff_date.isoformat(),
        }


@shared_task
def cleanup_expired_sessions() -> Dict[str, Any]:
    """
    Cleanup expired sessions from Redis.
    Note: Redis TTL handles most cleanup automatically.

    Returns:
        Dict with cleanup summary
    """
    # Redis handles TTL automatically, but we can log the action
    return {
        "message": "Session cleanup handled by Redis TTL",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
