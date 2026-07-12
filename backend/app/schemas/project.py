"""Pydantic-схемы канала."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    niche: str = ""
    target_audience: str = ""
    style_prompt: str = ""
    language_primary: str = "ru"
    languages_export: list[str] = Field(default_factory=list)
    voice_settings: dict[str, str] = Field(default_factory=dict)
    tts_mode: str = "local"
    accent_color: str = "#6366f1"
    particles_enabled: bool = False
    intro_enabled: bool = False
    intro_template: str = "Добро пожаловать на канал {channel}. Сегодня мы поговорим о: {topic}."
    default_music_track_id: str | None = None
    default_music_volume: float = 0.15


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    niche: str | None = None
    target_audience: str | None = None
    style_prompt: str | None = None
    language_primary: str | None = None
    languages_export: list[str] | None = None
    voice_settings: dict[str, str] | None = None
    tts_mode: str | None = None
    accent_color: str | None = None
    particles_enabled: bool | None = None
    intro_enabled: bool | None = None
    intro_template: str | None = None
    default_music_track_id: str | None = None
    default_music_volume: float | None = None


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class ProjectWithStats(ProjectOut):
    video_count: int = 0
    ready_count: int = 0
