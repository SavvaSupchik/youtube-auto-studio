"""Аудиодорожка (озвучка сценария)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid

if TYPE_CHECKING:
    from app.models.script import Script


class AudioTrack(Base, TimestampMixin):
    """Озвучка одного сценария одним движком/голосом."""

    __tablename__ = "audio_tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    script_id: Mapped[str] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(1024), default="")
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    voice_id: Mapped[str] = mapped_column(String(64), default="")
    engine: Mapped[str] = mapped_column(String(32), default="kokoro")  # kokoro/manual/elevenlabs
    status: Mapped[str] = mapped_column(String(16), default="ready")  # ready/failed
    version: Mapped[int] = mapped_column(Integer, default=1)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    script: Mapped["Script"] = relationship(back_populates="audio_tracks")
