"""Клиент для Suno API (неофициальный self-hosted: https://github.com/gcui-art/suno-api).

Настройка:
  SUNO_API_URL=http://localhost:3000   # базовый URL вашего инстанса suno-api
  SUNO_COOKIE=...                      # cookie из браузера (если требует suno-api)

Если SUNO_API_URL не задан — генерация недоступна, вернётся ошибка.
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx
from loguru import logger

from app.core.config import settings


class SunoError(RuntimeError):
    pass


def _base_url() -> str:
    url = getattr(settings, "suno_api_url", "")
    if not url:
        raise SunoError(
            "SUNO_API_URL не задан в .env. "
            "Разверните https://github.com/gcui-art/suno-api и укажите его адрес."
        )
    return url.rstrip("/")


def generate(
    prompt: str,
    *,
    tags: str = "",
    title: str = "",
    instrumental: bool = True,
    wait: bool = True,
    timeout: int = 300,
) -> list[dict]:
    """Запускает генерацию трека на Suno и возвращает список готовых треков.

    Каждый трек — словарь с полями: id, title, audio_url, duration.
    Если wait=False — возвращает задачу немедленно (статус pending).
    """
    base = _base_url()
    payload = {
        "prompt": prompt,
        "tags": tags,
        "title": title or prompt[:80],
        "make_instrumental": instrumental,
        "wait_audio": False,
    }
    logger.info("[suno] Генерация: prompt={p!r}", p=prompt[:80])
    try:
        resp = httpx.post(f"{base}/api/custom_generate", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise SunoError(f"Suno API ошибка: {e}") from e

    if not data:
        raise SunoError("Suno API вернул пустой ответ")

    ids = [item["id"] for item in data if "id" in item]
    if not wait:
        return data

    # Ждём готовности
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        try:
            result = httpx.get(f"{base}/api/get", params={"ids": ",".join(ids)}, timeout=15)
            result.raise_for_status()
            tracks = result.json()
        except httpx.HTTPError as e:
            logger.warning("[suno] Ошибка при проверке статуса: {e}", e=e)
            continue

        done = [t for t in tracks if t.get("status") in ("complete", "streaming")]
        if len(done) >= len(ids):
            logger.info("[suno] Готово: {n} треков", n=len(done))
            return done

    raise SunoError(f"Suno не завершил генерацию за {timeout}с")


def download_track(audio_url: str, out_path: Path) -> None:
    """Скачивает аудио по URL и сохраняет в out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("[suno] Скачиваем {url} -> {p}", url=audio_url[:80], p=out_path)
    with httpx.stream("GET", audio_url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_bytes(8192):
                f.write(chunk)
