"""SQLAlchemy engine, сессии и базовый класс моделей."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


# Гарантируем, что директория под БД существует
settings.db_file.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.db_file}",
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: выдаёт сессию и закрывает её после запроса."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Создаёт все таблицы (для разработки без Alembic) и сидирует справочники."""
    # Импорт моделей нужен, чтобы они зарегистрировались в metadata
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _seed_builtin_voices()


# Лёгкая ad-hoc миграция для SQLite: create_all не добавляет новые колонки в
# уже существующие таблицы (Alembic в проекте установлен, но пока не
# используется для dev — см. CLAUDE.md §14). Чтобы не терять данные
# пользователя при добавлении новых полей в модели, добавляем недостающие
# колонки явным ALTER TABLE.
_NEW_COLUMNS: list[tuple[str, str, str]] = [
    # (таблица, колонка, SQL-тип с DEFAULT)
    ("videos", "voice_overrides", "JSON DEFAULT '{}'"),
    ("videos", "script_prompts", "JSON DEFAULT '{}'"),
    ("videos", "render_params", "JSON DEFAULT '{}'"),
    ("projects", "particles_enabled", "BOOLEAN DEFAULT 0"),
    ("audio_tracks", "version", "INTEGER DEFAULT 1"),
    ("audio_tracks", "archived", "BOOLEAN DEFAULT 0"),
    ("script_analysis", "title_suggestions", "JSON DEFAULT '[]'"),
    ("script_analysis", "youtube_tags", "JSON DEFAULT '[]'"),
    ("videos", "visual_playlist", "JSON DEFAULT '[]'"),
    ("projects", "intro_enabled", "BOOLEAN DEFAULT 0"),
    ("projects", "intro_template", "TEXT DEFAULT 'Добро пожаловать на канал {channel}. Сегодня мы поговорим о: {topic}.'"),
    ("videos", "music_track_id", "TEXT DEFAULT NULL"),
    ("videos", "music_volume", "REAL DEFAULT 0.15"),
    ("projects", "default_music_track_id", "TEXT DEFAULT NULL"),
    ("projects", "default_music_volume", "REAL DEFAULT 0.15"),
]


def _ensure_columns() -> None:
    with engine.connect() as conn:
        for table, column, col_type in _NEW_COLUMNS:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                conn.commit()


# Встроенные голоса Kokoro по языкам — те же ID, что были дефолтными в
# tts_service до появления библиотеки голосов. Помечены is_builtin=True,
# чтобы их нельзя было удалить (но можно добавить свои рядом).
_BUILTIN_VOICES = [
    # Edge TTS — нативные голоса, бесплатно, без GPU. Лучший выбор для русского.
    ("Edge RU — Дмитрий (м)", "ru", "edge", "ru-RU-DmitryNeural", "Нативный русский мужской голос (Microsoft Edge TTS)"),
    ("Edge RU — Светлана (ж)", "ru", "edge", "ru-RU-SvetlanaNeural", "Нативный русский женский голос (Microsoft Edge TTS)"),
    ("Edge EN — Brian (м, спокойный)", "en", "edge", "en-US-BrianNeural", "Тёплый спокойный мужской голос — хорошо для «History for Sleep»"),
    ("Edge EN — Aria (ж)", "en", "edge", "en-US-AriaNeural", "Женский английский голос (Microsoft Edge TTS)"),
    ("Edge EN — Guy (м)", "en", "edge", "en-US-GuyNeural", "Мужской английский голос (Microsoft Edge TTS)"),
    ("Edge ES — Álvaro (м)", "es", "edge", "es-ES-AlvaroNeural", "Испанский мужской голос (Microsoft Edge TTS)"),
    ("Edge FR — Henri (м)", "fr", "edge", "fr-FR-HenriNeural", "Французский мужской голос (Microsoft Edge TTS)"),
    ("Edge DE — Conrad (м)", "de", "edge", "de-DE-ConradNeural", "Немецкий мужской голос (Microsoft Edge TTS)"),
    # Kokoro — локальный синтез (GPU/CPU). Нет нативного русского.
    ("Kokoro EN — Heart (ж)", "en", "kokoro", "af_heart", "Стандартный женский голос Kokoro для английского"),
    ("Kokoro ES — Dora (ж)", "es", "kokoro", "ef_dora", "Стандартный голос Kokoro для испанского"),
    ("Kokoro FR — Siwis (ж)", "fr", "kokoro", "ff_siwis", "Стандартный голос Kokoro для французского"),
    ("Kokoro IT — Sara (ж)", "it", "kokoro", "if_sara", "Стандартный голос Kokoro для итальянского"),
    ("Kokoro PT — Dora (ж)", "pt", "kokoro", "pf_dora", "Стандартный голос Kokoro для португальского"),
    ("Kokoro JA — Alpha (ж)", "ja", "kokoro", "jf_alpha", "Стандартный голос Kokoro для японского"),
    ("Kokoro ZH — Xiaobei (ж)", "zh", "kokoro", "zf_xiaobei", "Стандартный голос Kokoro для китайского"),
    ("Kokoro HI — Alpha (ж)", "hi", "kokoro", "hf_alpha", "Стандартный голос Kokoro для хинди"),
]


def _seed_builtin_voices() -> None:
    from app.models.voice import Voice

    db = SessionLocal()
    try:
        existing = {(v.language, v.voice_id) for v in db.query(Voice).filter(Voice.is_builtin == True)}  # noqa: E712
        for name, lang, engine, voice_id, desc in _BUILTIN_VOICES:
            if (lang, voice_id) in existing:
                continue
            db.add(Voice(name=name, language=lang, engine=engine, voice_id=voice_id, description=desc, is_builtin=True))
        db.commit()
    finally:
        db.close()
