"""Генерация зацикленной последовательности кадров с частицами.

Два вида:
- "embers"    — искры огня: тёплые оранжевые точки, дрейфуют вверх, мерцают.
- "fireflies" — светлячки: жёлто-зелёные огоньки по всему экрану, медленно
                блуждают на месте и подмигивают.

Кадры рисуются один раз через Pillow и кешируются на диске (DATA_DIR/particles/<kind>).
Фон чёрный, точки — светящиеся круги: при наложении на видео через
ffmpeg blend=screen чёрный фон не даёт эффекта (screen с чёрным = no-op), а
яркие точки аддитивно подсвечивают кадр — никакой альфа-канал не нужен.

Важно: все частоты/скорости — целые числа циклов на длину лупа, поэтому
анимация зацикливается бесшовно (без "щелчка" на стыке).
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from loguru import logger

_N_FRAMES = 250  # 10 секунд при 25 fps
_SIZE = (1280, 720)

# Маркер кеша: v2 — новый формат (250 кадров, бесшовный луп, виды частиц)
_MARKER = "_done_v2"

_KINDS: dict[str, dict] = {
    "embers": {
        "n": 22,
        "colors": [(255, 200, 120), (255, 170, 90), (255, 140, 60), (255, 225, 160)],
        "radius": (2.0, 5.0),
        "blur": 3,
        "drift_cycles": (1, 2),     # полных проходов экрана вверх за луп
        "sway_amp": (10, 40),
        "sway_cycles": (1, 3),
        "twinkle_cycles": (3, 9),
        "twinkle_depth": 0.45,      # 0.55 + 0.45*sin
        "brightness": (0.6, 1.0),
    },
    "fireflies": {
        "n": 34,
        "colors": [(220, 255, 150), (255, 240, 140), (190, 255, 130), (255, 255, 190)],
        "radius": (1.5, 3.2),
        "blur": 2,
        "drift_cycles": (0, 0),     # не дрейфуют — блуждают на месте
        "sway_amp": (25, 80),
        "sway_cycles": (1, 3),
        "twinkle_cycles": (2, 6),
        "twinkle_depth": 0.75,      # глубокое "подмигивание"
        "brightness": (0.5, 1.0),
    },
    "dust": {
        "n": 44,
        "colors": [(225, 222, 210), (205, 208, 220), (235, 230, 215), (210, 205, 195)],
        "radius": (1.0, 2.4),
        "blur": 2,
        "drift_cycles": (-1, 0),    # медленно оседают вниз (или висят)
        "sway_amp": (15, 55),
        "sway_cycles": (1, 2),
        "twinkle_cycles": (1, 3),
        "twinkle_depth": 0.30,      # почти не мерцают — просто плывут
        "brightness": (0.22, 0.5),  # тусклые, ненавязчивые
    },
}


def _draw_frame(particles: list[dict], frame_idx: int, size: tuple[int, int], blur: int):
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.new("RGB", size, (0, 0, 0))
    draw = ImageDraw.Draw(img)
    w, h = size
    t = frame_idx / _N_FRAMES

    for p in particles:
        # Вертикальный дрейф (целое число проходов за луп -> бесшовно) +
        # синусоидальное блуждание по обеим осям (целые частоты -> бесшовно)
        y = (p["y0"] - t * p["drift"] * h + math.sin(t * 2 * math.pi * p["sway_y_freq"] + p["phase_y"]) * p["sway_amp"] * 0.6) % h
        x = (p["x0"] + math.sin(t * 2 * math.pi * p["sway_x_freq"] + p["phase_x"]) * p["sway_amp"]) % w
        # Мерцание яркости (твинкл)
        twinkle = (1.0 - p["twinkle_depth"]) + p["twinkle_depth"] * math.sin(
            t * 2 * math.pi * p["twinkle_freq"] + p["phase_x"] * 3
        )
        brightness = max(0.0, min(1.0, twinkle)) * p["base_brightness"]
        r = int(p["color"][0] * brightness)
        g = int(p["color"][1] * brightness)
        b = int(p["color"][2] * brightness)
        radius = p["radius"]
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(r, g, b))

    return img.filter(ImageFilter.GaussianBlur(radius=blur))


def _particles_dir(kind: str) -> Path:
    from app.core.config import settings

    p = settings.data_path / "particles" / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_particle_frames(kind: str = "embers") -> Path:
    """Генерирует (один раз, кешируя) папку с кадрами частиц. Возвращает путь к папке."""
    cfg = _KINDS.get(kind)
    if cfg is None:
        logger.warning("Неизвестный вид частиц '{kind}', использую 'embers'", kind=kind)
        kind, cfg = "embers", _KINDS["embers"]

    out_dir = _particles_dir(kind)
    marker = out_dir / _MARKER
    if marker.exists():
        return out_dir

    try:
        from PIL import Image  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Pillow не установлен. Установите: pip install pillow") from e

    rng = random.Random(42)  # фиксированный сид -> воспроизводимая, но "случайная" картина
    particles = [
        {
            "x0": rng.uniform(0, _SIZE[0]),
            "y0": rng.uniform(0, _SIZE[1]),
            "drift": rng.randint(*cfg["drift_cycles"]),
            "sway_amp": rng.uniform(*cfg["sway_amp"]),
            "sway_x_freq": rng.randint(*cfg["sway_cycles"]),
            "sway_y_freq": rng.randint(*cfg["sway_cycles"]),
            "twinkle_freq": rng.randint(*cfg["twinkle_cycles"]),
            "twinkle_depth": cfg["twinkle_depth"],
            "phase_x": rng.uniform(0, math.pi * 2),
            "phase_y": rng.uniform(0, math.pi * 2),
            "radius": rng.uniform(*cfg["radius"]),
            "base_brightness": rng.uniform(*cfg["brightness"]),
            "color": rng.choice(cfg["colors"]),
        }
        for _ in range(cfg["n"])
    ]

    for i in range(_N_FRAMES):
        frame = _draw_frame(particles, i, _SIZE, cfg["blur"])
        frame.save(out_dir / f"frame_{i:04d}.png", "PNG")

    marker.write_text("ok", encoding="utf-8")
    logger.info("Частицы '{kind}' сгенерированы: {dir} ({n} кадров)", kind=kind, dir=out_dir, n=_N_FRAMES)
    return out_dir
