"""Озвучка сценариев.

Два режима:
- "local"  — Kokoro TTS локально (бесплатно, GPU/CPU). Тяжёлые зависимости
             импортируются лениво, чтобы приложение поднималось без них.
- "manual" — ручной режим: файл не генерируется, ожидается, что пользователь
             загрузит готовую озвучку. Возвращаем понятный статус.
"""
from __future__ import annotations

import re
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.core.config import settings


class TTSError(RuntimeError):
    """Ошибка озвучки (нет движка/модели/голоса)."""


@dataclass
class TTSResult:
    file_path: str
    duration_sec: int
    voice_id: str
    engine: str
    status: str  # ready / pending_manual / failed


# Маппинг языка на дефолтный голос Kokoro, если в проекте не задан свой.
_DEFAULT_VOICES = {
    "en": "af_heart",
    "es": "ef_dora",
    "fr": "ff_siwis",
    "it": "if_sara",
    "pt": "pf_dora",
    "ja": "jf_alpha",
    "zh": "zf_xiaobei",
    "hi": "hf_alpha",
    "ru": "af_heart",  # workaround: русский через английский голос
}


def _wav_duration(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return int(frames / rate) if rate else 0
    except Exception:  # noqa: BLE001
        return 0


def probe_duration_sec(path: Path) -> int:
    """Определяет длительность аудиофайла любого формата через FFmpeg.

    Используется при ручной загрузке готовой озвучки (произвольный формат,
    не обязательно wav) — для wav сначала пробуем быстрый путь без ffmpeg.
    """
    if path.suffix.lower() == ".wav":
        dur = _wav_duration(path)
        if dur:
            return dur
    try:
        proc = subprocess.run(
            [settings.ffmpeg_path, "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr)
        if m:
            h, mnt, s = m.groups()
            return int(int(h) * 3600 + int(mnt) * 60 + float(s))
    except Exception:  # noqa: BLE001
        pass
    return 0


def _synthesize_kokoro(text: str, voice: str, out_path: Path) -> int:
    """Синтез через Kokoro. Возвращает длительность в секундах.

    Зависимости (kokoro, soundfile, torch) импортируются здесь лениво.
    """
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError as e:  # pragma: no cover
        raise TTSError(
            "Kokoro TTS не установлен. Установите: pip install kokoro soundfile, "
            "или переключите канал в режим tts_mode='manual'."
        ) from e

    lang_code = voice[0] if voice else "a"
    pipeline = KPipeline(lang_code=lang_code)
    audio_chunks = []
    for _, _, audio in pipeline(text, voice=voice):
        audio_chunks.append(audio)
    if not audio_chunks:
        raise TTSError("Kokoro вернул пустой результат озвучки.")
    full = np.concatenate(audio_chunks)
    sf.write(str(out_path), full, 24000)
    return _wav_duration(out_path)


_PREVIEW_TEXT = {
    "ru": "Привет! Это пример голоса для предпрослушивания.",
    "en": "Hello! This is a short voice preview sample.",
    "es": "¡Hola! Esta es una breve muestra de voz.",
    "fr": "Bonjour ! Voici un court échantillon de cette voix.",
    "de": "Hallo! Dies ist eine kurze Sprachprobe.",
    "it": "Ciao! Questo è un breve campione di questa voce.",
    "pt": "Olá! Esta é uma breve amostra desta voz.",
    "ja": "こんにちは。これは音声のサンプルです。",
    "zh": "你好，这是一个语音示例。",
    "hi": "नमस्ते! यह आवाज़ का एक छोटा नमूना है।",
}


def synthesize_preview(language: str, voice_id: str, out_path: Path) -> int:
    """Генерирует короткий тестовый сэмпл для прослушивания голоса (только Kokoro)."""
    text = _PREVIEW_TEXT.get(language, _PREVIEW_TEXT["en"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return _synthesize_kokoro(text, voice_id, out_path)


def synthesize(
    *,
    text: str,
    language: str,
    out_path: Path,
    tts_mode: str,
    voice_settings: dict[str, str],
) -> TTSResult:
    """Озвучивает текст в файл out_path согласно режиму канала."""
    voice = voice_settings.get(language) or _DEFAULT_VOICES.get(language, "af_heart")

    if tts_mode == "manual":
        logger.info("TTS manual режим: ожидается ручная загрузка озвучки для {lang}", lang=language)
        return TTSResult(
            file_path=str(out_path),
            duration_sec=0,
            voice_id="manual",
            engine="manual",
            status="pending_manual",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Kokoro озвучка {lang} голосом {voice} (device={dev})",
                lang=language, voice=voice, dev=settings.kokoro_device)
    duration = _synthesize_kokoro(text, voice, out_path)
    return TTSResult(
        file_path=str(out_path),
        duration_sec=duration,
        voice_id=voice,
        engine="kokoro",
        status="ready",
    )
