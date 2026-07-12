"""Анализ сценария: извлечение hook, summary, topics, structure через Claude."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from loguru import logger

from app.core.config import settings
from app.core.llm import LLMResult, llm_client
from app.services import prompts


@dataclass
class Analysis:
    hook: str = ""
    summary_short: str = ""
    summary_long: str = ""
    key_points: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    structure: list[str] = field(default_factory=list)
    tone: str = ""
    title_suggestions: list[str] = field(default_factory=list)
    youtube_tags: list[str] = field(default_factory=list)


@dataclass
class AnalyzeResult:
    analysis: Analysis
    llm: LLMResult


def _extract_json(text: str) -> dict:
    """Достаёт JSON из ответа, даже если он завёрнут в ```json ... ```."""
    text = text.strip()
    if text.startswith("```"):
        # убираем ограждение ```json ... ```
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def analyze_script(content: str) -> AnalyzeResult:
    """Извлекает структурированную суть сценария.

    Использует быструю/дешёвую модель текущего провайдера (settings.model_fast).
    """
    system = prompts.render("analyze_system")
    result = llm_client.complete(
        system=system,
        prompt=content,
        model=settings.model_fast,
        max_tokens=2000,
        stream=False,
    )
    try:
        data = _extract_json(result.text)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("Не удалось распарсить анализ сценария: {err}", err=e)
        data = {}

    analysis = Analysis(
        hook=str(data.get("hook", "")),
        summary_short=str(data.get("summary_short", "")),
        summary_long=str(data.get("summary_long", "")),
        key_points=list(data.get("key_points", []) or []),
        topics=list(data.get("topics", []) or []),
        structure=list(data.get("structure", []) or []),
        tone=str(data.get("tone", "")),
        title_suggestions=list(data.get("title_suggestions", []) or []),
        youtube_tags=list(data.get("youtube_tags", []) or []),
    )
    return AnalyzeResult(analysis=analysis, llm=result)
