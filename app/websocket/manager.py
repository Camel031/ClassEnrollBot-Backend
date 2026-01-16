"""WebSocket connection manager for real-time notifications."""

import json
from typing import Any, Dict, Set
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self) -> None:
        # Map user_id to set of active connections
        self._connections: Dict[UUID, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: UUID) -> None:
        """
        Accept a new WebSocket connection.

        Args:
            websocket: WebSocket connection
            user_id: UUID of the connected user
        """
        await websocket.accept()

        if user_id not in self._connections:
            self._connections[user_id] = set()

        self._connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: UUID) -> None:
        """
        Remove a WebSocket connection.

        Args:
            websocket: WebSocket connection to remove
            user_id: UUID of the user
        """
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]

    async def send_to_user(self, user_id: UUID, message: Dict[str, Any]) -> None:
        """
        Send a message to all connections of a specific user.

        Args:
            user_id: UUID of the target user
            message: Message to send
        """
        if user_id not in self._connections:
            return

        disconnected = set()
        for websocket in self._connections[user_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.add(websocket)

        # Clean up disconnected sockets
        for ws in disconnected:
            self._connections[user_id].discard(ws)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """
        Broadcast a message to all connected users.

        Args:
            message: Message to broadcast
        """
        disconnected_users = []

        for user_id, connections in self._connections.items():
            disconnected = set()
            for websocket in connections:
                try:
                    await websocket.send_json(message)
                except Exception:
                    disconnected.add(websocket)

            # Clean up disconnected sockets
            for ws in disconnected:
                connections.discard(ws)

            if not connections:
                disconnected_users.append(user_id)

        # Clean up users with no connections
        for user_id in disconnected_users:
            del self._connections[user_id]

    def get_connection_count(self, user_id: UUID | None = None) -> int:
        """
        Get the number of active connections.

        Args:
            user_id: Optional user to count connections for

        Returns:
            Number of active connections
        """
        if user_id is not None:
            return len(self._connections.get(user_id, set()))

        return sum(len(conns) for conns in self._connections.values())

    def is_user_connected(self, user_id: UUID) -> bool:
        """
        Check if a user has any active connections.

        Args:
            user_id: UUID of the user

        Returns:
            True if user has active connections
        """
        return user_id in self._connections and len(self._connections[user_id]) > 0


# Global connection manager instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
