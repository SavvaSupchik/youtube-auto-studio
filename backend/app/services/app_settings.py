"""Глобальные настройки приложения, редактируемые в рантайме (через UI).

В отличие от .env (ключи API, пути — задаются при установке), эти настройки
пользователь меняет на странице «Настройки». Хранятся в DATA_DIR/settings.json.

Сейчас:
- default_voices: {язык: voice_id} — голоса озвучки по умолчанию. Имеют самый
  низкий приоритет: берутся, когда голос не задан ни у видео (voice_overrides),
  ни у канала (voice_settings).
"""
from __future__ import annotations

import json

from loguru import logger

from app.core import paths

_DEFAULTS: dict = {"default_voices": {}}


def load() -> dict:
    """Текущие настройки (с дефолтами для отсутствующих ключей)."""
    f = paths.app_settings_file()
    if not f.exists():
        return {**_DEFAULTS}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("Не удалось прочитать settings.json: {err}", err=e)
        return {**_DEFAULTS}
    return {**_DEFAULTS, **data}


def save(patch: dict) -> dict:
    """Частично обновляет настройки и пишет на диск. Возвращает полный набор."""
    current = load()
    current.update(patch)
    paths.app_settings_file().write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return current


def get_default_voices() -> dict[str, str]:
    return load().get("default_voices") or {}
