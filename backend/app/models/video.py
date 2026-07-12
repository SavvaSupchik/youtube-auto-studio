"""Модель видео."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.script import Script
    from app.models.video_asset import VideoAsset
    from app.models.generation_log import GenerationLog


class Video(Base, TimestampMixin):
    """Видео: тема, статус, длительность."""

    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), default="")
    topic_brief: Mapped[str] = mapped_column(Text, default="")
    # draft / generating / ready / error
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Переопределение голоса канала для конкретного видео: {язык: voice_id}.
    # Пустое значение/отсутствие языка в словаре -> берётся голос канала.
    voice_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Адаптированные под тему промты 3-шаговой генерации: {stage1, stage2, stage3}.
    # Заполняются на шаге адаптации (или передаются из UI после ручной правки).
    # Пусто -> пайплайн адаптирует шаблоны автоматически.
    script_prompts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Параметры монтажного рендера: resolution, zoom, zoom_direction, warm_grade.
    # Если пусто — используются дефолты видеостроителя (720p, subtle, in, True).
    render_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    visual_playlist: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Фоновая музыка: ID трека из библиотеки и громкость 0.0–1.0
    music_track_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    music_volume: Mapped[float] = mapped_column(default=0.15)

    project: Mapped["Project"] = relationship(back_populates="videos")
    scripts: Mapped[list["Script"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    assets: Mapped[list["VideoAsset"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    logs: Mapped[list["GenerationLog"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
