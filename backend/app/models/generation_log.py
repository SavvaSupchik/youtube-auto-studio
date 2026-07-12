"""Лог стадий генерации (для прогресса и статистики)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid

if TYPE_CHECKING:
    from app.models.video import Video


class GenerationLog(Base, TimestampMixin):
    """Запись об одной стадии пайплайна: модель, токены, стоимость, статус."""

    __tablename__ = "generation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    # script / analysis / translate / tts / visuals / thumbnail / render / stats
    stage: Mapped[str] = mapped_column(String(32), index=True)
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok / running / error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    video: Mapped["Video"] = relationship(back_populates="logs")
