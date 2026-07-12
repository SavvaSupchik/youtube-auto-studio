"""Анализ сценария: hook, summary, topics, structure."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid

if TYPE_CHECKING:
    from app.models.script import Script


class ScriptAnalysis(Base, TimestampMixin):
    """Извлечённая суть сценария — основа для memory.jsonl и статистики."""

    __tablename__ = "script_analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    script_id: Mapped[str] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), unique=True, index=True
    )
    hook: Mapped[str] = mapped_column(Text, default="")
    summary_short: Mapped[str] = mapped_column(Text, default="")
    summary_long: Mapped[str] = mapped_column(Text, default="")
    key_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    structure: Mapped[list[str]] = mapped_column(JSON, default=list)
    tone: Mapped[str] = mapped_column(String(64), default="")
    title_suggestions: Mapped[list[str]] = mapped_column(JSON, default=list)
    youtube_tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    script: Mapped["Script"] = relationship(back_populates="analysis")
