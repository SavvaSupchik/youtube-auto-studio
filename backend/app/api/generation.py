"""WebSocket прогресса пайплайна."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.jobs import broker

router = APIRouter(tags=["generation"])


@router.websocket("/api/ws/jobs/{video_id}")
async def ws_jobs(websocket: WebSocket, video_id: str):
    """Стримит события пайплайна для конкретного видео.

    Клиент подключается до/во время генерации и получает события:
    pipeline_start, stage_start, stage_done, stage_error, pipeline_done/error.
    """
    await websocket.accept()
    queue = broker.subscribe(video_id)
    try:
        await websocket.send_json({"type": "connected", "video_id": video_id})
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event)
                if event.get("type") in {"pipeline_done", "pipeline_error"}:
                    # держим соединение ещё немного на случай дочитки клиентом
                    pass
            except asyncio.TimeoutError:
                # ping, чтобы соединение не висело мёртвым
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        broker.unsubscribe(video_id, queue)
