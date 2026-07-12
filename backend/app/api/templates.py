"""API редактируемых шаблонов сценария + адаптация промтов под тему.

Шаблоны глобальные (один комплект на приложение), правятся в Настройках.
Адаптация — предварительный шаг: ИИ переписывает 3 базовых шаблона под
конкретную тему канала, чтобы их можно было посмотреть/поправить в форме
создания видео до запуска генерации.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.llm import LLMError
from app.models.project import Project
from app.schemas.template import (
    AdaptPromptsIn,
    AdaptPromptsOut,
    TemplateOut,
    TemplateUpdate,
)
from app.services import script_chain, script_templates

router = APIRouter(prefix="/api", tags=["templates"])


@router.get("/templates", response_model=list[TemplateOut])
def list_templates():
    """Все шаблоны сценария (с учётом пользовательских правок)."""
    return script_templates.list_all()


@router.put("/templates/{name}", response_model=TemplateOut)
def save_template(name: str, payload: TemplateUpdate):
    """Сохраняет пользовательскую правку шаблона."""
    if not script_templates.is_valid(name):
        raise HTTPException(404, f"Неизвестный шаблон: {name}")
    script_templates.save(name, payload.content)
    return {
        "name": name,
        "title": script_templates.TEMPLATE_TITLES[name],
        "content": script_templates.load(name),
        "overridden": script_templates.is_overridden(name),
    }


@router.post("/templates/{name}/reset", response_model=TemplateOut)
def reset_template(name: str):
    """Сбрасывает шаблон к дефолтному (удаляет пользовательскую правку)."""
    if not script_templates.is_valid(name):
        raise HTTPException(404, f"Неизвестный шаблон: {name}")
    script_templates.reset(name)
    return {
        "name": name,
        "title": script_templates.TEMPLATE_TITLES[name],
        "content": script_templates.load(name),
        "overridden": script_templates.is_overridden(name),
    }


@router.post("/templates/adapt", response_model=AdaptPromptsOut)
def adapt_prompts(payload: AdaptPromptsIn, db: Session = Depends(get_db)):
    """Адаптирует 3 шаблона под тему канала -> 3 готовых промта для правки."""
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(404, "Канал не найден")
    try:
        result = script_chain.adapt_prompts(project, payload.topic, project.language_primary)
    except LLMError as e:
        raise HTTPException(400, str(e)) from e
    return AdaptPromptsOut(
        stage1=result.prompts["stage1"],
        stage2=result.prompts["stage2"],
        stage3=result.prompts["stage3"],
        input_tokens=result.llm.input_tokens,
        output_tokens=result.llm.output_tokens,
        cost_usd=result.llm.cost_usd,
    )
