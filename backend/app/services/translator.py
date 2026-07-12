"""Перевод (локализация) сценария на другой язык через Claude."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.llm import LLMResult, llm_client
from app.services import prompts


@dataclass
class TranslatedScript:
    content: str
    llm: LLMResult


def translate_script(content: str, source_lang: str, target_lang: str) -> TranslatedScript:
    """Локализует сценарий с source_lang на target_lang."""
    system = prompts.render(
        "translate_system", source_lang=source_lang, target_lang=target_lang
    )
    result = llm_client.complete(
        system=system, prompt=content, max_tokens=16000, stream=True
    )
    return TranslatedScript(content=result.text.strip(), llm=result)
