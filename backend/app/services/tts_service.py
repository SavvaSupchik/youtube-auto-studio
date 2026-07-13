"""Озвучка сценариев.

Движки (определяются по voice_id голоса):
- "kokoro" — Kokoro TTS локально (бесплатно, GPU/CPU). Нет нативного русского.
- "edge"   — Microsoft Edge TTS (бесплатно, без GPU, отличные русские голоса
             ru-RU-Dmitry/Svetlana; поддерживает темп/высоту тона). voice_id
             в формате "ru-RU-DmitryNeural".
- "manual" — файл не генерируется, ожидается ручная загрузка готовой озвучки.

«Живость» голоса управляется глобальными параметрами (voice_params из настроек
приложения): темп речи, высота тона, паузы между предложениями/абзацами и
лёгкая пост-обработка (компрессия + тёплый EQ + мягкая реверберация). Тяжёлые
зависимости (kokoro/torch, edge_tts, soundfile) импортируются лениво.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.core.config import settings

# Частота дискретизации, к которой приводим все движки (Гц, моно).
_SR = 24000


class TTSError(RuntimeError):
    """Ошибка озвучки (нет движка/модели/голоса)."""


@dataclass
class TTSResult:
    file_path: str
    duration_sec: int
    voice_id: str
    engine: str
    status: str  # ready / pending_manual / failed


# Параметры «живости» голоса по умолчанию. Переопределяются глобальными
# настройками приложения (app_settings.get_voice_params()).
_DEFAULT_PARAMS: dict = {
    "speed": 0.95,            # темп речи, 1.0 = норма; <1 медленнее (спокойнее)
    "pitch": 0,              # сдвиг высоты тона в полутонах (только edge), -6..+6
    "sentence_pause_ms": 160,  # пауза между предложениями
    "paragraph_pause_ms": 650,  # пауза между абзацами
    "post_process": True,    # тёплая пост-обработка через FFmpeg
    "warmth": 0.35,          # интенсивность тепла/реверберации, 0..1
}


# Маппинг языка на дефолтный голос, если в проекте не задан свой.
# Для русского по умолчанию берём Edge (нативный русский), не Kokoro-workaround.
_DEFAULT_VOICES = {
    "ru": "ru-RU-DmitryNeural",
    "en": "en-US-BrianNeural",
    "es": "ef_dora",
    "fr": "ff_siwis",
    "it": "if_sara",
    "pt": "pf_dora",
    "ja": "jf_alpha",
    "zh": "zf_xiaobei",
    "hi": "hf_alpha",
}


def _detect_engine(voice_id: str) -> str:
    """Определяет движок по формату voice_id.

    Edge-голоса выглядят как "ru-RU-DmitryNeural"; всё остальное — Kokoro.
    """
    return "edge" if "Neural" in voice_id else "kokoro"


def _merge_params(voice_params: dict | None) -> dict:
    p = {**_DEFAULT_PARAMS}
    if voice_params:
        for k, v in voice_params.items():
            if v is not None:
                p[k] = v
    return p


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


# ── Разбивка текста на сегменты для естественных пауз ──────────────────────

_MD_HEADER = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_MARKS = re.compile(r"[*_`>#]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _clean_for_tts(text: str) -> str:
    """Убирает markdown-разметку, которую движок иначе прочитал бы вслух."""
    text = _MD_HEADER.sub("", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)   # картинки
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # ссылки -> текст
    text = _MD_MARKS.sub("", text)
    return text


def _segment_text(text: str) -> list[tuple[str, bool]]:
    """Делит текст на сегменты. Возвращает список (фраза, конец_абзаца).

    Абзацы — по пустым строкам; длинные абзацы дополнительно режутся по
    предложениям, чтобы между ними можно было вставить короткие паузы.
    """
    text = _clean_for_tts(text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        # Нет пустых строк — считаем каждую непустую строку абзацем.
        paragraphs = [ln.strip() for ln in text.splitlines() if ln.strip()] or paragraphs

    segments: list[tuple[str, bool]] = []
    for para in paragraphs:
        para = " ".join(para.split())
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(para) if s.strip()]
        if not sentences:
            continue
        for i, sent in enumerate(sentences):
            is_para_end = i == len(sentences) - 1
            segments.append((sent, is_para_end))
    return segments


def _assemble(blocks: list, gaps_ms: list[int]):
    """Склеивает список numpy-массивов, вставляя между ними паузы (тишину)."""
    import numpy as np

    parts = []
    for i, block in enumerate(blocks):
        parts.append(np.asarray(block, dtype="float32").reshape(-1))
        gap = gaps_ms[i] if i < len(gaps_ms) else 0
        if gap > 0:
            parts.append(np.zeros(int(_SR * gap / 1000), dtype="float32"))
    if not parts:
        return np.zeros(0, dtype="float32")
    return np.concatenate(parts)


# ── Движки синтеза (один сегмент -> numpy float32 @ _SR) ───────────────────

def _kokoro_blocks(segments: list[tuple[str, bool]], voice: str, speed: float) -> list:
    """Синтез через Kokoro. Возвращает по одному массиву на сегмент."""
    try:
        import numpy as np
        from kokoro import KPipeline
    except ImportError as e:  # pragma: no cover
        raise TTSError(
            "Kokoro TTS не установлен. Установите: pip install kokoro soundfile, "
            "переключите голос на Edge (ru-RU-DmitryNeural и т.п.) или режим "
            "tts_mode='manual'."
        ) from e

    lang_code = voice[0] if voice else "a"
    pipeline = KPipeline(lang_code=lang_code)
    blocks = []
    for text, _ in segments:
        chunks = [audio for _, _, audio in pipeline(text, voice=voice, speed=speed)]
        blocks.append(np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32"))
    return blocks


def _edge_blocks(segments: list[tuple[str, bool]], voice: str, speed: float, pitch: int) -> list:
    """Синтез через Edge TTS. Каждый сегмент -> mp3 -> декод в numpy @ _SR."""
    try:
        import edge_tts
        import soundfile as sf
    except ImportError as e:  # pragma: no cover
        raise TTSError(
            "edge-tts не установлен. Установите: pip install edge-tts soundfile."
        ) from e

    # Edge принимает относительные значения строкой: rate "-8%", pitch "+0Hz".
    rate = f"{int(round((speed - 1.0) * 100)):+d}%"
    pitch_hz = f"{int(round(pitch * 12)):+d}Hz"  # ~12 Гц на полутон (грубо)

    async def _one(text: str, dst: Path) -> None:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch_hz)
        await comm.save(str(dst))

    blocks = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        for i, (text, _) in enumerate(segments):
            mp3 = tmpd / f"seg_{i}.mp3"
            wav = tmpd / f"seg_{i}.wav"
            # Edge иногда возвращает "No audio received" (транзиентный сбой
            # серверов Microsoft / протухший токен) — повторяем несколько раз.
            last_err: Exception | None = None
            for attempt in range(4):
                try:
                    asyncio.run(_one(text, mp3))
                    last_err = None
                    break
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    if attempt < 3:
                        import time
                        time.sleep(0.6 * (attempt + 1))
            if last_err is not None:
                raise TTSError(f"Edge TTS не смог озвучить сегмент: {last_err}") from last_err
            # Декодируем mp3 -> wav @ _SR, моно.
            subprocess.run(
                [settings.ffmpeg_path, "-y", "-i", str(mp3),
                 "-ar", str(_SR), "-ac", "1", str(wav)],
                capture_output=True, check=False,
            )
            if wav.exists():
                data, _ = sf.read(str(wav))
                blocks.append(data)
            else:
                import numpy as np
                blocks.append(np.zeros(0, dtype="float32"))
    return blocks


def _post_process(raw: Path, out_path: Path, warmth: float) -> None:
    """Тёплая пост-обработка: компрессия динамики, мягкий EQ, лёгкая реверберация.

    Делает голос ровнее и «теплее» — ближе к студийной начитке.
    """
    filters = [
        "acompressor=threshold=-18dB:ratio=3:attack=15:release=250",
        "equalizer=f=180:t=q:w=1.2:g=2",     # тёплый низ
        "equalizer=f=3200:t=q:w=2:g=1.4",    # разборчивость/присутствие
    ]
    if warmth > 0:
        decay = min(0.9, 0.75 + warmth * 0.15)
        delay = int(35 + warmth * 45)
        filters.append(f"aecho=0.85:{decay:.2f}:{delay}:{0.08 + warmth * 0.18:.2f}")
    filters.append("dynaudnorm=f=200:g=5")   # мягкая нормализация громкости
    subprocess.run(
        [settings.ffmpeg_path, "-y", "-i", str(raw),
         "-af", ",".join(filters), "-ar", str(_SR), "-ac", "1", str(out_path)],
        capture_output=True, check=False,
    )


def _synthesize_local(
    text: str, voice: str, out_path: Path, params: dict
) -> int:
    """Полный конвейер локального синтеза: сегменты -> движок -> паузы -> пост."""
    import numpy as np
    import soundfile as sf

    segments = _segment_text(text)
    if not segments:
        raise TTSError("Пустой текст для озвучки.")

    speed = float(params["speed"])
    engine = _detect_engine(voice)
    if engine == "edge":
        blocks = _edge_blocks(segments, voice, speed, int(params["pitch"]))
    else:
        blocks = _kokoro_blocks(segments, voice, speed)

    # Паузы: после предложения — короткая, в конце абзаца — длинная.
    sp = int(params["sentence_pause_ms"])
    pp = int(params["paragraph_pause_ms"])
    gaps = [pp if is_end else sp for (_, is_end) in segments]
    gaps[-1] = 0  # без хвостовой тишины
    full = _assemble(blocks, gaps)
    if full.size == 0:
        raise TTSError("Движок вернул пустой результат озвучки.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if params.get("post_process"):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.wav"
            sf.write(str(raw), full, _SR)
            _post_process(raw, out_path, float(params["warmth"]))
        if not out_path.exists():  # если ffmpeg-фильтр упал — пишем без обработки
            sf.write(str(out_path), full, _SR)
    else:
        sf.write(str(out_path), full, _SR)
    return _wav_duration(out_path)


_PREVIEW_TEXT = {
    "ru": "Привет! Это пример голоса для предпрослушивания. Послушайте, как он звучит.",
    "en": "Hello! This is a short voice preview sample. Listen to how it sounds.",
    "es": "¡Hola! Esta es una breve muestra de voz.",
    "fr": "Bonjour ! Voici un court échantillon de cette voix.",
    "de": "Hallo! Dies ist eine kurze Sprachprobe.",
    "it": "Ciao! Questo è un breve campione di questa voce.",
    "pt": "Olá! Esta é uma breve amostra desta voz.",
    "ja": "こんにちは。これは音声のサンプルです。",
    "zh": "你好，这是一个语音示例。",
    "hi": "नमस्ते! यह आवाज़ का एक छोटा नमूना है।",
}


def synthesize_preview(
    language: str, voice_id: str, out_path: Path, voice_params: dict | None = None
) -> int:
    """Короткий тестовый сэмпл для прослушивания голоса (Kokoro или Edge)."""
    text = _PREVIEW_TEXT.get(language, _PREVIEW_TEXT["en"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return _synthesize_local(text, voice_id, out_path, _merge_params(voice_params))


def synthesize(
    *,
    text: str,
    language: str,
    out_path: Path,
    tts_mode: str,
    voice_settings: dict[str, str],
    voice_params: dict | None = None,
) -> TTSResult:
    """Озвучивает текст в файл out_path согласно режиму канала."""
    voice = voice_settings.get(language) or _DEFAULT_VOICES.get(language, "en-US-BrianNeural")

    if tts_mode == "manual":
        logger.info("TTS manual режим: ожидается ручная загрузка озвучки для {lang}", lang=language)
        return TTSResult(
            file_path=str(out_path),
            duration_sec=0,
            voice_id="manual",
            engine="manual",
            status="pending_manual",
        )

    params = _merge_params(voice_params)
    engine = _detect_engine(voice)
    logger.info(
        "Озвучка {lang} движком {eng} голосом {voice} (speed={sp}, pauses {spause}/{ppause}мс)",
        lang=language, eng=engine, voice=voice,
        sp=params["speed"], spause=params["sentence_pause_ms"], ppause=params["paragraph_pause_ms"],
    )
    duration = _synthesize_local(text, voice, out_path, params)
    return TTSResult(
        file_path=str(out_path),
        duration_sec=duration,
        voice_id=voice,
        engine=engine,
        status="ready",
    )
