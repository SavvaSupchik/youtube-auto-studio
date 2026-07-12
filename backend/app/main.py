"""FastAPI entry point для YouTube Auto Studio."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api import app_settings, generation, music, niche, projects, stats, templates, videos, voices
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.core.jobs import broker
from app.models.video import Video


def _reset_stuck_videos() -> None:
    """При старте сбрасываем видео, застрявшие в статусе 'generating'.

    BackgroundTask умирает вместе с процессом uvicorn — без этого видео
    зависает в 'generating' навсегда и кнопка 'Перегенерировать' не работает.
    """
    db = SessionLocal()
    try:
        stuck = db.query(Video).filter(Video.status == "generating").all()
        if stuck:
            for v in stuck:
                v.status = "error"
            db.commit()
            logger.warning(
                "Сброшено {n} видео из статуса 'generating' в 'error' (незавершённые задачи предыдущего сеанса)",
                n=len(stuck),
            )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _reset_stuck_videos()
    broker.bind_loop(asyncio.get_running_loop())
    settings.data_path.mkdir(parents=True, exist_ok=True)

    # Файловый DEBUG-лог — пишем только после того, как data_path гарантированно существует.
    # Читать: data/debug.log  (ротация 10 MB, хранить 7 дней)
    log_file = settings.data_path / "debug.log"
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True)
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        format="{time:HH:mm:ss.SSS} | {level:<7} | {name}:{line} | {message}",
    )

    logger.info(
        "YouTube Auto Studio backend запущен. Провайдер LLM: {provider}, настроен: {ok}",
        provider=settings.llm_provider, ok=settings.llm_configured,
    )
    yield


app = FastAPI(title="YouTube Auto Studio", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(videos.router)
app.include_router(generation.router)
app.include_router(stats.router)
app.include_router(app_settings.router)
app.include_router(templates.router)
app.include_router(voices.router)
app.include_router(music.router)
app.include_router(niche.router)

# Раздача сгенерированных файлов (аудио, видео, обложки)
(settings.data_path / "projects").mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/projects",
    StaticFiles(directory=str(settings.data_path / "projects")),
    name="files",
)

# Демо-сэмплы голосов (для прослушивания в библиотеке голосов)
(settings.data_path / "voices").mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/voices",
    StaticFiles(directory=str(settings.data_path / "voices")),
    name="voice_files",
)

# Музыкальная библиотека
(settings.data_path / "music").mkdir(parents=True, exist_ok=True)
app.mount(
    "/files/music",
    StaticFiles(directory=str(settings.data_path / "music")),
    name="music_files",
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_configured": settings.llm_configured,
    }
