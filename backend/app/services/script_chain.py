"""3-шаговая генерация сценария через цепочку адаптируемых промтов.

Пользователь задаёт только тему. Дальше:
  0. ADAPT      — ИИ переписывает 3 базовых шаблона под конкретную тему/язык
                  (свои клише, свои боли ЦА). Результат — 3 готовых промта,
                  которые можно посмотреть/поправить (хранятся в video.script_prompts).
  1. PREP       — по адаптированному промту 1 + память канала → бриф.
  2. WRITE      — по промту 2 + бриф из шага 1 → черновик сценария.
  3. HUMANIZE   — по промту 3 + черновик → авто-аудит и чистовой сценарий.

Каждый шаг — отдельный вызов LLM. Промежуточные результаты (бриф, черновик)
пайплайн сохраняет на диск, чтобы их можно было посмотреть и доделать руками.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.llm import LLMResult, llm_client
from app.core.config import settings
from app.models.project import Project
from app.services import script_templates
from app.utils.text import words_for_minutes

# Полные названия языков для подстановки в {{LANGUAGE}} (модели лучше следуют
# названию, чем коду). Неизвестный код используется как есть.
_LANG_NAMES = {
    "ru": "Russian",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "zh": "Chinese",
    "hi": "Hindi",
    "uk": "Ukrainian",
}


def lang_name(code: str) -> str:
    return _LANG_NAMES.get(code, code)


def _fill(text: str, **values: str) -> str:
    """Подстановка {{KEY}} -> value (без str.format, чтобы не конфликтовать со скобками)."""
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val)
    return text


@dataclass
class StageResult:
    text: str
    llm: LLMResult


@dataclass
class AdaptResult:
    prompts: dict[str, str]  # {"stage1": ..., "stage2": ..., "stage3": ...}
    llm: LLMResult  # суммарные метрики по всем вызовам адаптации


def _sum_llm(results: list[LLMResult]) -> LLMResult:
    if not results:
        return LLMResult(text="", model=settings.model_fast, input_tokens=0, output_tokens=0, cost_usd=0.0)
    return LLMResult(
        text="",
        model=results[0].model,
        input_tokens=sum(r.input_tokens for r in results),
        output_tokens=sum(r.output_tokens for r in results),
        cost_usd=sum(r.cost_usd for r in results),
    )


def _adapt_one(template_name: str, project: Project, topic: str, language: str) -> StageResult:
    """Переписывает один базовый шаблон шага под тему/канал (быстрая модель)."""
    adapt_meta = script_templates.load("adapt")
    template = script_templates.load(template_name)
    ctx = dict(
        TOPIC=topic or "—",
        LANGUAGE=lang_name(language),
        NICHE=project.niche or "—",
        AUDIENCE=project.target_audience or "general audience",
        STYLE=project.style_prompt or "—",
        TEMPLATE=template,
    )
    system = (
        "You are an expert prompt engineer. Follow the user's instructions exactly "
        "and output only the rewritten prompt."
    )
    user = _fill(adapt_meta, **ctx)
    res = llm_client.complete(system=system, prompt=user, model=settings.model_fast, max_tokens=8000)
    return StageResult(text=res.text.strip(), llm=res)


def adapt_prompts(project: Project, topic: str, language: str) -> AdaptResult:
    """Создаёт 3 готовых промта под тему из базовых шаблонов."""
    r1 = _adapt_one("stage1_prep", project, topic, language)
    r2 = _adapt_one("stage2_write", project, topic, language)
    r3 = _adapt_one("stage3_humanize", project, topic, language)
    return AdaptResult(
        prompts={"stage1": r1.text, "stage2": r2.text, "stage3": r3.text},
        llm=_sum_llm([r1.llm, r2.llm, r3.llm]),
    )


def run_prep(prompt: str, topic: str, language: str, memory: str, duration_min: int) -> StageResult:
    """Шаг 1: бриф. prompt — адаптированный шаблон stage1."""
    user = (
        f"VIDEO TOPIC: {topic}\n\n"
        f"CHANNEL MEMORY — compressed summaries of recent videos. Do NOT repeat their "
        f"hooks, structures or key topics:\n{memory}\n\n"
        f"TARGET VIDEO LENGTH: about {duration_min} minutes.\n\n"
        f"Produce the full preparation brief now, in {lang_name(language)}."
    )
    res = llm_client.complete(system=prompt, prompt=user, max_tokens=8000)
    return StageResult(text=res.text.strip(), llm=res)


def run_write(prompt: str, prep_text: str, language: str, duration_min: int) -> StageResult:
    """Шаг 2: черновик сценария. prompt — адаптированный шаблон stage2."""
    words = words_for_minutes(duration_min)
    user = (
        f"PREPARATION BRIEF (input from Step 1):\n\n{prep_text}\n\n"
        f"TARGET LENGTH: about {duration_min} minutes (~{words} words at ~150 wpm).\n\n"
        f"Write the complete voiceover script now, in {lang_name(language)}. "
        f"Output only the script."
    )
    res = llm_client.complete(system=prompt, prompt=user, max_tokens=16000)
    return StageResult(text=res.text.strip(), llm=res)


def run_humanize(prompt: str, draft_text: str, language: str) -> StageResult:
    """Шаг 3: авто-аудит и чистовой сценарий. prompt — адаптированный шаблон stage3."""
    user = (
        f"DRAFT SCRIPT TO AUDIT AND IMPROVE:\n\n{draft_text}\n\n"
        f"Run the full internal audit, then AUTOMATICALLY apply all CRITICAL and "
        f"IMPORTANT fixes (do not ask anything). Output ONLY the final clean voiceover "
        f"script in {lang_name(language)} — no tables, no commentary, no change log."
    )
    res = llm_client.complete(system=prompt, prompt=user, max_tokens=16000)
    return StageResult(text=res.text.strip(), llm=res)
