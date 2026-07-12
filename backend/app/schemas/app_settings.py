"""Схемы глобальных настроек приложения."""
from __future__ import annotations

from pydantic import BaseModel


class AppSettingsOut(BaseModel):
    default_voices: dict[str, str]


class AppSettingsUpdate(BaseModel):
    # {язык: voice_id}; пустая строка/отсутствие языка -> без дефолта для него
    default_voices: dict[str, str] | None = None
