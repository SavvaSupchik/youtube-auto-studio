"""API анализа ниш YouTube: скан под-ниш и глубокий разбор.

Расход квоты YouTube Data API реальный (см. services/niche_analyzer.py),
поэтому результаты сохраняются в БД (NicheReport) как история.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.niche_report import NicheReport
from app.services import niche_analyzer
from app.services.niche_analyzer import NicheError

router = APIRouter(prefix="/api/niche", tags=["niche"])


# ---------------------------------------------------------------- schemas
class NicheStatus(BaseModel):
    youtube_configured: bool
    llm_configured: bool
    region_default: str
    language_default: str


class ScanRequest(BaseModel):
    seed: str = Field(min_length=2, max_length=300)
    region: str | None = None
    language: str | None = None
    max_niches: int = Field(default=8, ge=1, le=12)


class DeepDiveRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=300)
    region: str | None = None
    language: str | None = None


class ReportOut(BaseModel):
    id: str
    kind: str
    query: str
    region: str
    language: str
    payload: dict
    note: str
    created_at: str

    @classmethod
    def from_orm_safe(cls, r: NicheReport) -> "ReportOut":
        return cls(
            id=r.id, kind=r.kind, query=r.query, region=r.region, language=r.language,
            payload=r.payload or {}, note=r.note or "", created_at=r.created_at.isoformat(),
        )


# ---------------------------------------------------------------- endpoints
@router.get("/status", response_model=NicheStatus)
def status():
    return NicheStatus(
        youtube_configured=settings.has_youtube,
        llm_configured=settings.llm_configured,
        region_default=settings.youtube_region,
        language_default=settings.youtube_language,
    )


@router.get("/reports", response_model=list[ReportOut])
def list_reports(kind: str | None = None, db: Session = Depends(get_db)):
    q = db.query(NicheReport)
    if kind:
        q = q.filter(NicheReport.kind == kind)
    reports = q.order_by(NicheReport.created_at.desc()).limit(50).all()
    return [ReportOut.from_orm_safe(r) for r in reports]


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)):
    r = db.get(NicheReport, report_id)
    if not r:
        raise HTTPException(404, "Отчёт не найден")
    return ReportOut.from_orm_safe(r)


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: str, db: Session = Depends(get_db)):
    r = db.get(NicheReport, report_id)
    if not r:
        raise HTTPException(404, "Отчёт не найден")
    db.delete(r)
    db.commit()


@router.post("/scan", response_model=ReportOut)
def scan(req: ScanRequest, db: Session = Depends(get_db)):
    """Сканирует под-ниши по широкой теме и ранжирует по Opportunity Score.

    Синхронный: расходует квоту YouTube (~100 units на под-нишу), занимает
    10-30 с. Для одного локального пользователя это приемлемо.
    """
    try:
        result = niche_analyzer.scan(
            req.seed, region=req.region, language=req.language, max_niches=req.max_niches
        )
    except NicheError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("[niche] Ошибка скана")
        raise HTTPException(500, f"Ошибка анализа ниш: {e}") from e

    top = result["niches"][0] if result["niches"] else {}
    note = (
        f"Лучшая: «{top.get('keyword', '—')}» "
        f"(score {top.get('opportunity_score', '—')})"
        if top else "Ниши не найдены"
    )
    report = NicheReport(
        kind="scan", query=req.seed, region=result["region"],
        language=result["language"], payload=result, note=note,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return ReportOut.from_orm_safe(report)


@router.post("/deep-dive", response_model=ReportOut)
def deep_dive(req: DeepDiveRequest, db: Session = Depends(get_db)):
    """Детальный разбор одной ниши: метрики, топ-видео, тренд, вердикт LLM."""
    try:
        result = niche_analyzer.deep_dive(
            req.keyword, region=req.region, language=req.language
        )
    except NicheError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("[niche] Ошибка глубокого разбора")
        raise HTTPException(500, f"Ошибка разбора ниши: {e}") from e

    verdict = result.get("verdict", {})
    note = f"{verdict.get('verdict', '—')}: {verdict.get('one_liner', '')}"
    report = NicheReport(
        kind="deep", query=req.keyword, region=result["region"],
        language=result["language"], payload=result, note=note,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return ReportOut.from_orm_safe(report)
