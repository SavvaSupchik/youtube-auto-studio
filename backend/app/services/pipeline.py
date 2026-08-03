"""Оркестратор пайплайна генерации видео.

Последовательность стадий (см. CLAUDE.md §7). Каждая стадия:
- логируется в generation_logs;
- публикует событие прогресса в broker (для WebSocket);
- идемпотентна настолько, насколько возможно (повторный запуск пересоздаёт артефакты).

Запускается в фоне (BackgroundTasks) с собственной сессией БД.

Отказоустойчивость: только генерация сценария (стадия "script") считается
критичной — без неё нет вообще никакого результата. Все стадии после неё
(анализ, перевод на каждый язык, озвучка на каждый язык, обложка, рендер на
каждый язык) — независимые "блоки": ошибка в одном блоке логируется в
generation_logs и видна в UI, но не останавливает остальные блоки и не
переводит видео в статус "error". Это позволяет вручную доделать только
сломавшуюся часть (например, загрузить аудио руками или перезапустить
конкретную стадию через /videos/{id}/stages/{stage}), не теряя то, что уже
сгенерировалось.
"""
from __future__ import annotations

import json
import random
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
import time

from app.core import paths
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.jobs import broker
from app.core.llm import LLMResult
from app.models.audio import AudioTrack
from app.models.generation_log import GenerationLog
from app.models.project import Project
from app.models.script import Script
from app.models.script_analysis import ScriptAnalysis
from app.models.video import Video
from app.models.video_asset import VideoAsset
from app.services import (
    app_settings,
    image_gen,
    script_analyzer,
    script_chain,
    script_generator,
    thumbnail_gen,
    translator,
    tts_service,
    video_builder,
)
from app.services.memory_service import append_memory, format_memory_for_prompt, read_memory
from app.utils.text import count_words, estimate_duration_sec


@dataclass
class PipelineOptions:
    languages: list[str]
    target_duration_min: int | None = None
    run_translate: bool = True
    run_tts: bool = False
    run_render: bool = False
    # AI-визуальный ряд (Replicate/FLUX): картинка по контексту сценария,
    # меняется каждые settings.visual_segment_minutes минут видео. Опционально
    # и платно — генерируется только если явно запрошено.
    run_visuals: bool = False
    # Готовый сценарий на основном языке — если задан, Claude для генерации
    # сценария не вызывается, текст сохраняется как есть.
    script_content: str | None = None
    # Адаптированные промты 3-шаговой цепочки {stage1, stage2, stage3}. Если
    # заданы — используются как есть (шаг адаптации пропускается). Если нет —
    # шаблоны адаптируются под тему автоматически внутри стадии script.
    script_prompts: dict[str, str] | None = None


def _publish(video_id: str, **payload: Any) -> None:
    broker.publish(video_id, payload)


# Множество video_id, для которых пользователь запросил отмену.
# In-memory — сбрасывается при рестарте сервера (и это нормально).
_cancel_requested: set[str] = set()


def request_cancel(video_id: str) -> None:
    """Помечает видео для отмены; пайплайн проверяет флаг между шагами."""
    logger.debug("[cancel] request_cancel vid={vid} | очередь отмены: {q}", vid=video_id[:8], q=len(_cancel_requested) + 1)
    _cancel_requested.add(video_id)


def clear_cancel(video_id: str) -> None:
    """Снимает флаг отмены. Вызывается перед запуском новой стадии,
    чтобы старый cancel не блокировал следующие запуски."""
    if video_id in _cancel_requested:
        logger.debug("[cancel] clear_cancel: флаг СНЯТ для vid={vid}", vid=video_id[:8])
        _cancel_requested.discard(video_id)
    else:
        logger.debug("[cancel] clear_cancel: флага не было для vid={vid}", vid=video_id[:8])


def _check_cancel(video_id: str) -> None:
    """Бросает RuntimeError если для видео запрошена отмена."""
    if video_id in _cancel_requested:
        logger.debug("[cancel] _check_cancel: СРАБАТЫВАНИЕ → RuntimeError для vid={vid}", vid=video_id[:8])
        _cancel_requested.discard(video_id)
        raise RuntimeError("Отменено пользователем")
    logger.debug("[cancel] _check_cancel: флага нет, продолжаем vid={vid}", vid=video_id[:8])


@contextmanager
def _stage(db, video_id: str, stage: str, llm_holder: dict | None = None):
    """Контекст одной стадии: лог в БД + события прогресса + замер времени."""
    # Если предыдущий запуск этой стадии завис (сервер упал) — сбрасываем его.
    stuck = (
        db.query(GenerationLog)
        .filter(
            GenerationLog.video_id == video_id,
            GenerationLog.stage == stage,
            GenerationLog.status == "running",
        )
        .all()
    )
    for s in stuck:
        s.status = "error"
        s.error_message = "Прерван (перезапуск сервера)"
        s.duration_sec = 0
    if stuck:
        logger.debug("[stage] сброшено {n} зависших running-логов для stage={stage} vid={vid}", n=len(stuck), stage=stage, vid=video_id[:8])
        db.commit()

    log = GenerationLog(video_id=video_id, stage=stage, status="running")
    db.add(log)
    db.commit()
    logger.debug("[stage] START stage={stage} vid={vid} log_id={lid}", stage=stage, vid=video_id[:8], lid=str(log.id)[:8])
    _publish(video_id, type="stage_start", stage=stage)
    started = time.monotonic()
    try:
        yield log
    except Exception as e:  # noqa: BLE001
        elapsed = time.monotonic() - started
        log.status = "error"
        log.error_message = str(e)
        log.duration_sec = elapsed
        db.commit()
        logger.debug("[stage] ERROR stage={stage} vid={vid} dur={dur:.1f}s err={err}", stage=stage, vid=video_id[:8], dur=elapsed, err=str(e)[:120])
        _publish(video_id, type="stage_error", stage=stage, error=str(e))
        raise
    else:
        elapsed = time.monotonic() - started
        log.status = "ok"
        log.duration_sec = elapsed
        db.commit()
        logger.debug("[stage] OK stage={stage} vid={vid} dur={dur:.1f}s", stage=stage, vid=video_id[:8], dur=elapsed)
        _publish(
            video_id,
            type="stage_done",
            stage=stage,
            duration_sec=round(elapsed, 2),
        )


def _record_llm(log: GenerationLog, result: LLMResult | None) -> None:
    if result is None:
        return
    log.model_used = result.model
    log.input_tokens = result.input_tokens
    log.output_tokens = result.output_tokens
    log.cost_usd = result.cost_usd


def _save_script_row(db, video: Video, language: str, content: str, is_primary: bool) -> Script:
    """Создаёт/обновляет Script на языке и пишет файл script_<lang>.md."""
    existing = (
        db.query(Script)
        .filter(Script.video_id == video.id, Script.language == language)
        .one_or_none()
    )
    wc = count_words(content)
    dur = estimate_duration_sec(content)
    if existing:
        existing.content_md = content
        existing.word_count = wc
        existing.duration_estimate_sec = dur
        existing.is_primary = is_primary
        script = existing
    else:
        script = Script(
            video_id=video.id,
            language=language,
            content_md=content,
            word_count=wc,
            duration_estimate_sec=dur,
            is_primary=is_primary,
        )
        db.add(script)
    db.commit()
    db.refresh(script)

    path = paths.script_file(video.project_id, video.id, language)
    path.write_text(content, encoding="utf-8")
    return script


def _get_script(db, video_id: str, lang: str) -> Script | None:
    return (
        db.query(Script)
        .filter(Script.video_id == video_id, Script.language == lang)
        .one_or_none()
    )


def _get_primary_script(db, video_id: str) -> Script | None:
    return (
        db.query(Script)
        .filter(Script.video_id == video_id, Script.is_primary == True)  # noqa: E712
        .one_or_none()
    )


def _get_audio_track(db, video_id: str, lang: str) -> AudioTrack | None:
    """Активный (не архивированный) аудиотрек для языка."""
    script = _get_script(db, video_id, lang)
    if script is None:
        return None
    tracks = db.query(AudioTrack).filter(AudioTrack.script_id == script.id).all()
    active = [t for t in tracks if not t.archived]
    if active:
        return max(active, key=lambda t: t.version)
    # Fallback: если все архивированы — берём с наибольшей версией
    return max(tracks, key=lambda t: t.version) if tracks else None


def _upsert_asset(db, video_id: str, language: str | None, asset_type: str, file_path: str) -> None:
    q = db.query(VideoAsset).filter(
        VideoAsset.video_id == video_id, VideoAsset.type == asset_type
    )
    if language is not None:
        q = q.filter(VideoAsset.language == language)
    asset = q.one_or_none()
    if asset is None:
        asset = VideoAsset(video_id=video_id, language=language, type=asset_type)
        db.add(asset)
    asset.file_path = file_path
    db.commit()


# ---------------------------------------------------------------------------
# Отдельные стадии — каждая самодостаточна, чтобы её можно было перезапустить
# вручную через /videos/{id}/stages/{stage}, не трогая остальные.
# ---------------------------------------------------------------------------


def _set_title_from_content(db, video: Video, content: str) -> None:
    if not video.title and content.strip():
        first_line = content.strip().splitlines()[0][:120]
        video.title = first_line.lstrip("# ").strip()
        db.commit()


def _stage_script(
    db,
    video: Video,
    project: Project,
    target_duration_min: int | None,
    manual_content: str | None = None,
    preset_prompts: dict[str, str] | None = None,
) -> Script:
    """Генерирует основной сценарий.

    Режимы:
    - manual_content задан -> текст сохраняется как есть (одна стадия "script");
    - иначе -> 3-шаговая цепочка: адаптация шаблонов под тему -> бриф ->
      черновик -> авто-аудит/очеловечивание. Каждый шаг логируется отдельно
      ("script:adapt/prep/write/humanize"), промежуточные результаты пишутся
      в pipeline/prep.md и pipeline/draft.md.

    Критичны адаптация, бриф и черновик — без них сценария нет. Очеловечивание
    не критично: если упало, в качестве финала берётся черновик.
    """
    primary_lang = project.language_primary

    if manual_content and manual_content.strip():
        with _stage(db, video.id, "script"):
            content = manual_content.strip()
            primary_script = _save_script_row(db, video, primary_lang, content, True)
            _set_title_from_content(db, video, content)
        return primary_script

    duration = target_duration_min or script_generator.DEFAULT_DURATION_MIN

    # [0] ADAPT — переписываем шаблоны под тему (если промты ещё не готовы)
    prompts = preset_prompts or (video.script_prompts or None)
    has_all = bool(prompts) and all((prompts or {}).get(k) for k in ("stage1", "stage2", "stage3"))
    if not has_all:
        with _stage(db, video.id, "script:adapt") as log:
            ar = script_chain.adapt_prompts(project, video.topic_brief, primary_lang)
            _record_llm(log, ar.llm)
            prompts = ar.prompts
            video.script_prompts = prompts
            db.commit()
    elif video.script_prompts != prompts:
        video.script_prompts = prompts
        db.commit()

    memory_str = format_memory_for_prompt(read_memory(project.id, limit=40))

    # [1] PREP — бриф
    with _stage(db, video.id, "script:prep") as log:
        pr = script_chain.run_prep(prompts["stage1"], video.topic_brief, primary_lang, memory_str, duration)
        _record_llm(log, pr.llm)
        paths.pipeline_step_file(project.id, video.id, "prep").write_text(pr.text, encoding="utf-8")

    # [2] WRITE — черновик сценария; сохраняем в БД сразу, чтобы не потерять
    # при перезапуске процесса (например, если HUMANIZE упадёт на следующем шаге).
    with _stage(db, video.id, "script:write") as log:
        wr = script_chain.run_write(prompts["stage2"], pr.text, primary_lang, duration)
        _record_llm(log, wr.llm)
        paths.pipeline_step_file(project.id, video.id, "draft").write_text(wr.text, encoding="utf-8")
    primary_script = _save_script_row(db, video, primary_lang, wr.text, True)
    _set_title_from_content(db, video, wr.text)

    # [3] HUMANIZE — авто-аудит и чистовой текст (не критично: при сбое
    # сценарий уже сохранён как черновик — пользователь хотя бы не теряет всё).
    try:
        with _stage(db, video.id, "script:humanize") as log:
            hr = script_chain.run_humanize(prompts["stage3"], wr.text, primary_lang)
            _record_llm(log, hr.llm)
            if hr.text and hr.text.strip():
                primary_script = _save_script_row(db, video, primary_lang, hr.text, True)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Очеловечивание сценария видео {vid} не удалось, оставляю черновик: {err}",
            vid=video.id, err=e,
        )

    return primary_script


def _stage_analysis(db, video: Video, project: Project, primary_script: Script) -> None:
    with _stage(db, video.id, "analysis") as log:
        ares = script_analyzer.analyze_script(primary_script.content_md)
        _record_llm(log, ares.llm)
        a = ares.analysis
        analysis = (
            db.query(ScriptAnalysis)
            .filter(ScriptAnalysis.script_id == primary_script.id)
            .one_or_none()
        )
        if analysis is None:
            analysis = ScriptAnalysis(script_id=primary_script.id)
            db.add(analysis)
        analysis.hook = a.hook
        analysis.summary_short = a.summary_short
        analysis.summary_long = a.summary_long
        analysis.key_points = a.key_points
        analysis.topics = a.topics
        analysis.structure = a.structure
        analysis.tone = a.tone
        analysis.title_suggestions = a.title_suggestions
        analysis.youtube_tags = a.youtube_tags
        db.commit()

        append_memory(
            project.id,
            {
                "video_id": video.id,
                "created_at": video.created_at.date().isoformat(),
                "title": video.title,
                "hook": a.hook,
                "summary_short": a.summary_short,
                "key_points": a.key_points,
                "topics": a.topics,
                "structure": a.structure,
            },
        )
        paths.analysis_file(project.id, video.id).write_text(
            json.dumps(
                {
                    "hook": a.hook,
                    "summary_short": a.summary_short,
                    "summary_long": a.summary_long,
                    "key_points": a.key_points,
                    "topics": a.topics,
                    "structure": a.structure,
                    "tone": a.tone,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _stage_translate(db, video: Video, project: Project, primary_script: Script, lang: str) -> None:
    with _stage(db, video.id, f"translate:{lang}") as log:
        tr = translator.translate_script(primary_script.content_md, project.language_primary, lang)
        _record_llm(log, tr.llm)
        _save_script_row(db, video, lang, tr.content, False)


def _stage_tts(db, video: Video, project: Project, lang: str) -> None:
    script = _get_script(db, video.id, lang)
    if script is None:
        raise RuntimeError(f"Нет сценария на языке {lang} — сначала сгенерируйте/переведите его.")
    with _stage(db, video.id, f"tts:{lang}"):
        # Архивируем старые треки, определяем следующую версию
        old_tracks = db.query(AudioTrack).filter(AudioTrack.script_id == script.id).all()
        max_ver = max((t.version for t in old_tracks), default=0)
        new_ver = max_ver + 1
        for t in old_tracks:
            t.archived = True
        if old_tracks:
            db.commit()
            logger.debug("[tts] архивировано {n} треков для {lang}, новая версия={v}", n=len(old_tracks), lang=lang, v=new_ver)

        out = paths.audio_file(project.id, video.id, lang, version=new_ver)
        # Приоритет голоса: видео (override) > канал > глобальный дефолт.
        effective_voices = {
            **app_settings.get_default_voices(),
            **(project.voice_settings or {}),
            **(video.voice_overrides or {}),
        }
        voice_params = app_settings.get_voice_params()
        res = tts_service.synthesize(
            text=script.content_md,
            language=lang,
            out_path=out,
            tts_mode=project.tts_mode,
            voice_settings=effective_voices,
            voice_params=voice_params,
        )
        # Если включено интро канала — синтезируем его и склеиваем с основным аудио
        final_audio_path = res.file_path
        final_duration = res.duration_sec
        if project.intro_enabled and project.tts_mode != "manual" and res.status == "ready":
            try:
                intro_text = (project.intro_template or "").format(
                    channel=project.name,
                    topic=video.title or video.topic_brief,
                )
                intro_out = paths.intro_audio_file(project.id, video.id, lang)
                tts_service.synthesize(
                    text=intro_text,
                    language=lang,
                    out_path=intro_out,
                    tts_mode="local",
                    voice_settings=effective_voices,
                    voice_params=voice_params,
                )
                if intro_out.exists():
                    merged = paths.audio_with_intro_file(project.id, video.id, lang, version=new_ver)
                    video_builder.prepend_intro_audio(intro_out, Path(res.file_path), merged)
                    if merged.exists():
                        final_audio_path = str(merged)
                        # Пересчитываем длительность
                        import wave
                        try:
                            with wave.open(str(merged), "rb") as wf:
                                final_duration = int(wf.getnframes() / wf.getframerate())
                        except Exception:
                            pass
                        logger.info("[tts] интро склеено для {lang}, итого ~{d}с", lang=lang, d=final_duration)
            except Exception as e:  # noqa: BLE001
                logger.warning("[tts] не удалось добавить интро для {lang}: {err}", lang=lang, err=e)

        track = AudioTrack(
            script_id=script.id,
            file_path=final_audio_path,
            duration_sec=final_duration,
            voice_id=res.voice_id,
            engine=res.engine,
            status="ready" if res.status == "ready" else "failed",
            version=new_ver,
            archived=False,
        )
        db.add(track)
        db.commit()


def _stage_thumbnail(db, video: Video, project: Project) -> None:
    import json as _json
    import shutil as _shutil
    from datetime import datetime as _dt

    with _stage(db, video.id, "thumbnail"):
        thumb_path = paths.thumbnail_file(project.id, video.id)
        history_path = thumb_path.parent / "thumbnail_history.json"

        # Читаем историю и архивируем текущую обложку
        history: list[dict] = []
        if history_path.exists():
            try:
                history = _json.loads(history_path.read_text(encoding="utf-8"))
            except Exception:
                history = []
        if thumb_path.exists() and history:
            last_ver = history[-1]["version"]
            archived = thumb_path.parent / f"thumbnail_v{last_ver}.png"
            _shutil.copy2(str(thumb_path), str(archived))
            history[-1]["archived_file"] = archived.name

        result = thumbnail_gen.generate_thumbnail(
            title=video.title,
            out_path=thumb_path,
            accent_color=project.accent_color,
            niche=project.niche or "",
            style_hint=project.style_prompt[:200] if project.style_prompt else "",
        )

        history.append({
            "version": len(history) + 1,
            "created_at": _dt.utcnow().isoformat(),
            "model": result.model,
            "prompt": result.prompt,
            "file": "thumbnail.png",
        })
        history_path.write_text(
            _json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _upsert_asset(db, video.id, None, "thumbnail", str(thumb_path))


# Примерная стоимость одной картинки FLUX schnell на Replicate — для статистики.
_IMAGE_COST_USD = 0.003
# + апскейл Real-ESRGAN, если включён (settings.visual_upscale)
_UPSCALE_COST_USD = 0.004


def _get_visual_assets(db, video_id: str) -> list[VideoAsset]:
    """Картинки визуального ряда (язык-независимы), только активная версия, по порядку."""
    assets = (
        db.query(VideoAsset)
        .filter(VideoAsset.video_id == video_id, VideoAsset.type == "visual")
        .all()
    )
    active = [a for a in assets if not (a.asset_metadata or {}).get("archived", False)]
    result = active if active else assets  # fallback: если архивированы все — берём все
    result.sort(key=lambda a: (a.asset_metadata or {}).get("index", 0))
    return result


def _stage_visuals(db, video: Video, project: Project, visual_engine: str = "replicate") -> None:
    """AI-визуальный ряд: разбивает сценарий на сцены и рисует картинку под каждую.

    visual_engine:
      - "replicate" (по умолчанию) — модель из settings.replicate_image_model (FLUX.2 [dev])
      - "gemini" — бесплатная генерация через Gemini (Nano Banana), нужен GEMINI_API_KEY
      - конкретный slug модели Replicate (см. image_gen.IMAGE_MODEL_OPTIONS), например
        "ideogram-ai/ideogram-v3-turbo" — переопределяет модель только для этой генерации
    Не зависит от языка — один набор картинок используется для рендера на
    всех языках (отличается только аудио).
    """
    primary_script = _get_primary_script(db, video.id)
    if primary_script is None:
        raise RuntimeError("Нет основного сценария — сначала сгенерируйте его.")

    with _stage(db, video.id, "visuals") as log:
        duration_sec = video.duration_sec or primary_script.duration_estimate_sec or 0
        count = image_gen.segments_for_duration(duration_sec)
        pr = image_gen.generate_image_prompts(
            primary_script.content_md,
            count,
            niche=project.niche or "",
            style_hint=project.style_prompt or "",
        )
        _record_llm(log, pr.llm)

        # Архивируем старые картинки (не удаляем — пользователь сможет вернуться
        # к предыдущей версии). Определяем следующий номер версии.
        old_assets = (
            db.query(VideoAsset)
            .filter(VideoAsset.video_id == video.id, VideoAsset.type == "visual")
            .all()
        )
        max_ver = max(
            ((a.asset_metadata or {}).get("version", 1) for a in old_assets),
            default=0,
        )
        new_ver = max_ver + 1
        logger.debug("[visuals] архивируем {n} старых ассетов, новая версия={v} vid={vid}", n=len(old_assets), v=new_ver, vid=video.id[:8])
        for a in old_assets:
            meta = dict(a.asset_metadata or {})
            meta["archived"] = True
            a.asset_metadata = meta
        db.commit()

        # Общий seed на всё видео -> стабильнее композиция/палитра между кадрами.
        # При включённом img2img-референсе seed не фиксируем (консистентность даёт
        # опорная картинка, иначе кадры выходят почти одинаковыми).
        seed = None if settings.visual_use_reference else random.randint(1, 2_000_000_000)
        anchor: Path | None = None
        use_gemini = visual_engine == "gemini"
        # Конкретный slug модели Replicate, если передан явно (иначе — settings.replicate_image_model)
        image_model = None if use_gemini or visual_engine in ("replicate", "", None) else visual_engine
        model_used_label = "gemini" if use_gemini else (image_model or settings.replicate_image_model)

        ok_count = 0
        failed: list[str] = []
        for i, prompt in enumerate(pr.prompts):
            _check_cancel(video.id)
            if i > 0:
                # Бережём rate-limit (Replicate и Gemini оба имеют ограничения).
                time.sleep(4 if use_gemini else 11)
                _check_cancel(video.id)
            out = paths.visual_image_file(project.id, video.id, i, version=new_ver)
            try:
                if use_gemini:
                    image_gen.generate_image_gemini(prompt, out)
                else:
                    image_gen.generate_image(prompt, out, seed=seed, reference_image_path=anchor, model=image_model)
                if anchor is None and out.exists():
                    anchor = out  # первая удачная картинка — якорь стиля для остальных
                if not use_gemini and settings.visual_upscale:
                    # Апскейл — только для Replicate.
                    time.sleep(11)
                    try:
                        image_gen.upscale_image(out)
                    except image_gen.ImageGenError as e:
                        logger.warning(
                            "Апскейл картинки {i} видео {vid} не удался, оставляю исходное "
                            "разрешение: {err}", i=i, vid=video.id, err=e,
                        )
            except image_gen.ImageGenError as e:
                # Одна неудачная картинка не должна стирать уже сгенерированные
                # (коммитим по одной) — продолжаем со следующей.
                failed.append(f"#{i}: {e}")
                logger.warning(
                    "Визуальный ряд видео {vid}: картинка {i} не удалась: {err}",
                    vid=video.id, i=i, err=e,
                )
                continue
            db.add(
                VideoAsset(
                    video_id=video.id,
                    language=None,
                    type="visual",
                    file_path=str(out),
                    asset_metadata={
                        "index": i,
                        "version": new_ver,
                        "archived": False,
                        "prompt": prompt,
                        "style": pr.style,
                        "model": model_used_label,
                    },
                )
            )
            db.commit()
            ok_count += 1

        per_image = _IMAGE_COST_USD + (_UPSCALE_COST_USD if settings.visual_upscale else 0.0)
        log.cost_usd = (log.cost_usd or 0.0) + ok_count * per_image
        logger.debug("[visuals] готово {ok}/{total} картинок версии v{v} vid={vid}", ok=ok_count, total=len(pr.prompts), v=new_ver, vid=video.id[:8])
        if ok_count == 0:
            raise RuntimeError(f"Не удалось сгенерировать ни одной картинки: {'; '.join(failed)}")
        if failed:
            log.error_message = f"{ok_count}/{len(pr.prompts)} картинок готовы. Сбои: {'; '.join(failed)}"


def _stage_render(db, video: Video, project: Project, lang: str) -> None:
    with _stage(db, video.id, f"render:{lang}"):
        track = _get_audio_track(db, video.id, lang)
        if track is None or track.status != "ready" or not Path(track.file_path).exists():
            raise RuntimeError(
                f"Нет готового аудио для рендера ({lang}). Озвучьте сценарий или загрузите аудио вручную."
            )

        # Архивируем старые финальные видео, определяем следующую версию
        old_finals = (
            db.query(VideoAsset)
            .filter(VideoAsset.video_id == video.id, VideoAsset.type == "final", VideoAsset.language == lang)
            .all()
        )
        max_ver = max(((a.asset_metadata or {}).get("version", 1) for a in old_finals), default=0)
        new_ver = max_ver + 1
        for a in old_finals:
            meta = dict(a.asset_metadata or {})
            meta["archived"] = True
            a.asset_metadata = meta
        if old_finals:
            db.commit()
            logger.debug("[render] архивировано {n} финальных видео для {lang}, новая версия={v}", n=len(old_finals), lang=lang, v=new_ver)

        out = paths.final_video_file(project.id, video.id, lang, version=new_ver)
        # Если задан пользовательский плейлист — используем его (может быть больше/меньше/иной порядок)
        playlist_ids: list[str] = video.visual_playlist or []
        if playlist_ids:
            asset_map = {
                a.id: a for a in db.query(VideoAsset)
                .filter(VideoAsset.video_id == video.id, VideoAsset.type == "visual")
                .all()
            }
            visuals = [asset_map[aid] for aid in playlist_ids if aid in asset_map and Path(asset_map[aid].file_path).exists()]
            logger.debug("[render] плейлист: {n} картинок для {lang} vid={vid}", n=len(visuals), lang=lang, vid=video.id[:8])
        else:
            visuals = [a for a in _get_visual_assets(db, video.id) if Path(a.file_path).exists()]

        if visuals:
            total = track.duration_sec or len(visuals) * 30
            per_image = total / len(visuals)
            images = [(Path(a.file_path), per_image) for a in visuals]
            rp = video.render_params or {}
            # Оверлей частиц: если в параметрах видео не задан — берём настройку канала
            overlay = rp.get("overlay")
            if overlay is None:
                overlay = "embers" if project.particles_enabled else "off"
            video_builder.render_video_segments(
                images=images, audio_path=Path(track.file_path), out_path=out,
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
                check_cancel=lambda: _check_cancel(video.id),
            )
        else:
            thumb_path = paths.thumbnail_file(project.id, video.id)
            if not thumb_path.exists():
                _stage_thumbnail(db, video, project)
            video_builder.render_video(
                image_path=thumb_path, audio_path=Path(track.file_path), out_path=out
            )
        # Микшируем фоновую музыку если задана
        if video.music_track_id:
            from app.models.music_track import MusicTrack
            music = db.get(MusicTrack, video.music_track_id)
            if music and music.status == "ready" and music.file_path and Path(music.file_path).exists():
                music_out = out.with_stem(out.stem + "_music")
                try:
                    video_builder.mix_background_music(
                        out, Path(music.file_path), music_out,
                        volume=video.music_volume or 0.15,
                    )
                    music_out.replace(out)
                    logger.info("[render] музыка подмикширована для {lang}", lang=lang)
                except Exception as e:
                    logger.warning("[render] не удалось подмикшировать музыку: {e}", e=e)

        db.add(VideoAsset(
            video_id=video.id,
            language=lang,
            type="final",
            file_path=str(out),
            asset_metadata={"version": new_ver, "archived": False, "lang": lang},
        ))
        db.commit()


def _update_duration_from_primary(db, video: Video, project: Project) -> None:
    primary = _get_primary_script(db, video.id)
    track = _get_audio_track(db, video.id, project.language_primary) if primary else None
    if track and track.duration_sec:
        video.duration_sec = track.duration_sec
    elif primary:
        video.duration_sec = primary.duration_estimate_sec
    db.commit()


# ---------------------------------------------------------------------------
# Полный пайплайн (запуск нового видео)
# ---------------------------------------------------------------------------


# Глобальная очередь полных пайплайнов: не больше одного одновременно.
# При пакетном создании видео фоновые задачи FastAPI стартуют параллельно —
# без замка они бы одновременно долбили LLM/Replicate и ловили rate-limit'ы.
_PIPELINE_QUEUE = threading.BoundedSemaphore(1)


def run_pipeline(video_id: str, options: PipelineOptions) -> None:
    """Запускает полный пайплайн для видео. Вызывать в фоне.

    Пайплайны выполняются по одному (глобальная очередь) — второй и последующие
    ждут завершения предыдущего, оставаясь в статусе "draft".

    Критична только генерация сценария — если она упала, видео помечается
    status="error" (больше ничего полезного нет). Все стадии после неё —
    блоки: ошибка одного блока (например, TTS одного языка) логируется и
    публикуется по WS, но не прерывает остальные блоки и не валит весь
    пайплайн.
    """
    with _PIPELINE_QUEUE:
        _run_pipeline_locked(video_id, options)


def _run_pipeline_locked(video_id: str, options: PipelineOptions) -> None:
    db = SessionLocal()
    try:
        video = db.get(Video, video_id)
        if video is None:
            logger.error("Pipeline: видео {vid} не найдено", vid=video_id)
            return
        project = db.get(Project, video.project_id)
        if project is None:
            logger.error("Pipeline: проект для видео {vid} не найден", vid=video_id)
            return

        video.status = "generating"
        db.commit()
        _publish(video_id, type="pipeline_start")

        primary_lang = project.language_primary
        languages = options.languages or [primary_lang]
        if primary_lang not in languages:
            languages = [primary_lang, *languages]

        # [1] GENERATE_SCRIPT — критичная стадия, ошибка здесь валит весь пайплайн
        # (если передан script_content — Claude не вызывается, текст сохраняется как есть)
        primary_script = _stage_script(
            db, video, project, options.target_duration_min,
            manual_content=options.script_content,
            preset_prompts=options.script_prompts,
        )

        # [2] ANALYZE_SCRIPT -> память (не критично: сценарий уже сохранён)
        try:
            _stage_analysis(db, video, project, primary_script)
        except Exception as e:  # noqa: BLE001
            logger.warning("Анализ сценария видео {vid} не удался: {err}", vid=video_id, err=e)

        # [3] TRANSLATE (остальные языки) — каждый язык независим
        other_langs = [l for l in languages if l != primary_lang]
        if options.run_translate:
            for lang in other_langs:
                try:
                    _stage_translate(db, video, project, primary_script, lang)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "Перевод на {lang} для видео {vid} не удался: {err}", lang=lang, vid=video_id, err=e
                    )

        # [4] TTS (по языкам) — каждый язык независим
        if options.run_tts:
            langs_for_tts = languages if (options.run_translate or len(languages) == 1) else [primary_lang]
            for lang in langs_for_tts:
                if _get_script(db, video_id, lang) is None:
                    continue
                try:
                    _stage_tts(db, video, project, lang)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "Озвучка {lang} для видео {vid} не удалась: {err}", lang=lang, vid=video_id, err=e
                    )

        # [4.5] VISUALS — AI-визуальный ряд (опционально, платно через Replicate)
        if options.run_visuals:
            try:
                _stage_visuals(db, video, project)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Визуальный ряд для видео {vid} не удался: {err}", vid=video_id, err=e
                )

        # [5] THUMBNAIL + [6] RENDER — рендерим только то, для чего уже есть готовое аудио
        if options.run_render:
            try:
                _stage_thumbnail(db, video, project)
            except Exception as e:  # noqa: BLE001
                logger.warning("Обложка для видео {vid} не удалась: {err}", vid=video_id, err=e)

            for lang in languages:
                track = _get_audio_track(db, video_id, lang)
                if track is None or track.status != "ready" or not Path(track.file_path).exists():
                    continue  # нет аудио на этот язык — рендер просто пропускается, это не ошибка
                try:
                    _stage_render(db, video, project, lang)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "Рендер {lang} для видео {vid} не удался: {err}", lang=lang, vid=video_id, err=e
                    )

        # [7] UPDATE_STATS — достигаем сюда, если хотя бы сценарий сгенерирован
        with _stage(db, video_id, "stats"):
            _update_duration_from_primary(db, video, project)
            video.status = "ready"
            db.commit()

        _publish(video_id, type="pipeline_done", status="ready")
        logger.info("Пайплайн видео {vid} завершён", vid=video_id)

    except Exception as e:  # noqa: BLE001
        # Сюда долетает только ошибка критичной стадии "script" (или совсем
        # неожиданный сбой) — без сценария показывать пользователю нечего.
        logger.exception("Пайплайн видео {vid} упал: {err}", vid=video_id, err=e)
        v = db.get(Video, video_id)
        if v:
            v.status = "error"
            db.commit()
        _publish(video_id, type="pipeline_error", error=str(e))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Точечный перезапуск одной стадии (ручное доведение после сбоя)
# ---------------------------------------------------------------------------

VALID_STAGES = {"analysis", "translate", "tts", "thumbnail", "visuals", "render"}


def run_pipeline_stage(video_id: str, stage: str, lang: str | None = None, visual_engine: str = "replicate") -> None:  # noqa: C901
    """Перезапускает ровно одну стадию для уже существующего видео.

    Используется, когда автоматический пайплайн что-то не смог (например,
    TTS без установленного Kokoro) и пользователь донастроил/доделал руками
    (например, загрузил аудио или сменил tts_mode), а теперь хочет
    перезапустить именно эту стадию, не трогая остальной результат.
    """
    logger.debug("[stage_retry] START stage={stage} lang={lang} vid={vid}", stage=stage, lang=lang, vid=video_id[:8])
    db = SessionLocal()
    try:
        video = db.get(Video, video_id)
        if video is None:
            return
        project = db.get(Project, video.project_id)
        if project is None:
            return
        primary_script = _get_primary_script(db, video_id)

        try:
            if stage == "analysis":
                if primary_script is None:
                    raise RuntimeError("Нет основного сценария — сначала сгенерируйте его.")
                _stage_analysis(db, video, project, primary_script)
            elif stage == "translate":
                if not lang:
                    raise RuntimeError("Не указан язык перевода.")
                if primary_script is None:
                    raise RuntimeError("Нет основного сценария — сначала сгенерируйте его.")
                _stage_translate(db, video, project, primary_script, lang)
            elif stage == "tts":
                if not lang:
                    raise RuntimeError("Не указан язык озвучки.")
                _stage_tts(db, video, project, lang)
            elif stage == "thumbnail":
                _stage_thumbnail(db, video, project)
            elif stage == "visuals":
                _stage_visuals(db, video, project, visual_engine=visual_engine)
            elif stage == "render":
                if not lang:
                    raise RuntimeError("Не указан язык рендера.")
                _stage_render(db, video, project, lang)
            else:
                raise RuntimeError(f"Неизвестная стадия: {stage}")
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Повтор стадии {stage} ({lang}) для видео {vid} не удался: {err}",
                stage=stage, lang=lang, vid=video_id, err=e,
            )

        if video.status == "ready":
            _update_duration_from_primary(db, video, project)
        _publish(video_id, type="stage_retry_done", stage=stage, lang=lang)
    finally:
        db.close()
