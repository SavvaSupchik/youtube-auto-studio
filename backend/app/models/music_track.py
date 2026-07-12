"""Модель трека музыкальной библиотеки."""
from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid


class MusicTrack(Base, TimestampMixin):
    __tablename__ = "music_tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(String(500), default="")
    # suno / upload / manual
    source: Mapped[str] = mapped_column(String(32), default="upload")
    # теги/жанр — произвольная строка
    tags: Mapped[str] = mapped_column(String(500), default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ID задачи Suno (для отслеживания статуса)
    suno_id: Mapped[str] = mapped_column(String(128), default="")
    # pending / ready / error
    status: Mapped[str] = mapped_column(String(16), default="ready")
