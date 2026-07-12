"""Генерация обложки YouTube 1280×720 через Replicate (Ideogram V3 Turbo / FLUX, полностью AI).

Текст на обложке рисует сама модель (по инструкции в промте), отдельного
наложения через Pillow для AI-обложек больше нет.

Приоритет: Ideogram V3 Turbo (лучший текст) → FLUX.1 Pro → Pollinations FLUX →
Pillow-градиент, если Replicate недоступен.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.core.config import settings
from app.core.llm import LLMError, llm_client


class ThumbnailError(RuntimeError):
    pass


def _detect_language(text: str) -> str:
    """Грубое определение языка заголовка по алфавиту (кириллица/латиница), без внешних либ."""
    cyrillic = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
    latin = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    return "Russian" if cyrillic > latin else "English"


def _generate_thumbnail_prompt(title: str, niche: str = "", style_hint: str = "") -> str:
    """Просит LLM придумать визуальный промт для YouTube-обложки (оптимизирован для FLUX.1 Pro).

    Модель сама придумывает короткую цепляющую надпись (2-5 слов, на языке заголовка)
    и получает явную инструкцию отрисовать именно её крупным жирным шрифтом на картинке —
    отдельного наложения текста поверх больше нет. Язык надписи определяется в коде
    (по алфавиту заголовка), а не отдаётся на усмотрение LLM, чтобы Style notes на другом
    языке не перебивали язык самого заголовка.
    """
    caption_lang = _detect_language(title)
    system = (
        "You are a YouTube thumbnail art director optimizing prompts for FLUX.1 Pro image model. "
        "Write ONE detailed visual prompt (max 150 words) describing a stunning YouTube thumbnail scene "
        "that includes bold typography baked directly into the image. "
        f"First, invent a SHORT, punchy caption (2-5 words max, written strictly in {caption_lang}, "
        f"regardless of the language used in the niche or style notes below) "
        "that captures the hook of the video — never the full title, always short. "
        "Then explicitly instruct the image model to render EXACTLY that caption as huge, bold, "
        "high-contrast text (with outline or drop shadow for legibility) placed in the lower third of the frame, "
        "integrated naturally into the scene like a real YouTube thumbnail. "
        "Also describe dramatic cinematic lighting, vivid colors, sharp details, professional composition "
        "matching the video topic and mood — no generic stock-photo look. "
        "Put the caption text inside quotes in the prompt so it is unambiguous. "
        "Output ONLY the image prompt, nothing else."
    )
    prompt = (
        f"Video title: {title}\n"
        f"Caption language: {caption_lang}\n"
        f"Channel niche: {niche or 'general'}\n"
        f"Style notes: {style_hint or 'none'}"
    )
    try:
        result = llm_client.complete(
            system=system, prompt=prompt,
            model=settings.model_fast, max_tokens=250, stream=False,
        )
        return result.text.strip()
    except LLMError:
        return (
            f'YouTube thumbnail, cinematic dramatic scene matching the topic "{title}". '
            f'Huge bold white text with dark outline reading a short catchy caption related to the topic, '
            f'placed in the lower third, warm rich colors, professional composition.'
        )


def _generate_pollinations(prompt: str, out_path: Path) -> bool:
    """Генерирует обложку через Pollinations.ai (FLUX, бесплатно, без ключа)."""
    try:
        import hashlib
        import urllib.parse

        import httpx

        encoded = urllib.parse.quote(prompt)
        seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % 10000
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=2560&height=1440&nologo=true&seed={seed}&model=flux"
        )
        r = httpx.get(
            url, timeout=90, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200 and len(r.content) > 1024:
            out_path.write_bytes(r.content)
            return True
        logger.warning("[thumbnail] Pollinations вернул {s}", s=r.status_code)
    except Exception as e:
        logger.warning("[thumbnail] Pollinations не сработал: {err}", err=str(e)[:200])
    return False


def _collect_replicate_output(output) -> bytes | None:
    """Собирает байты картинки из ответа Replicate (FileOutput — стрим байтовых чанков)."""
    chunks: list[bytes] = []
    if isinstance(output, bytes):
        chunks = [output]
    elif isinstance(output, list) and output:
        return _collect_replicate_output(output[0])
    elif hasattr(output, "__iter__"):
        for chunk in output:
            if isinstance(chunk, bytes):
                chunks.append(chunk)
            elif hasattr(chunk, "read"):
                chunks.append(chunk.read())
            elif isinstance(chunk, str) and chunk.startswith("http"):
                import httpx
                with httpx.stream("GET", chunk, timeout=120, follow_redirects=True) as r:
                    r.raise_for_status()
                    chunks.append(r.read())
                break

    if chunks:
        data = b"".join(chunks)
        if len(data) > 1024:
            return data
    return None


def _generate_ideogram(prompt: str, out_path: Path) -> bool:
    """Генерирует обложку через Ideogram V3 Turbo (Replicate) — лучший вариант для текста в кадре."""
    if not settings.has_replicate:
        return False
    try:
        import replicate
        client = replicate.Client(api_token=settings.replicate_api_token, timeout=180)
        output = client.run(
            "ideogram-ai/ideogram-v3-turbo",
            input={
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "magic_prompt_option": "Off",
            },
        )
        data = _collect_replicate_output(output)
        if data:
            out_path.write_bytes(data)
            return True
        logger.warning("[thumbnail] Ideogram: не удалось получить изображение")
        return False
    except Exception as e:
        logger.warning("[thumbnail] Ideogram не сработал: {err}", err=str(e)[:300])
    return False


def _generate_flux_pro(prompt: str, out_path: Path) -> bool:
    """Генерирует обложку через FLUX.1 Pro (Replicate). Возвращает True при успехе."""
    if not settings.has_replicate:
        return False
    try:
        import replicate
        client = replicate.Client(api_token=settings.replicate_api_token, timeout=180)
        output = client.run(
            "black-forest-labs/flux-1.1-pro",
            input={
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "output_format": "png",
                "output_quality": 100,
                "safety_tolerance": 2,
                "prompt_upsampling": True,
            },
        )
        data = _collect_replicate_output(output)
        if data:
            out_path.write_bytes(data)
            return True
        logger.warning("[thumbnail] FLUX Pro: не удалось получить изображение")
        return False
    except Exception as e:
        logger.warning("[thumbnail] FLUX Pro не сработал: {err}", err=str(e)[:300])
    return False


def _fallback_pillow(title: str, accent_color: str, out_path: Path) -> None:
    """Fallback: градиент + текст через Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    def hex_rgb(v: str) -> tuple[int, int, int]:
        v = v.lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        try:
            return tuple(int(v[i:i+2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            return (99, 102, 241)

    accent = hex_rgb(accent_color)
    dark = (17, 17, 27)
    img = Image.new("RGB", (1280, 720), dark)
    for y in range(720):
        t = y / 720
        r = int(dark[0] + (accent[0] - dark[0]) * t * 0.7)
        g = int(dark[1] + (accent[1] - dark[1]) * t * 0.7)
        b = int(dark[2] + (accent[2] - dark[2]) * t * 0.7)
        ImageDraw.Draw(img).line([(0, y), (1280, y)], fill=(r, g, b))

    draw = ImageDraw.Draw(img)
    font = None
    for size in (72, 56, 44, 36):
        for fname in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "arial.ttf"):
            try:
                font = ImageFont.truetype(fname, size)
                break
            except OSError:
                continue
        if font:
            break
    if font is None:
        font = ImageFont.load_default()

    words = (title or "Untitled").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textbbox((0, 0), test, font=font)[2] > 1088 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)

    lh = draw.textbbox((0, 0), "Ay", font=font)[3] + 10
    y = 720 - lh * len(lines) - 48
    for line in lines:
        lw = draw.textbbox((0, 0), line, font=font)[2]
        x = (1280 - lw) // 2
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=accent)
        y += lh

    img.save(str(out_path), "PNG")


class ThumbnailResult:
    def __init__(self, path: str, model: str, prompt: str) -> None:
        self.path = path
        self.model = model
        self.prompt = prompt


def generate_thumbnail(
    *,
    title: str,
    out_path: Path,
    accent_color: str = "#6366f1",
    niche: str = "",
    style_hint: str = "",
) -> ThumbnailResult:
    """Генерирует обложку через Ideogram V3 Turbo → FLUX.1 Pro → Pollinations → Pillow fallback.

    Короткую надпись рисует сама AI-модель по инструкции в промте — отдельного
    наложения текста через Pillow для AI-обложек больше нет. Ideogram V3 Turbo стоит
    первым, так как специально заточена под точную отрисовку текста в кадре.
    Возвращает ThumbnailResult с путём, моделью и промтом.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ai_prompt = _generate_thumbnail_prompt(title, niche=niche, style_hint=style_hint)
    logger.debug("[thumbnail] промт: {p}", p=ai_prompt[:150])

    model_used = ""
    ai_generated = False

    if _generate_ideogram(ai_prompt, out_path):
        model_used = "Ideogram V3 Turbo"
        logger.info("Обложка готова (Ideogram V3 Turbo): {p}", p=out_path)
        ai_generated = True
    elif _generate_flux_pro(ai_prompt, out_path):
        model_used = "FLUX.1 Pro"
        logger.info("Обложка готова (FLUX.1 Pro): {p}", p=out_path)
        ai_generated = True
    elif _generate_pollinations(ai_prompt, out_path):
        model_used = "Pollinations FLUX"
        logger.info("Обложка сгенерирована (Pollinations FLUX): {p}", p=out_path)
        ai_generated = True

    if ai_generated:
        return ThumbnailResult(str(out_path), model_used, ai_prompt)

    # Полный fallback: Pillow-градиент
    try:
        from PIL import Image  # noqa: F401
    except ImportError as e:
        raise ThumbnailError("Pillow не установлен и все AI-сервисы недоступны") from e

    _fallback_pillow(title, accent_color, out_path)
    logger.info("Обложка готова (Pillow fallback): {p}", p=out_path)
    return ThumbnailResult(str(out_path), "Pillow (fallback)", "")
