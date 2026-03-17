"""Realtime websocket routes."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.api.deps import require_websocket_local_token
from backend.app.services.task_service import TaskService


TASK_SNAPSHOT_INTERVAL_SECONDS = 0.5
router = APIRouter(prefix='/ws', tags=['ws'])


@router.websocket('/tasks')
async def task_updates(websocket: WebSocket) -> None:
    app_state = require_websocket_local_token(websocket)
    await websocket.accept()
    service = TaskService(app_state)
    last_payload = ''

    try:
        while True:
            try:
                items = service.list_tasks()
                message = {
                    'type': 'task_snapshot',
                    'items': [item.model_dump() for item in items],
                    'total': len(items),
                }
            except Exception as exc:
                message = {
                    'type': 'error',
                    'detail': str(exc),
                }

            payload = json.dumps(message, sort_keys=True, separators=(',', ':'))
            if payload != last_payload:
                await websocket.send_json(message)
                last_payload = payload

            await asyncio.sleep(TASK_SNAPSHOT_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return
