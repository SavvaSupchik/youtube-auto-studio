"""Глобальная статистика."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.generation_log import GenerationLog
from app.models.project import Project
from app.models.video import Video

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _dir_size_bytes(path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


@router.get("/global")
def global_stats(db: Session = Depends(get_db)):
    total_projects = db.query(func.count(Project.id)).scalar() or 0
    total_videos = db.query(func.count(Video.id)).scalar() or 0
    total_cost = db.query(func.coalesce(func.sum(GenerationLog.cost_usd), 0.0)).scalar() or 0.0
    total_in = db.query(func.coalesce(func.sum(GenerationLog.input_tokens), 0)).scalar() or 0
    total_out = db.query(func.coalesce(func.sum(GenerationLog.output_tokens), 0)).scalar() or 0
    total_duration = db.query(func.coalesce(func.sum(Video.duration_sec), 0)).scalar() or 0

    return {
        "total_projects": total_projects,
        "total_videos": total_videos,
        "total_input_tokens": int(total_in),
        "total_output_tokens": int(total_out),
        "total_cost_usd": round(float(total_cost), 4),
        "total_duration_sec": int(total_duration),
        "disk_usage_bytes": _dir_size_bytes(settings.data_path),
        "llm_provider": settings.llm_provider,
        "llm_configured": settings.llm_configured,
    }
