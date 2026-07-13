"""Схемы глобальных настроек приложения."""
from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceParams(BaseModel):
    """Глобальные параметры «живости» голоса."""

    speed: float = Field(default=0.95, ge=0.5, le=1.5)
    pitch: int = Field(default=0, ge=-6, le=6)
    sentence_pause_ms: int = Field(default=160, ge=0, le=1500)
    paragraph_pause_ms: int = Field(default=650, ge=0, le=3000)
    post_process: bool = True
    warmth: float = Field(default=0.35, ge=0.0, le=1.0)


class AppSettingsOut(BaseModel):
    default_voices: dict[str, str]
    voice_params: VoiceParams


class AppSettingsUpdate(BaseModel):
    # {язык: voice_id}; пустая строка/отсутствие языка -> без дефолта для него
    default_voices: dict[str, str] | None = None
    voice_params: VoiceParams | None = None
