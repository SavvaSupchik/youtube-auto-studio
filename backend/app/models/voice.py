"""Сохранённый голос для озвучки — глобальная библиотека, общая для всех каналов."""
from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid


class Voice(Base, TimestampMixin):
    """Именованный голос: язык + движок + voice_id движка.

    Создаётся один раз в общей библиотеке и затем выбирается в настройках
    любого канала (Project.voice_settings[language] = voice.voice_id).
    """

    __tablename__ = "voices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(8), index=True)
    # "kokoro" (локальный синтез) или "manual" (озвучка всегда загружается руками)
    engine: Mapped[str] = mapped_column(String(16), default="kokoro")
    voice_id: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
