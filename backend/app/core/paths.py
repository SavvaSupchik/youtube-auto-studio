"""Управление файловой структурой проектов на диске.

Структура:
    data/projects/<project_id>/
        config.json
        memory.jsonl
        videos/<video_id>/
            script_<lang>.md
            analysis.json
            audio/<lang>.wav
            assets/
            thumbnail.png
            final_<lang>.mp4
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings


def projects_root() -> Path:
    p = settings.data_path / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_dir(project_id: str) -> Path:
    p = projects_root() / project_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_config_file(project_id: str) -> Path:
    return project_dir(project_id) / "config.json"


def project_memory_file(project_id: str) -> Path:
    return project_dir(project_id) / "memory.jsonl"


def videos_dir(project_id: str) -> Path:
    p = project_dir(project_id) / "videos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def video_dir(project_id: str, video_id: str) -> Path:
    p = videos_dir(project_id) / video_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def script_file(project_id: str, video_id: str, lang: str) -> Path:
    return video_dir(project_id, video_id) / f"script_{lang}.md"


def analysis_file(project_id: str, video_id: str) -> Path:
    return video_dir(project_id, video_id) / "analysis.json"


def audio_dir(project_id: str, video_id: str) -> Path:
    p = video_dir(project_id, video_id) / "audio"
    p.mkdir(parents=True, exist_ok=True)
    return p


def audio_file(project_id: str, video_id: str, lang: str, version: int = 1) -> Path:
    """version=1 → lang.wav (обратная совместимость), version≥2 → lang_v{N}.wav."""
    d = audio_dir(project_id, video_id)
    return d / (f"{lang}.wav" if version <= 1 else f"{lang}_v{version}.wav")


def assets_dir(project_id: str, video_id: str) -> Path:
    p = video_dir(project_id, video_id) / "assets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def visual_image_file(project_id: str, video_id: str, index: int, version: int = 1) -> Path:
    """Картинка визуального ряда (AI-генерация по контексту сценария).

    version=1 — обратная совместимость: файлы в корне assets/.
    version>=2 — подпапка visuals/v{N}/ чтобы не затирать предыдущие версии.
    """
    if version <= 1:
        return assets_dir(project_id, video_id) / f"visual_{index:03d}.png"
    base = assets_dir(project_id, video_id) / "visuals" / f"v{version}"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"visual_{index:03d}.png"


def thumbnail_file(project_id: str, video_id: str, lang: str | None = None) -> Path:
    name = "thumbnail.png" if lang is None else f"thumbnail_{lang}.png"
    return video_dir(project_id, video_id) / name


def intro_audio_file(project_id: str, video_id: str, lang: str) -> Path:
    return audio_dir(project_id, video_id) / f"intro_{lang}.wav"


def audio_with_intro_file(project_id: str, video_id: str, lang: str, version: int = 1) -> Path:
    """Склеенный файл интро+основное аудио, используется в рендере."""
    d = audio_dir(project_id, video_id)
    return d / (f"{lang}_with_intro.wav" if version <= 1 else f"{lang}_v{version}_with_intro.wav")


def final_video_file(project_id: str, video_id: str, lang: str, version: int = 1) -> Path:
    """version=1 → final_lang.mp4 (обратная совместимость), version≥2 → final_lang_v{N}.mp4."""
    d = video_dir(project_id, video_id)
    return d / (f"final_{lang}.mp4" if version <= 1 else f"final_{lang}_v{version}.mp4")


def pipeline_dir(project_id: str, video_id: str) -> Path:
    """Папка с промежуточными артефактами 3-шаговой генерации (бриф, черновик)."""
    p = video_dir(project_id, video_id) / "pipeline"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pipeline_step_file(project_id: str, video_id: str, name: str) -> Path:
    """Файл результата шага цепочки: prep.md / draft.md (для просмотра/доделки руками)."""
    return pipeline_dir(project_id, video_id) / f"{name}.md"


def app_settings_file() -> Path:
    """Глобальные настройки приложения, редактируемые в рантайме (не из .env)."""
    return settings.data_path / "settings.json"


def templates_dir() -> Path:
    """Папка с пользовательскими (отредактированными) шаблонами сценария.

    Лежит в DATA_DIR, чтобы правки пользователя не смешивались с дефолтами в
    репозитории и переживали обновления кода. Если файла здесь нет —
    используется дефолт из app/prompts/chain/.
    """
    p = settings.data_path / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def template_override_file(name: str) -> Path:
    return templates_dir() / f"{name}.txt"


def voices_dir() -> Path:
    p = settings.data_path / "voices"
    p.mkdir(parents=True, exist_ok=True)
    return p


def voice_preview_file(voice_id: str) -> Path:
    """Файл короткого демо-сэмпла голоса (для прослушивания в библиотеке голосов)."""
    return voices_dir() / f"{voice_id}.wav"
