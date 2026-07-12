"""Модель сценария (на конкретном языке)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid

if TYPE_CHECKING:
    from app.models.video import Video
    from app.models.script_analysis import ScriptAnalysis
    from app.models.audio import AudioTrack


class Script(Base, TimestampMixin):
    """Сценарий на одном языке. Полный текст также дублируется в файл script_<lang>.md."""

    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(8), default="ru")
    content_md: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_estimate_sec: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    video: Mapped["Video"] = relationship(back_populates="scripts")
    analysis: Mapped["ScriptAnalysis | None"] = relationship(
        back_populates="script", cascade="all, delete-orphan", uselist=False
    )
    audio_tracks: Mapped[list["AudioTrack"]] = relationship(
        back_populates="script", cascade="all, delete-orphan"
    )
