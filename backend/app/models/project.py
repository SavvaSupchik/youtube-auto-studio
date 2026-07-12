"""Модель канала (проекта)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid

if TYPE_CHECKING:
    from app.models.video import Video


class Project(Base, TimestampMixin):
    """Канал: тематика, стиль, языки, настройки озвучки."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    niche: Mapped[str] = mapped_column(String(255), default="")
    target_audience: Mapped[str] = mapped_column(String(500), default="")
    style_prompt: Mapped[str] = mapped_column(Text, default="")

    language_primary: Mapped[str] = mapped_column(String(8), default="ru")
    languages_export: Mapped[list[str]] = mapped_column(JSON, default=list)
    voice_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tts_mode: Mapped[str] = mapped_column(String(16), default="local")  # local / manual

    # Акцентный цвет канала для UI
    accent_color: Mapped[str] = mapped_column(String(16), default="#6366f1")
    # Опциональный эффект частиц (тёплые огоньки/искры) на видео при рендере
    particles_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Вступительная фраза: если задана — озвучивается и склеивается с основным аудио
    intro_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Шаблон вступления. Поддерживает {channel} и {topic}
    intro_template: Mapped[str] = mapped_column(
        Text,
        default="Добро пожаловать на канал {channel}. Сегодня мы поговорим о: {topic}.",
    )

    # Музыка по умолчанию для новых видео канала
    default_music_track_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    default_music_volume: Mapped[float] = mapped_column(Float, default=0.15)

    videos: Mapped[list["Video"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
