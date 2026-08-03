"""CRUD видео, сценарии, анализ, логи, запуск/перезапуск пайплайна."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import paths
from app.core.database import get_db
from app.models.audio import AudioTrack
from app.models.generation_log import GenerationLog
from app.models.project import Project
from app.models.script import Script
from app.models.script_analysis import ScriptAnalysis
from app.models.video import Video
from app.models.video_asset import VideoAsset
from app.schemas.video import (
    AnalysisOut,
    AudioOut,
    LogOut,
    RenderParamsIn,
    ScriptOut,
    ScriptUpdate,
    VideoCreate,
    VideoOut,
    VideoUpdate,
    VisualAssetOut,
    VoiceOverrideIn,
)
from app.services import image_gen, tts_service
from app.services.pipeline import VALID_STAGES, PipelineOptions, clear_cancel, request_cancel, run_pipeline, run_pipeline_stage

router = APIRouter(prefix="/api", tags=["videos"])


@router.get("/image-models")
def get_image_models():
    """Список моделей, доступных для выбора при (пере)генерации видеоряда."""
    return image_gen.IMAGE_MODEL_OPTIONS


def _video_or_404(db: Session, video_id: str) -> Video:
    v = db.get(Video, video_id)
    if v is None:
        raise HTTPException(404, "Видео не найдено")
    return v


def _launch(video: Video, project: Project, payload: VideoCreate, bg: BackgroundTasks) -> None:
    langs = payload.languages or [project.language_primary, *project.languages_export]
    # уникализируем, сохраняя порядок
    seen: set[str] = set()
    langs = [l for l in langs if not (l in seen or seen.add(l))]
    options = PipelineOptions(
        languages=langs,
        target_duration_min=payload.target_duration_min,
        run_translate=payload.run_translate,
        run_tts=payload.run_tts,
        run_render=payload.run_render,
        run_visuals=payload.run_visuals,
        script_content=payload.script_content,
        script_prompts=payload.script_prompts,
    )
    bg.add_task(run_pipeline, video.id, options)


@router.get("/projects/{project_id}/videos", response_model=list[VideoOut])
def list_videos(project_id: str, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "Канал не найден")
    return (
        db.query(Video)
        .filter(Video.project_id == project_id)
        .order_by(Video.created_at.desc())
        .all()
    )


@router.post("/projects/{project_id}/videos", response_model=VideoOut, status_code=201)
def create_video(
    project_id: str,
    payload: VideoCreate,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Канал не найден")
    video = Video(
        project_id=project_id,
        title=payload.title,
        topic_brief=payload.topic_brief,
        status="draft",
        script_prompts=payload.script_prompts or {},
        music_track_id=project.default_music_track_id,
        music_volume=project.default_music_volume,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    _launch(video, project, payload, bg)
    return video


@router.get("/videos/{video_id}", response_model=VideoOut)
def get_video(video_id: str, db: Session = Depends(get_db)):
    return _video_or_404(db, video_id)


@router.patch("/videos/{video_id}", response_model=VideoOut)
def update_video(video_id: str, payload: VideoUpdate, db: Session = Depends(get_db)):
    video = _video_or_404(db, video_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(video, k, v)
    db.commit()
    db.refresh(video)
    return video


@router.put("/videos/{video_id}/voice/{lang}", response_model=VideoOut)
def set_voice_override(
    video_id: str, lang: str, payload: VoiceOverrideIn, db: Session = Depends(get_db)
):
    """Переопределяет голос канала для конкретного видео и языка.

    voice_id="" или null снимает override — дальше при озвучке снова
    используется голос, заданный в настройках канала.
    """
    video = _video_or_404(db, video_id)
    overrides = dict(video.voice_overrides or {})
    if payload.voice_id:
        overrides[lang] = payload.voice_id
    else:
        overrides.pop(lang, None)
    video.voice_overrides = overrides
    db.commit()
    db.refresh(video)
    return video


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: str, db: Session = Depends(get_db)):
    video = _video_or_404(db, video_id)
    db.delete(video)
    db.commit()


@router.get("/videos/{video_id}/scripts", response_model=list[ScriptOut])
def get_scripts(video_id: str, db: Session = Depends(get_db)):
    _video_or_404(db, video_id)
    return db.query(Script).filter(Script.video_id == video_id).all()


@router.patch("/videos/{video_id}/scripts/{lang}", response_model=ScriptOut)
def edit_script(video_id: str, lang: str, payload: ScriptUpdate, db: Session = Depends(get_db)):
    script = (
        db.query(Script)
        .filter(Script.video_id == video_id, Script.language == lang)
        .one_or_none()
    )
    if script is None:
        raise HTTPException(404, "Сценарий не найден")
    from app.core import paths
    from app.utils.text import count_words, estimate_duration_sec

    script.content_md = payload.content_md
    script.word_count = count_words(payload.content_md)
    script.duration_estimate_sec = estimate_duration_sec(payload.content_md)
    db.commit()
    db.refresh(script)
    video = db.get(Video, video_id)
    paths.script_file(video.project_id, video_id, lang).write_text(
        payload.content_md, encoding="utf-8"
    )
    return script


@router.get("/videos/{video_id}/analysis", response_model=AnalysisOut)
def get_analysis(video_id: str, db: Session = Depends(get_db)):
    primary = (
        db.query(Script)
        .filter(Script.video_id == video_id, Script.is_primary == True)  # noqa: E712
        .one_or_none()
    )
    if primary is None:
        raise HTTPException(404, "Основной сценарий не найден")
    analysis = (
        db.query(ScriptAnalysis).filter(ScriptAnalysis.script_id == primary.id).one_or_none()
    )
    if analysis is None:
        raise HTTPException(404, "Анализ ещё не готов")
    return analysis


@router.get("/videos/{video_id}/visuals", response_model=list[VisualAssetOut])
def get_visuals(video_id: str, db: Session = Depends(get_db)):
    """AI-картинки визуального ряда — только активная (не архивированная) версия."""
    _video_or_404(db, video_id)
    assets = (
        db.query(VideoAsset)
        .filter(VideoAsset.video_id == video_id, VideoAsset.type == "visual")
        .all()
    )
    active = [a for a in assets if not (a.asset_metadata or {}).get("archived", False)]
    result = active if active else assets
    result.sort(key=lambda a: (a.asset_metadata or {}).get("index", 0))
    return result


@router.get("/videos/{video_id}/visuals/history", response_model=list[VisualAssetOut])
def get_visuals_history(video_id: str, db: Session = Depends(get_db)):
    """Все версии визуального ряда (включая архивные), по убыванию версии."""
    _video_or_404(db, video_id)
    assets = (
        db.query(VideoAsset)
        .filter(VideoAsset.video_id == video_id, VideoAsset.type == "visual")
        .all()
    )
    assets.sort(
        key=lambda a: (
            -(a.asset_metadata or {}).get("version", 1),
            (a.asset_metadata or {}).get("index", 0),
        )
    )
    return assets


@router.put("/videos/{video_id}/visuals/activate/{version}", response_model=list[VisualAssetOut])
def activate_visuals_version(video_id: str, version: int, db: Session = Depends(get_db)):
    """Делает указанную версию визуального ряда активной (снимает archive с неё, архивирует остальные)."""
    _video_or_404(db, video_id)
    assets = (
        db.query(VideoAsset)
        .filter(VideoAsset.video_id == video_id, VideoAsset.type == "visual")
        .all()
    )
    existing_versions = {(a.asset_metadata or {}).get("version", 1) for a in assets}
    if version not in existing_versions:
        raise HTTPException(404, f"Версия {version} не найдена")
    activated = []
    for a in assets:
        meta = dict(a.asset_metadata or {})
        meta["archived"] = meta.get("version", 1) != version
        a.asset_metadata = meta
        if not meta["archived"]:
            activated.append(a)
    db.commit()
    activated.sort(key=lambda a: (a.asset_metadata or {}).get("index", 0))
    return activated


@router.get("/videos/{video_id}/visuals/all", response_model=list[VisualAssetOut])
def get_all_visuals(video_id: str, db: Session = Depends(get_db)):
    """Все картинки из всех версий (для редактора плейлиста)."""
    _video_or_404(db, video_id)
    assets = (
        db.query(VideoAsset)
        .filter(VideoAsset.video_id == video_id, VideoAsset.type == "visual")
        .all()
    )
    assets.sort(
        key=lambda a: (
            (a.asset_metadata or {}).get("version", 1),
            (a.asset_metadata or {}).get("index", 0),
        )
    )
    return assets


@router.get("/videos/{video_id}/visuals/playlist")
def get_visual_playlist(video_id: str, db: Session = Depends(get_db)):
    """Возвращает текущий плейлист (список asset_id в нужном порядке)."""
    video = _video_or_404(db, video_id)
    return {"playlist": video.visual_playlist or []}


@router.put("/videos/{video_id}/visuals/playlist")
def set_visual_playlist(video_id: str, body: dict, db: Session = Depends(get_db)):
    """Сохраняет плейлист — список asset_id в нужном порядке для рендера."""
    video = _video_or_404(db, video_id)
    playlist = body.get("playlist", [])
    # Проверяем что все переданные id реально существуют
    if playlist:
        existing = {
            a.id for a in db.query(VideoAsset)
            .filter(VideoAsset.video_id == video_id, VideoAsset.type == "visual")
            .all()
        }
        unknown = [aid for aid in playlist if aid not in existing]
        if unknown:
            raise HTTPException(400, f"Неизвестные asset_id: {unknown}")
    video.visual_playlist = playlist
    db.commit()
    return {"playlist": playlist}


@router.get("/videos/{video_id}/audio", response_model=list[AudioOut])
def get_audio(video_id: str, db: Session = Depends(get_db)):
    """Активные (не архивированные) аудиотреки — по одному на язык."""
    _video_or_404(db, video_id)
    scripts = db.query(Script).filter(Script.video_id == video_id).all()
    ids = [s.id for s in scripts]
    if not ids:
        return []
    all_tracks = db.query(AudioTrack).filter(AudioTrack.script_id.in_(ids)).all()
    # Для каждого script_id — только активный (не archived) с макс. версией
    by_script: dict[str, AudioTrack] = {}
    for t in all_tracks:
        if t.archived:
            continue
        prev = by_script.get(t.script_id)
        if prev is None or t.version > prev.version:
            by_script[t.script_id] = t
    return list(by_script.values())


@router.get("/videos/{video_id}/audio/history", response_model=list[AudioOut])
def get_audio_history(video_id: str, db: Session = Depends(get_db)):
    """Все версии аудиотреков включая архивные (по убыванию версии)."""
    _video_or_404(db, video_id)
    scripts = db.query(Script).filter(Script.video_id == video_id).all()
    ids = [s.id for s in scripts]
    if not ids:
        return []
    tracks = db.query(AudioTrack).filter(AudioTrack.script_id.in_(ids)).all()
    tracks.sort(key=lambda t: (-t.version, t.script_id))
    return tracks


@router.put("/videos/{video_id}/audio/{lang}/activate/{version}", response_model=list[AudioOut])
def activate_audio_version(video_id: str, lang: str, version: int, db: Session = Depends(get_db)):
    """Делает указанную версию аудио активной (снимает archive с неё, архивирует остальные)."""
    _video_or_404(db, video_id)
    script = (
        db.query(Script)
        .filter(Script.video_id == video_id, Script.language == lang)
        .one_or_none()
    )
    if script is None:
        raise HTTPException(404, f"Нет сценария на языке '{lang}'")
    tracks = db.query(AudioTrack).filter(AudioTrack.script_id == script.id).all()
    existing_versions = {t.version for t in tracks}
    if version not in existing_versions:
        raise HTTPException(404, f"Версия {version} не найдена")
    activated = []
    for t in tracks:
        t.archived = t.version != version
        if not t.archived:
            activated.append(t)
    db.commit()
    return activated


@router.get("/videos/{video_id}/renders/{lang}/history", response_model=list[VisualAssetOut])
def get_renders_history(video_id: str, lang: str, db: Session = Depends(get_db)):
    """Все версии финальных рендеров для языка (включая архивные)."""
    _video_or_404(db, video_id)
    assets = (
        db.query(VideoAsset)
        .filter(VideoAsset.video_id == video_id, VideoAsset.type == "final", VideoAsset.language == lang)
        .all()
    )
    assets.sort(key=lambda a: -(a.asset_metadata or {}).get("version", 1))
    return assets


@router.put("/videos/{video_id}/renders/{lang}/activate/{version}", response_model=list[VisualAssetOut])
def activate_render_version(video_id: str, lang: str, version: int, db: Session = Depends(get_db)):
    """Делает указанную версию финального рендера активной."""
    _video_or_404(db, video_id)
    assets = (
        db.query(VideoAsset)
        .filter(VideoAsset.video_id == video_id, VideoAsset.type == "final", VideoAsset.language == lang)
        .all()
    )
    existing_versions = {(a.asset_metadata or {}).get("version", 1) for a in assets}
    if version not in existing_versions:
        raise HTTPException(404, f"Версия {version} не найдена")
    activated = []
    for a in assets:
        meta = dict(a.asset_metadata or {})
        meta["archived"] = meta.get("version", 1) != version
        a.asset_metadata = meta
        if not meta["archived"]:
            activated.append(a)
    db.commit()
    return activated


@router.get("/videos/{video_id}/logs", response_model=list[LogOut])
def get_logs(video_id: str, db: Session = Depends(get_db)):
    _video_or_404(db, video_id)
    return (
        db.query(GenerationLog)
        .filter(GenerationLog.video_id == video_id)
        .order_by(GenerationLog.created_at.asc())
        .all()
    )


@router.post("/videos/{video_id}/rerun", response_model=VideoOut, status_code=202)
def rerun(
    video_id: str,
    payload: VideoCreate,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Перезапускает ВЕСЬ пайплайн для существующего видео (с новыми опциями).

    Для точечного перезапуска одной стадии используйте
    POST /videos/{id}/stages/{stage}.
    """
    video = _video_or_404(db, video_id)
    project = db.get(Project, video.project_id)
    if payload.topic_brief and payload.topic_brief != video.topic_brief:
        video.topic_brief = payload.topic_brief
        db.commit()
    clear_cancel(video_id)
    _launch(video, project, payload, bg)
    return video


@router.post("/videos/{video_id}/stages/{stage}", status_code=202)
def rerun_stage(
    video_id: str,
    stage: str,
    bg: BackgroundTasks,
    lang: str | None = None,
    visual_engine: str = "replicate",
    db: Session = Depends(get_db),
):
    """Точечно перезапускает одну стадию (analysis/translate/tts/thumbnail/render).

    Не трогает результаты остальных стадий — удобно доделать вручную то,
    что не получилось автоматически (например, после установки Kokoro или
    загрузки аудио руками перезапустить только TTS/render для одного языка).
    """
    _video_or_404(db, video_id)
    if stage not in VALID_STAGES:
        raise HTTPException(400, f"Неизвестная стадия: {stage}. Допустимые: {sorted(VALID_STAGES)}")
    if stage in {"translate", "tts", "render"} and not lang:
        raise HTTPException(400, f"Для стадии '{stage}' нужен параметр lang")

    # Сбрасываем stuck "running"-лог для этой стадии прямо сейчас, до старта фонового таска.
    # Иначе фронт на первом же poll видит старую запись с давним created_at и кажет неверный таймер.
    stage_key = f"{stage}:{lang}" if lang else stage
    logger.debug("[rerun_stage] stage={stage_key} vid={vid}", stage_key=stage_key, vid=video_id[:8])
    stuck = (
        db.query(GenerationLog)
        .filter(
            GenerationLog.video_id == video_id,
            GenerationLog.stage == stage_key,
            GenerationLog.status == "running",
        )
        .all()
    )
    for s in stuck:
        s.status = "error"
        s.error_message = "Прерван (перезапуск стадии)"
        s.duration_sec = 0
    if stuck:
        logger.debug("[rerun_stage] сброшено {n} stuck running-логов для {stage_key} vid={vid}", n=len(stuck), stage_key=stage_key, vid=video_id[:8])
        db.commit()

    # Снимаем флаг отмены — иначе новый запуск сразу получит "Отменено пользователем"
    clear_cancel(video_id)
    bg.add_task(run_pipeline_stage, video_id, stage, lang, visual_engine)
    logger.debug("[rerun_stage] фоновая задача поставлена: stage={stage_key} vid={vid}", stage_key=stage_key, vid=video_id[:8])
    return {"status": "started", "stage": stage, "lang": lang}


@router.post("/videos/{video_id}/cancel", status_code=202)
def cancel_pipeline(video_id: str, db: Session = Depends(get_db)):
    """Запрашивает отмену текущего пайплайна (флаг проверяется между шагами генерации).

    Немедленно помечает все зависшие running-логи как cancelled и устанавливает
    флаг отмены — пайплайн остановится при следующей проверке.
    """
    _video_or_404(db, video_id)
    logger.debug("[cancel] cancel_pipeline запрос vid={vid}", vid=video_id[:8])
    request_cancel(video_id)
    # Сразу обновляем зависшие логи, чтобы UI разблокировался без ожидания
    stuck = (
        db.query(GenerationLog)
        .filter(GenerationLog.video_id == video_id, GenerationLog.status == "running")
        .all()
    )
    for s in stuck:
        s.status = "error"
        s.error_message = "Отменено пользователем"
        s.duration_sec = s.duration_sec if s.duration_sec is not None else 0.0
    if stuck:
        logger.debug("[cancel] помечено error {n} running-логов для vid={vid}: {stages}", n=len(stuck), vid=video_id[:8], stages=[s.stage for s in stuck])
        db.commit()
    # Если реально бегущего пайплайна нет (stuck-лог от прошлого запуска) —
    # сразу снимаем флаг, чтобы следующий запуск не получил "Отменено пользователем".
    if not stuck:
        logger.debug("[cancel] running-логов нет — флаг отмены сразу снят для vid={vid}", vid=video_id[:8])
        clear_cancel(video_id)
    return {"status": "cancel_requested"}


@router.put("/videos/{video_id}/render_params", response_model=VideoOut)
def set_render_params(
    video_id: str, payload: RenderParamsIn, db: Session = Depends(get_db)
):
    """Сохраняет параметры монтажного рендера (разрешение, зум, цветокор).

    Применяются при следующем вызове POST /stages/render.
    """
    video = _video_or_404(db, video_id)
    video.render_params = payload.model_dump()
    db.commit()
    db.refresh(video)
    return video


class MusicSettingsIn(BaseModel):
    music_track_id: str | None = None
    music_volume: float = 0.15


@router.put("/videos/{video_id}/music", response_model=VideoOut)
def set_music(video_id: str, payload: MusicSettingsIn, db: Session = Depends(get_db)):
    """Устанавливает фоновую музыку и громкость для видео."""
    video = _video_or_404(db, video_id)
    video.music_track_id = payload.music_track_id
    video.music_volume = max(0.0, min(1.0, payload.music_volume))
    db.commit()
    db.refresh(video)
    return video


@router.post("/videos/{video_id}/audio/{lang}", response_model=AudioOut)
async def upload_audio(
    video_id: str,
    lang: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Ручная загрузка готовой озвучки для языка (когда TTS не настроен/не справился).

    Принимает аудиофайл любого формата, который понимает FFmpeg (wav/mp3/...).
    После загрузки можно перезапустить стадию render: POST /stages/render?lang=...
    """
    video = _video_or_404(db, video_id)
    script = (
        db.query(Script)
        .filter(Script.video_id == video_id, Script.language == lang)
        .one_or_none()
    )
    if script is None:
        raise HTTPException(404, f"Нет сценария на языке '{lang}' — сначала сгенерируйте/переведите его")

    suffix = Path(file.filename or "").suffix or ".wav"
    out_path = paths.audio_dir(video.project_id, video_id) / f"{lang}{suffix}"
    content = await file.read()
    out_path.write_bytes(content)

    duration = tts_service.probe_duration_sec(out_path)
    track = db.query(AudioTrack).filter(AudioTrack.script_id == script.id).one_or_none()
    if track is None:
        track = AudioTrack(script_id=script.id)
        db.add(track)
    track.file_path = str(out_path)
    track.duration_sec = duration
    track.voice_id = "manual-upload"
    track.engine = "manual"
    track.status = "ready"
    db.commit()
    db.refresh(track)
    return track


# ---------------------------------------------------------------------------
# Thumbnail history
# ---------------------------------------------------------------------------

class ThumbnailEntry(BaseModel):
    version: int
    created_at: str
    model: str
    prompt: str
    file: str
    archived_file: str | None = None


@router.get("/videos/{video_id}/thumbnail-history", response_model=list[ThumbnailEntry])
def get_thumbnail_history(video_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Видео не найдено")
    history_path = paths.thumbnail_file(video.project_id, video_id).parent / "thumbnail_history.json"
    if not history_path.exists():
        return []
    import json
    try:
        return json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return []


class RestoreVersionIn(BaseModel):
    version: int


@router.post("/videos/{video_id}/thumbnail-restore")
def restore_thumbnail_version(video_id: str, body: RestoreVersionIn, db: Session = Depends(get_db)):
    """Устанавливает старую версию обложки как текущую."""
    import json, shutil
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Видео не найдено")
    thumb_dir = paths.thumbnail_file(video.project_id, video_id).parent
    history_path = thumb_dir / "thumbnail_history.json"
    if not history_path.exists():
        raise HTTPException(404, "История обложек не найдена")
    history = json.loads(history_path.read_text(encoding="utf-8"))
    entry = next((e for e in history if e["version"] == body.version), None)
    if not entry:
        raise HTTPException(404, f"Версия {body.version} не найдена")
    src = thumb_dir / (entry.get("archived_file") or entry["file"])
    if not src.exists():
        raise HTTPException(404, f"Файл версии не найден: {src.name}")
    thumb_path = thumb_dir / "thumbnail.png"
    shutil.copy2(str(src), str(thumb_path))
    return {"status": "ok", "restored_version": body.version}


# ---------------------------------------------------------------------------
# Превью монтажа
# ---------------------------------------------------------------------------

_PREVIEW_SEG_SEC = 4.0
_PREVIEW_MAX_IMAGES = 3


@router.post("/videos/{video_id}/preview-render")
def preview_render(video_id: str, db: Session = Depends(get_db)):
    """Быстрый превью-ролик (~12 сек, без звука) с текущими параметрами монтажа.

    Берёт первые картинки визуального ряда (или плейлиста) и собирает короткий
    mp4, чтобы оценить зум/панораму/цветокор/частицы, не рендеря всё видео.
    """
    from app.services import video_builder

    video = _video_or_404(db, video_id)
    project = db.get(Project, video.project_id)

    playlist_ids: list[str] = video.visual_playlist or []
    if playlist_ids:
        asset_map = {
            a.id: a for a in db.query(VideoAsset)
            .filter(VideoAsset.video_id == video_id, VideoAsset.type == "visual")
            .all()
        }
        visuals = [asset_map[aid] for aid in playlist_ids if aid in asset_map]
    else:
        assets = (
            db.query(VideoAsset)
            .filter(VideoAsset.video_id == video_id, VideoAsset.type == "visual")
            .all()
        )
        visuals = [a for a in assets if not (a.asset_metadata or {}).get("archived", False)]
        visuals.sort(key=lambda a: (a.asset_metadata or {}).get("index", 0))
    images = [Path(a.file_path) for a in visuals if a.file_path and Path(a.file_path).exists()]
    if not images:
        raise HTTPException(400, "Сначала сгенерируйте визуальный ряд (блок «Визуальный ряд (AI)»)")
    images = images[:_PREVIEW_MAX_IMAGES]

    rp = video.render_params or {}
    overlay = rp.get("overlay")
    if overlay is None:
        overlay = "embers" if project and project.particles_enabled else "off"

    out = paths.video_dir(video.project_id, video_id) / "preview_montage.mp4"
    try:
        video_builder.render_video_segments(
            images=[(p, _PREVIEW_SEG_SEC) for p in images],
            audio_path=None,
            out_path=out,
            particles=overlay,
            resolution=rp.get("resolution", "720p"),
            zoom=rp.get("zoom", "subtle"),
            zoom_speed=rp.get("zoom_speed"),
            zoom_direction=rp.get("zoom_direction", "in"),
            warm_grade=bool(rp.get("warm_grade", True)),
            grade=rp.get("grade"),
            vignette=bool(rp.get("vignette", False)),
            grain=bool(rp.get("grain", False)),
            transition=rp.get("transition", "none"),
            fade_in=bool(rp.get("fade_in", False)),
            fade_out=bool(rp.get("fade_out", False)),
        )
    except video_builder.RenderError as e:
        raise HTTPException(500, str(e)) from e
    return {"url": f"/projects/{video.project_id}/videos/{video_id}/preview_montage.mp4"}


# ---------------------------------------------------------------------------
# Пакет публикации YouTube
# ---------------------------------------------------------------------------


@router.get("/videos/{video_id}/youtube-package")
def youtube_package(video_id: str, db: Session = Depends(get_db)):
    """Готовые метаданные для загрузки на YouTube: заголовки, описание, теги."""
    video = _video_or_404(db, video_id)
    scripts = db.query(Script).filter(Script.video_id == video_id).all()
    if not scripts:
        raise HTTPException(404, "У видео ещё нет сценария")
    primary = next((s for s in scripts if s.is_primary), scripts[0])
    analysis = (
        db.query(ScriptAnalysis).filter(ScriptAnalysis.script_id == primary.id).first()
    )
    if analysis is None:
        raise HTTPException(404, "Анализ сценария ещё не готов (стадия analysis)")

    titles = list(analysis.title_suggestions or []) or [video.title]
    tags = list(analysis.youtube_tags or [])
    # YouTube ограничивает суммарную длину тегов 500 символами
    tags_str = ""
    kept: list[str] = []
    for t in tags:
        candidate = ", ".join([*kept, t])
        if len(candidate) > 480:
            break
        kept.append(t)
        tags_str = candidate

    parts = [analysis.hook, "", analysis.summary_long]
    if analysis.key_points:
        parts += ["", "В этом видео:", *[f"• {p}" for p in analysis.key_points]]
    description = "\n".join(p for p in parts if p is not None)

    return {
        "titles": titles,
        "description": description,
        "tags": kept,
        "tags_string": tags_str,
    }


# ---------------------------------------------------------------------------
# Субтитры (.srt, приблизительные тайминги)
# ---------------------------------------------------------------------------


def _fmt_srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


@router.get("/videos/{video_id}/subtitles/{lang}")
def get_subtitles(video_id: str, lang: str, db: Session = Depends(get_db)):
    """Экспорт субтитров .srt с ПРИБЛИЗИТЕЛЬНЫМИ таймингами.

    Тайминги распределяются по предложениям пропорционально числу слов
    относительно длительности готового аудио. Для точных таймингов нужен
    Whisper (в планах).
    """
    import re

    from fastapi.responses import Response

    _video_or_404(db, video_id)
    script = (
        db.query(Script)
        .filter(Script.video_id == video_id, Script.language == lang)
        .first()
    )
    if script is None:
        raise HTTPException(404, f"Нет сценария на языке {lang}")

    track = (
        db.query(AudioTrack)
        .filter(AudioTrack.script_id == script.id, AudioTrack.status == "ready")
        .order_by(AudioTrack.created_at.desc())
        .first()
    )
    total_sec = float(track.duration_sec) if track and track.duration_sec else float(
        script.duration_estimate_sec or 0
    )
    if total_sec <= 0:
        raise HTTPException(400, "Неизвестна длительность аудио — сначала озвучьте сценарий")

    # Чистим markdown: заголовки, маркеры списков, жирный/курсив, ремарки в скобках
    text = script.content_md
    text = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.MULTILINE)  # заголовки — не речь
    text = re.sub(r"[*_`>#]+", "", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]
    if not sentences:
        raise HTTPException(400, "Сценарий пуст")

    word_counts = [max(1, len(s.split())) for s in sentences]
    total_words = sum(word_counts)

    lines: list[str] = []
    cursor = 0.0
    for idx, (sent, wc) in enumerate(zip(sentences, word_counts), start=1):
        dur = total_sec * wc / total_words
        start, end = cursor, cursor + dur
        cursor = end
        # Длинные предложения не держим на экране дольше 8 сек — обрезаем показ
        show_end = min(end, start + 8.0)
        lines += [str(idx), f"{_fmt_srt_time(start)} --> {_fmt_srt_time(show_end)}", sent, ""]

    srt = "\n".join(lines)
    return Response(
        content=srt,
        media_type="application/x-subrip",
        headers={
            "Content-Disposition": f'attachment; filename="subtitles_{lang}.srt"',
        },
    )


# ---------------------------------------------------------------------------
# Открыть папку видео в проводнике (локальное приложение)
# ---------------------------------------------------------------------------


@router.post("/videos/{video_id}/open-folder")
def open_video_folder(video_id: str, db: Session = Depends(get_db)):
    """Открывает папку видео (сценарии, аудио, финальные mp4) в проводнике ОС.

    Приложение локальное (см. CLAUDE.md — без auth), поэтому открытие
    папки на машине пользователя — ожидаемое поведение.
    """
    import os
    import subprocess
    import sys

    video = _video_or_404(db, video_id)
    folder = paths.video_dir(video.project_id, video_id)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(folder))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except OSError as e:
        raise HTTPException(500, f"Не удалось открыть папку: {e}") from e
    return {"folder": str(folder)}
