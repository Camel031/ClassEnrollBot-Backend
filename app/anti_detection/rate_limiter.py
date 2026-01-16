"""Intelligent rate limiter for anti-detection."""

import asyncio
import random
import time
from datetime import datetime
from enum import Enum
from typing import Dict


class RequestType(Enum):
    """Types of requests with different rate limits."""

    LOGIN = "login"
    CHECK_AVAILABILITY = "check"
    ENROLL = "enroll"
    HEARTBEAT = "heartbeat"
    GENERAL = "general"


# Rate limits: (min_interval_seconds, max_interval_seconds)
RATE_LIMITS: Dict[RequestType, tuple[float, float]] = {
    RequestType.LOGIN: (30.0, 60.0),
    RequestType.CHECK_AVAILABILITY: (3.0, 8.0),
    RequestType.ENROLL: (1.0, 2.0),
    RequestType.HEARTBEAT: (60.0, 120.0),
    RequestType.GENERAL: (1.0, 3.0),
}

# Peak hours for enrollment (hour, minute)
PEAK_HOURS = [(8, 30), (12, 0), (18, 0)]


class RateLimiter:
    """
    Intelligent rate limiter with different limits per request type.
    Adapts polling frequency based on time of day.
    """

    def __init__(self) -> None:
        self._last_request: Dict[RequestType, float] = {}
        self._request_counts: Dict[str, int] = {}

    def get_adaptive_interval(self, request_type: RequestType) -> float:
        """
        Get polling interval adapted to current time.

        - Near peak hours: more aggressive (shorter intervals)
        - Normal hours: conservative
        - Off hours: minimal polling
        """
        if request_type != RequestType.CHECK_AVAILABILITY:
            min_interval, max_interval = RATE_LIMITS[request_type]
            return random.uniform(min_interval, max_interval)

        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute

        for peak_hour, peak_minute in PEAK_HOURS:
            peak_minutes = peak_hour * 60 + peak_minute
            distance = abs(current_minutes - peak_minutes)

            if distance <= 5:  # Within 5 minutes of peak
                return random.uniform(2.0, 4.0)
            elif distance <= 30:  # Within 30 minutes of peak
                return random.uniform(5.0, 10.0)

        # Off-peak hours
        if 0 <= now.hour < 7 or now.hour >= 23:
            return random.uniform(60.0, 120.0)

        # Normal hours
        return random.uniform(15.0, 30.0)

    async def wait_for_slot(self, request_type: RequestType) -> None:
        """
        Wait until it's safe to make the next request.
        Uses adaptive intervals and adds human-like jitter.
        """
        last_time = self._last_request.get(request_type, 0)
        elapsed = time.time() - last_time

        required_wait = self.get_adaptive_interval(request_type)

        if elapsed < required_wait:
            sleep_time = required_wait - elapsed
            # Add human-like jitter
            jitter = random.uniform(-0.5, 1.5)
            sleep_time = max(0.1, sleep_time + jitter)
            await asyncio.sleep(sleep_time)

        self._last_request[request_type] = time.time()

    def is_rate_exceeded(
        self, window_minutes: int = 5, max_requests: int = 50
    ) -> bool:
        """Check if overall rate limit is exceeded."""
        current_window = int(time.time() / (window_minutes * 60))
        window_key = str(current_window)

        count = self._request_counts.get(window_key, 0)
        return count >= max_requests

    def record_request(self, window_minutes: int = 5) -> None:
        """Record a request for rate tracking."""
        current_window = int(time.time() / (window_minutes * 60))
        window_key = str(current_window)

        self._request_counts[window_key] = self._request_counts.get(window_key, 0) + 1

        # Clean old windows
        old_keys = [
            k for k in self._request_counts.keys()
            if int(k) < current_window - 1
        ]
        for k in old_keys:
            del self._request_counts[k]


def humanized_delay(
    min_seconds: float = 2.0,
    max_seconds: float = 5.0,
    jitter: float = 0.3,
) -> float:
    """
    Calculate a human-like delay.

    Args:
        min_seconds: Minimum delay
        max_seconds: Maximum delay
        jitter: Jitter factor (0-1)

    Returns:
        Calculated delay in seconds
    """
    base_delay = random.uniform(min_seconds, max_seconds)
    jitter_amount = base_delay * jitter * random.uniform(-1, 1)
    return max(0.5, base_delay + jitter_amount)


def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> float:
    """
    Calculate exponential backoff delay.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Initial delay
        max_delay: Maximum delay cap

    Returns:
        Calculated delay in seconds
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    # Add jitter to avoid thundering herd
    return delay + random.uniform(0, delay * 0.1)


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
