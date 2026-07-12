"""Брокер прогресса пайплайна для real-time обновлений по WebSocket.

Пайплайн выполняется в отдельном потоке (FastAPI BackgroundTasks), а WebSocket
живёт в event loop. Публикация событий из потока делается через
loop.call_soon_threadsafe, чтобы безопасно положить событие в asyncio.Queue.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class JobBroker:
    """Простой in-memory pub/sub по video_id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Запоминает event loop приложения (вызывается на старте)."""
        self._loop = loop

    def subscribe(self, video_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[video_id].add(q)
        return q

    def unsubscribe(self, video_id: str, q: asyncio.Queue) -> None:
        self._subscribers[video_id].discard(q)
        if not self._subscribers[video_id]:
            self._subscribers.pop(video_id, None)

    def publish(self, video_id: str, event: dict[str, Any]) -> None:
        """Публикует событие. Безопасно вызывается из любого потока."""
        queues = list(self._subscribers.get(video_id, ()))
        if not queues or self._loop is None:
            return

        def _push() -> None:
            for q in queues:
                q.put_nowait(event)

        try:
            self._loop.call_soon_threadsafe(_push)
        except RuntimeError:
            # loop закрыт — игнорируем
            pass


broker = JobBroker()
