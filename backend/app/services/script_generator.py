"""Генерация сценария по теме с учётом памяти канала (без повторов)."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.llm import LLMResult, llm_client
from app.models.project import Project
from app.services import prompts
from app.services.memory_service import format_memory_for_prompt, read_memory
from app.utils.text import words_for_minutes

DEFAULT_DURATION_MIN = 12


@dataclass
class GeneratedScript:
    content: str
    llm: LLMResult


def generate_script(
    project: Project,
    topic_brief: str,
    language: str,
    target_duration_min: int | None = None,
) -> GeneratedScript:
    """Генерирует сценарий на указанном языке.

    Передаёт в Claude сжатую память канала, чтобы не повторять прошлые hook/темы.
    """
    duration = target_duration_min or DEFAULT_DURATION_MIN
    memory_records = read_memory(project.id, limit=40)

    system = prompts.render(
        "script_system",
        project_name=project.name,
        niche=project.niche or "—",
        target_audience=project.target_audience or "широкая аудитория",
        language=language,
        style_prompt=project.style_prompt or "—",
        memory=format_memory_for_prompt(memory_records),
        target_duration_min=duration,
        target_words=words_for_minutes(duration),
    )
    user = prompts.render("script_user", topic_brief=topic_brief)

    result = llm_client.complete(system=system, prompt=user, max_tokens=16000, stream=True)
    return GeneratedScript(content=result.text.strip(), llm=result)
