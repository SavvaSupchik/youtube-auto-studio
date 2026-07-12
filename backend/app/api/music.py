"""API музыкальной библиотеки + генерация через Suno."""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.music_track import MusicTrack

router = APIRouter(prefix="/api/music", tags=["music"])


def _music_dir() -> Path:
    p = settings.data_path / "music"
    p.mkdir(parents=True, exist_ok=True)
    return p


class MusicOut(BaseModel):
    id: str
    title: str
    source: str
    tags: str
    file_path: str
    duration_sec: int | None
    status: str
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_safe(cls, t: MusicTrack) -> "MusicOut":
        return cls(
            id=t.id,
            title=t.title,
            source=t.source,
            tags=t.tags,
            file_path=t.file_path,
            duration_sec=t.duration_sec,
            status=t.status,
            created_at=t.created_at.isoformat(),
        )


class SunoGenerateRequest(BaseModel):
    prompt: str
    tags: str = ""
    title: str = ""
    instrumental: bool = True


def _get_audio_duration(path: Path) -> int | None:
    try:
        import wave
        with wave.open(str(path), "rb") as wf:
            return int(wf.getnframes() / wf.getframerate())
    except Exception:
        pass
    try:
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        import json
        d = json.loads(r.stdout)
        return int(float(d["format"]["duration"]))
    except Exception:
        return None


def _suno_background(track_id: str) -> None:
    """Фоновая задача: генерирует трек Suno и обновляет запись в БД."""
    from app.core.database import SessionLocal
    from app.services import suno_service

    db = SessionLocal()
    try:
        track = db.get(MusicTrack, track_id)
        if not track:
            return
        tracks = suno_service.generate(
            track.tags or track.title,
            tags=track.tags,
            title=track.title,
            instrumental=True,
            wait=True,
        )
        if not tracks:
            track.status = "error"
            db.commit()
            return

        first = tracks[0]
        audio_url = first.get("audio_url") or first.get("stream_audio_url", "")
        if not audio_url:
            track.status = "error"
            db.commit()
            return

        out_path = _music_dir() / f"{track_id}.mp3"
        suno_service.download_track(audio_url, out_path)

        track.file_path = str(out_path)
        track.duration_sec = first.get("duration") or _get_audio_duration(out_path)
        track.status = "ready"
        if not track.title and first.get("title"):
            track.title = first["title"]
        db.commit()
        logger.info("[music] Suno трек готов: {id}", id=track_id[:8])
    except Exception as e:
        logger.error("[music] Suno ошибка для {id}: {e}", id=track_id[:8], e=e)
        db2 = SessionLocal()
        try:
            t = db2.get(MusicTrack, track_id)
            if t:
                t.status = "error"
                db2.commit()
        finally:
            db2.close()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[MusicOut])
def list_tracks(db: Session = Depends(get_db)):
    tracks = db.query(MusicTrack).order_by(MusicTrack.created_at.desc()).all()
    return [MusicOut.from_orm_safe(t) for t in tracks]


@router.post("/generate", response_model=MusicOut, status_code=202)
def generate_suno(req: SunoGenerateRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """Запускает генерацию трека через Suno API (фоново)."""
    suno_url = getattr(settings, "suno_api_url", "")
    if not suno_url:
        raise HTTPException(
            422,
            "SUNO_API_URL не задан в .env. "
            "Разверните https://github.com/gcui-art/suno-api и укажите его адрес.",
        )
    track = MusicTrack(
        title=req.title or req.prompt[:80],
        source="suno",
        tags=req.tags,
        status="pending",
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    bg.add_task(_suno_background, track.id)
    return MusicOut.from_orm_safe(track)


class BrowseResult(BaseModel):
    path: str | None


@router.get("/browse", response_model=BrowseResult)
def browse_file():
    """Открывает системный диалог выбора файла на сервере и возвращает путь."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Выберите аудиофайл",
            filetypes=[("Аудио", "*.mp3 *.wav *.ogg *.flac *.m4a *.aac"), ("Все файлы", "*.*")],
        )
        root.destroy()
        return BrowseResult(path=path or None)
    except Exception as e:
        raise HTTPException(500, f"Не удалось открыть диалог: {e}") from e


class UploadByPathRequest(BaseModel):
    file_path: str  # абсолютный путь на локальной машине


@router.post("/upload", response_model=MusicOut)
def upload_track(req: UploadByPathRequest, db: Session = Depends(get_db)):
    """Копирует аудиофайл с локального диска в библиотеку."""
    src = Path(req.file_path)
    if not src.exists():
        raise HTTPException(404, f"Файл не найден: {src}")
    if not src.is_file():
        raise HTTPException(400, "Указанный путь не является файлом")

    suffix = src.suffix or ".mp3"
    track = MusicTrack(
        title=src.stem,
        source="upload",
        status="ready",
    )
    db.add(track)
    db.commit()
    db.refresh(track)

    out_path = _music_dir() / f"{track.id}{suffix}"
    shutil.copy2(str(src), str(out_path))

    track.file_path = str(out_path)
    track.duration_sec = _get_audio_duration(out_path)
    db.commit()
    return MusicOut.from_orm_safe(track)


@router.delete("/{track_id}", status_code=204)
def delete_track(track_id: str, db: Session = Depends(get_db)):
    track = db.get(MusicTrack, track_id)
    if not track:
        raise HTTPException(404, "Трек не найден")
    if track.file_path:
        Path(track.file_path).unlink(missing_ok=True)
    db.delete(track)
    db.commit()


@router.get("/{track_id}", response_model=MusicOut)
def get_track(track_id: str, db: Session = Depends(get_db)):
    track = db.get(MusicTrack, track_id)
    if not track:
        raise HTTPException(404, "Трек не найден")
    return MusicOut.from_orm_safe(track)
