"""WebSocket endpoints for real-time updates."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.api.deps import get_current_user_ws
from app.config import get_settings
from app.core.operation_logger import OperationLogger
from app.db.models import User
from app.websocket.manager import get_connection_manager

router = APIRouter()
settings = get_settings()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """
    WebSocket endpoint for real-time notifications and operation logs.

    Connect with: ws://localhost:8000/api/v1/ws?token=<jwt_token>

    Message types received:
    - notification: User notifications (enrollment success/failure)
    - operation_log: Real-time operation progress (login steps, captcha, etc.)

    Example operation_log message:
    {
        "type": "operation_log",
        "data": {
            "timestamp": "2026-01-21T14:32:15.123Z",
            "task": "browser_client",
            "operation_type": "login",
            "status": "in_progress",
            "message": "Step 3/6: Solving captcha",
            "details": {}
        }
    }
    """
    manager = get_connection_manager()

    # Authenticate user from token
    try:
        user = await get_current_user_ws(token)
        if not user:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Connect
    await manager.connect(websocket, user.id)

    # Register operation log subscriber for this user (dev mode)
    async def operation_log_handler(log_entry: dict) -> None:
        # Only send logs related to this user's accounts
        account_id = log_entry.get("account_id")
        if account_id:
            # In production, filter by user's NTNU accounts
            # For now in dev mode, broadcast all logs
            if settings.debug:
                await manager.send_operation_log(user.id, log_entry)

    OperationLogger.subscribe(operation_log_handler)

    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_json()

            # Handle ping/pong for keepalive
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        OperationLogger.unsubscribe(operation_log_handler)
        manager.disconnect(websocket, user.id)


@router.websocket("/ws/dev")
async def websocket_dev_endpoint(websocket: WebSocket) -> None:
    """
    Development WebSocket endpoint - no authentication required.

    Broadcasts ALL operation logs for debugging.
    Only available when DEBUG=true.

    Connect with: ws://localhost:8000/api/v1/ws/dev
    """
    if not settings.debug:
        await websocket.close(code=4003, reason="Dev endpoint only available in debug mode")
        return

    await websocket.accept()

    # Subscribe to all operation logs
    async def broadcast_handler(log_entry: dict) -> None:
        try:
            await websocket.send_json({
                "type": "operation_log",
                "data": log_entry,
            })
        except Exception:
            pass

    OperationLogger.subscribe(broadcast_handler)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        OperationLogger.unsubscribe(broadcast_handler)
