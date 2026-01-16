"""Redis session manager for NTNU sessions."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()


class SessionData:
    """Data structure for NTNU session."""

    def __init__(
        self,
        cookies: Dict[str, str],
        session_id: str,
        created_at: datetime,
        last_activity: datetime,
        is_active: bool = True,
    ) -> None:
        self.cookies = cookies
        self.session_id = session_id
        self.created_at = created_at
        self.last_activity = last_activity
        self.is_active = is_active

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "cookies": self.cookies,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        """Create from dictionary."""
        return cls(
            cookies=data["cookies"],
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            is_active=data.get("is_active", True),
        )


class SessionManager:
    """Manages NTNU sessions in Redis."""

    KEY_PREFIX = "ntnu_session:"
    TTL_SECONDS = settings.ntnu_session_ttl_minutes * 60

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _get_key(self, ntnu_account_id: UUID) -> str:
        """Get Redis key for an NTNU account."""
        return f"{self.KEY_PREFIX}{ntnu_account_id}"

    async def save_session(
        self,
        ntnu_account_id: UUID,
        cookies: Dict[str, str],
        session_id: str,
    ) -> SessionData:
        """
        Save a new NTNU session.

        Args:
            ntnu_account_id: NTNU account UUID
            cookies: Session cookies
            session_id: JSESSIONID or similar

        Returns:
            Created SessionData
        """
        r = await self._get_redis()

        now = datetime.now(timezone.utc)
        session_data = SessionData(
            cookies=cookies,
            session_id=session_id,
            created_at=now,
            last_activity=now,
            is_active=True,
        )

        key = self._get_key(ntnu_account_id)
        await r.set(
            key,
            json.dumps(session_data.to_dict()),
            ex=self.TTL_SECONDS,
        )

        return session_data

    async def get_session(self, ntnu_account_id: UUID) -> SessionData | None:
        """
        Get session data for an NTNU account.

        Args:
            ntnu_account_id: NTNU account UUID

        Returns:
            SessionData if exists and valid, None otherwise
        """
        r = await self._get_redis()
        key = self._get_key(ntnu_account_id)

        data = await r.get(key)
        if not data:
            return None

        return SessionData.from_dict(json.loads(data))

    async def update_activity(self, ntnu_account_id: UUID) -> bool:
        """
        Update last activity time and refresh TTL.

        Args:
            ntnu_account_id: NTNU account UUID

        Returns:
            True if session was updated, False if not found
        """
        session = await self.get_session(ntnu_account_id)
        if not session:
            return False

        r = await self._get_redis()
        session.last_activity = datetime.now(timezone.utc)

        key = self._get_key(ntnu_account_id)
        await r.set(
            key,
            json.dumps(session.to_dict()),
            ex=self.TTL_SECONDS,
        )

        return True

    async def invalidate_session(self, ntnu_account_id: UUID) -> bool:
        """
        Invalidate (delete) a session.

        Args:
            ntnu_account_id: NTNU account UUID

        Returns:
            True if session was deleted, False if not found
        """
        r = await self._get_redis()
        key = self._get_key(ntnu_account_id)
        result = await r.delete(key)
        return result > 0

    async def is_session_valid(self, ntnu_account_id: UUID) -> bool:
        """
        Check if a session exists and is valid.

        Args:
            ntnu_account_id: NTNU account UUID

        Returns:
            True if session is valid
        """
        session = await self.get_session(ntnu_account_id)
        return session is not None and session.is_active

    async def get_session_expiry(self, ntnu_account_id: UUID) -> datetime | None:
        """
        Get when the session will expire.

        Args:
            ntnu_account_id: NTNU account UUID

        Returns:
            Expiry datetime if session exists
        """
        r = await self._get_redis()
        key = self._get_key(ntnu_account_id)

        ttl = await r.ttl(key)
        if ttl <= 0:
            return None

        return datetime.now(timezone.utc) + timedelta(seconds=ttl)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Global session manager instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get the global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
