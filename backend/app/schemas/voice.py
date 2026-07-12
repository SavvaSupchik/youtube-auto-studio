"""Pydantic-схемы библиотеки голосов."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VoiceCreate(BaseModel):
    name: str = Field(min_length=1)
    language: str = Field(min_length=2, max_length=8)
    engine: str = "kokoro"  # kokoro / manual
    voice_id: str = ""
    description: str = ""


class VoiceUpdate(BaseModel):
    name: str | None = None
    language: str | None = None
    engine: str | None = None
    voice_id: str | None = None
    description: str | None = None


class VoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    language: str
    engine: str
    voice_id: str
    description: str
    is_builtin: bool
    created_at: datetime
