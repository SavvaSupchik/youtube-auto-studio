"""Схемы для редактируемых шаблонов сценария и адаптации промтов под тему."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateOut(BaseModel):
    name: str
    title: str
    content: str
    overridden: bool  # True -> используется пользовательская правка, не дефолт


class TemplateUpdate(BaseModel):
    content: str = Field(min_length=1)


class AdaptPromptsIn(BaseModel):
    project_id: str
    topic: str = Field(min_length=1)


class AdaptPromptsOut(BaseModel):
    stage1: str
    stage2: str
    stage3: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
