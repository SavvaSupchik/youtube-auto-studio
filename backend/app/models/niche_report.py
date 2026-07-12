"""Модель сохранённого отчёта анализа ниш YouTube.

Храним результаты сканов и глубоких разборов, чтобы:
- показывать историю во вкладке «Анализ ниш»;
- не тратить квоту YouTube Data API повторно на уже посчитанное.
"""
from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid


class NicheReport(Base, TimestampMixin):
    __tablename__ = "niche_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    # scan  — ранжированный список под-ниш по seed-запросу
    # deep  — детальный разбор одной ниши/ключа
    kind: Mapped[str] = mapped_column(String(16), default="scan")
    # Исходный запрос пользователя (seed или ключ ниши)
    query: Mapped[str] = mapped_column(String(500), default="")
    region: Mapped[str] = mapped_column(String(8), default="RU")
    language: Mapped[str] = mapped_column(String(8), default="ru")
    # Сам результат целиком (список ниш или детальный отчёт) — рендерится на фронте
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # Короткая заметка/вердикт для превью в списке истории
    note: Mapped[str] = mapped_column(Text, default="")
