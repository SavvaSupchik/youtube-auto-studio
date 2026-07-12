"""Общие миксины и утилиты для моделей."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def gen_uuid() -> str:
    """Генерирует строковый UUID (SQLite не имеет нативного UUID-типа)."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Текущее время в UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Добавляет created_at / updated_at."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
