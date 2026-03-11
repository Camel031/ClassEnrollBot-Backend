"""
Operation Logger for real-time visibility.

Provides structured logging for NTNU operations during development.
Logs can be viewed via:
- Console output (colorized)
- WebSocket broadcast (for frontend)
- File logs
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from app.config import get_settings

settings = get_settings()


class OperationType(str, Enum):
    """Types of operations being logged."""

    LOGIN = "login"
    CAPTCHA = "captcha"
    SEARCH = "search"
    ENROLL = "enroll"
    DROP = "drop"
    SESSION = "session"
    BROWSER = "browser"
    HTTP = "http"


class OperationStatus(str, Enum):
    """Status of an operation."""

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"


# ANSI color codes for console output
COLORS = {
    OperationStatus.STARTED: "\033[94m",  # Blue
    OperationStatus.IN_PROGRESS: "\033[93m",  # Yellow
    OperationStatus.SUCCESS: "\033[92m",  # Green
    OperationStatus.FAILED: "\033[91m",  # Red
    OperationStatus.RETRY: "\033[95m",  # Magenta
}
RESET = "\033[0m"

# Operation type icons
ICONS = {
    OperationType.LOGIN: "🔐",
    OperationType.CAPTCHA: "🔢",
    OperationType.SEARCH: "🔍",
    OperationType.ENROLL: "✅",
    OperationType.DROP: "❌",
    OperationType.SESSION: "🔄",
    OperationType.BROWSER: "🌐",
    OperationType.HTTP: "📡",
}


class OperationLogger:
    """
    Structured operation logger for development visibility.

    Example usage:
        logger = OperationLogger("login_task")
        await logger.log(OperationType.LOGIN, OperationStatus.STARTED, "Starting login")
        await logger.log(OperationType.CAPTCHA, OperationStatus.SUCCESS, "Captcha solved", {"answer": "abc123"})
    """

    _subscribers: list[Callable[[dict], Any]] = []

    def __init__(self, task_name: str, account_id: str | None = None) -> None:
        """
        Initialize operation logger.

        Args:
            task_name: Name of the task/operation context
            account_id: Optional account ID for filtering
        """
        self.task_name = task_name
        self.account_id = account_id
        self._logger = logging.getLogger(f"ntnu.{task_name}")
        self._operation_count = 0

        # Setup console handler if not exists
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO if settings.enable_operation_logging else logging.WARNING)

    async def log(
        self,
        op_type: OperationType,
        status: OperationStatus,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an operation with structured data.

        Args:
            op_type: Type of operation
            status: Current status
            message: Human-readable message
            details: Optional additional details
        """
        if not settings.enable_operation_logging:
            return

        self._operation_count += 1

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": self.task_name,
            "account_id": self.account_id,
            "operation_type": op_type.value,
            "status": status.value,
            "message": message,
            "details": details or {},
            "sequence": self._operation_count,
        }

        # Console output with colors
        icon = ICONS.get(op_type, "📋")
        color = COLORS.get(status, "")
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        console_msg = (
            f"{color}[{timestamp}] {icon} [{op_type.value.upper()}] "
            f"{status.value.upper()}: {message}{RESET}"
        )

        if details:
            # Filter sensitive data
            safe_details = {
                k: v for k, v in details.items()
                if k not in ("password", "cookies", "session_id")
            }
            if safe_details:
                console_msg += f" | {safe_details}"

        self._logger.info(console_msg)

        # Broadcast to subscribers (for WebSocket)
        await self._broadcast(log_entry)

    async def _broadcast(self, log_entry: dict) -> None:
        """Broadcast log entry to all subscribers."""
        for subscriber in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(subscriber):
                    await subscriber(log_entry)
                else:
                    subscriber(log_entry)
            except Exception:
                pass  # Don't let subscriber errors affect logging

    @classmethod
    def subscribe(cls, callback: Callable[[dict], Any]) -> None:
        """
        Subscribe to operation logs.

        Args:
            callback: Function to call with log entries
        """
        cls._subscribers.append(callback)

    @classmethod
    def unsubscribe(cls, callback: Callable[[dict], Any]) -> None:
        """Unsubscribe from operation logs."""
        if callback in cls._subscribers:
            cls._subscribers.remove(callback)

    async def log_step(
        self,
        step_num: int,
        total_steps: int,
        description: str,
        op_type: OperationType = OperationType.BROWSER,
    ) -> None:
        """
        Log a numbered step in a multi-step operation.

        Args:
            step_num: Current step number
            total_steps: Total number of steps
            description: Step description
            op_type: Type of operation
        """
        await self.log(
            op_type,
            OperationStatus.IN_PROGRESS,
            f"Step {step_num}/{total_steps}: {description}",
            {"step": step_num, "total": total_steps},
        )


# Convenience function
def get_operation_logger(
    task_name: str, account_id: str | None = None
) -> OperationLogger:
    """Get an operation logger instance."""
    return OperationLogger(task_name, account_id)
