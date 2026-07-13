"""CRUD библиотеки голосов (общая для всех каналов)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import paths
from app.core.database import get_db
from app.models.voice import Voice
from app.schemas.voice import VoiceCreate, VoiceOut, VoiceUpdate
from app.services import app_settings, tts_service
from app.services.tts_service import TTSError

router = APIRouter(prefix="/api/voices", tags=["voices"])


@router.get("", response_model=list[VoiceOut])
def list_voices(language: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Voice)
    if language:
        q = q.filter(Voice.language == language)
    return q.order_by(Voice.language, Voice.name).all()


@router.post("", response_model=VoiceOut, status_code=201)
def create_voice(payload: VoiceCreate, db: Session = Depends(get_db)):
    voice = Voice(**payload.model_dump())
    db.add(voice)
    db.commit()
    db.refresh(voice)
    return voice


@router.patch("/{voice_id}", response_model=VoiceOut)
def update_voice(voice_id: str, payload: VoiceUpdate, db: Session = Depends(get_db)):
    voice = db.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(404, "Голос не найден")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(voice, k, v)
    db.commit()
    db.refresh(voice)
    return voice


@router.delete("/{voice_id}", status_code=204)
def delete_voice(voice_id: str, db: Session = Depends(get_db)):
    voice = db.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(404, "Голос не найден")
    if voice.is_builtin:
        raise HTTPException(400, "Встроенный голос нельзя удалить")
    db.delete(voice)
    db.commit()


@router.post("/{voice_id}/preview", status_code=201)
def generate_preview(voice_id: str, db: Session = Depends(get_db)):
    """Генерирует короткий демо-сэмпл голоса, чтобы его можно было прослушать.

    Доступно для синтезируемых движков (kokoro/edge). У "manual" нет движка
    синтеза, его нечем озвучить заранее. Применяются глобальные параметры
    голоса, чтобы демо звучало так же, как финальная озвучка.
    """
    voice = db.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(404, "Голос не найден")
    if voice.engine == "manual":
        raise HTTPException(400, "Ручной голос нечем прослушать — озвучка загружается вручную")
    out_path = paths.voice_preview_file(voice.id)
    try:
        tts_service.synthesize_preview(
            voice.language, voice.voice_id, out_path, app_settings.get_voice_params()
        )
    except TTSError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "ok", "url": f"/files/voices/{voice.id}.wav"}
