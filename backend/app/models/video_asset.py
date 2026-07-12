"""Ассеты видео: обложки, финальные рендеры, футажи."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, gen_uuid

if TYPE_CHECKING:
    from app.models.video import Video


class VideoAsset(Base, TimestampMixin):
    """Файл-ассет, привязанный к видео (и опционально к языку)."""

    __tablename__ = "video_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    type: Mapped[str] = mapped_column(String(32))  # thumbnail / final / footage
    file_path: Mapped[str] = mapped_column(String(1024), default="")
    asset_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    video: Mapped["Video"] = relationship(back_populates="assets")
