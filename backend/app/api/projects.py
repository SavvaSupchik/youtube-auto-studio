"""CRUD каналов + память + статистика канала."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.llm import llm_client
from app.models.project import Project
from app.models.video import Video
from app.schemas.project import (
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    ProjectWithStats,
)
from app.services.memory_service import format_memory_for_prompt, read_memory, rewrite_memory

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Канал не найден")
    return project


@router.get("", response_model=list[ProjectWithStats])
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    out: list[ProjectWithStats] = []
    for p in projects:
        total = db.query(func.count(Video.id)).filter(Video.project_id == p.id).scalar() or 0
        ready = (
            db.query(func.count(Video.id))
            .filter(Video.project_id == p.id, Video.status == "ready")
            .scalar()
            or 0
        )
        item = ProjectWithStats.model_validate(p)
        item.video_count = total
        item.ready_count = ready
        out.append(item)
    return out


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if db.query(Project).filter(Project.name == payload.name).first():
        raise HTTPException(409, "Канал с таким именем уже существует")
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    return _get_or_404(db, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(project, k, v)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    db.delete(project)
    db.commit()


@router.get("/{project_id}/memory")
def get_memory(project_id: str, limit: int = 100, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)
    return read_memory(project_id, limit=limit)


@router.delete("/{project_id}/memory/{video_id}", status_code=204)
def delete_memory_entry(project_id: str, video_id: str, db: Session = Depends(get_db)):
    """Убирает запись из memory.jsonl (чтобы не учитывать её при генерации)."""
    _get_or_404(db, project_id)
    records = read_memory(project_id, limit=100000)
    records = [r for r in records if r.get("video_id") != video_id]
    rewrite_memory(project_id, records)


class TopicIdea(BaseModel):
    title: str
    brief: str


@router.post("/{project_id}/suggest-topics", response_model=list[TopicIdea])
def suggest_topics(project_id: str, count: int = 6, db: Session = Depends(get_db)):
    """Предлагает N идей для новых видео с учётом тематики канала и уже вышедших видео."""
    project = _get_or_404(db, project_id)
    memory = read_memory(project_id, limit=50)
    memory_str = format_memory_for_prompt(memory) if memory else "Видео ещё не выпускались."

    system = (
        "You are a YouTube content strategist. Respond ONLY with a valid JSON array, "
        "no markdown, no explanation, no code blocks. "
        "Each element: {\"title\": \"...\", \"brief\": \"...\"}. "
        f"Generate exactly {count} ideas."
    )
    prompt = (
        f"Channel: \"{project.name}\"\n"
        f"Niche/theme: {project.niche or 'general'}\n"
        f"Description: {project.description or 'not specified'}\n"
        f"Target audience: {project.target_audience or 'not specified'}\n\n"
        f"Already published videos (DO NOT repeat these topics):\n{memory_str}\n\n"
        f"Suggest {count} fresh video ideas that fit the channel theme and have NOT been covered yet. "
        "Write title and brief in the same language as the channel description. "
        "Reply with JSON array only."
    )

    try:
        result = llm_client.complete(system=system, prompt=prompt, max_tokens=2000, stream=False)
        text = result.text.strip()
        logger.debug("[suggest-topics] raw LLM response: {t}", t=text[:300])

        # Убираем markdown-обёртку если модель всё же добавила ```json
        text = re.sub(r"^```[a-z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        # Вырезаем JSON-массив
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            logger.error("[suggest-topics] JSON-массив не найден в ответе: {t}", t=text[:300])
            raise ValueError("Модель не вернула JSON-массив")
        ideas = json.loads(text[start : end + 1])
        return [TopicIdea(title=str(i.get("title", "")), brief=str(i.get("brief", ""))) for i in ideas]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[suggest-topics] ошибка: {e}", e=e)
        raise HTTPException(500, f"Не удалось сгенерировать идеи: {e}") from e


@router.get("/{project_id}/stats")
def project_stats(project_id: str, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)
    videos = db.query(Video).filter(Video.project_id == project_id).all()
    total = len(videos)
    ready = sum(1 for v in videos if v.status == "ready")
    total_duration = sum(v.duration_sec or 0 for v in videos)

    # Топ тем из памяти
    from collections import Counter

    topic_counter: Counter[str] = Counter()
    for rec in read_memory(project_id, limit=100000):
        topic_counter.update(rec.get("topics", []))

    return {
        "total_videos": total,
        "ready_videos": ready,
        "draft_videos": sum(1 for v in videos if v.status == "draft"),
        "generating_videos": sum(1 for v in videos if v.status == "generating"),
        "error_videos": sum(1 for v in videos if v.status == "error"),
        "total_duration_sec": total_duration,
        "top_topics": topic_counter.most_common(10),
    }
