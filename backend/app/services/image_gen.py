"""AI-генерация визуального ряда: картинки по контексту сценария.

Поток:
1. generate_image_prompts() — один запрос к LLM (быстрая модель), получаем
   список из N промтов на английском, каждый описывает визуальную сцену для
   своего отрезка видео (раскладка по смыслу всего сценария, не только intro).
2. generate_image() — каждый промт уходит в Replicate (FLUX schnell, самая
   дешёвая модель из каталога, ~$0.003/картинка), результат скачивается на диск.

Картинка меняется каждые settings.visual_segment_minutes минут видео —
число картинок считается из длительности и капается visual_max_images, чтобы
случайно не сжечь бюджет на сверхдлинном видео.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass

from loguru import logger

from app.core.config import settings
from app.core.llm import LLMError, LLMResult, llm_client


class ImageGenError(RuntimeError):
    """Ошибка генерации изображения (нет ключа/пакета, сбой API)."""


# Авто-повтор на временных сетевых сбоях Replicate (часто из-за нестабильного VPN)
_RETRIES = 3
_RETRY_BASE_SEC = 2
_TRANSIENT_MARKERS = (
    "SSL", "EOF", "timed out", "timeout", "Connection", "connection",
    "reset", "RemoteProtocol", "ServerDisconnected", "503", "502", "429",
    "throttled", "rate limit",
)


# Жёстко прибавляется к промту каждой картинки независимо от того, что решит
# LLM — гарантирует тёплую пастельную палитру и максимальное качество всегда.
_QUALITY_SUFFIX = (
    "warm pastel color grading, soft golden light, gentle warm highlights, "
    "best quality, ultra-detailed, sharp focus, high resolution"
)


# Модели, доступные для выбора при (пере)генерации видеоряда — id совпадает
# со slug'ом на Replicate, кроме "gemini" (отдельный бесплатный движок).
IMAGE_MODEL_OPTIONS: list[dict] = [
    {"id": "black-forest-labs/flux-2-dev", "label": "FLUX.2 [dev] — баланс цена/качество (~$0.012/шт)"},
    {"id": "black-forest-labs/flux-2-pro", "label": "FLUX.2 [pro] — топ качество FLUX.2 (~$0.055/шт)"},
    {"id": "black-forest-labs/flux-schnell", "label": "FLUX Schnell — самая дешёвая (~$0.003/шт)"},
    {"id": "black-forest-labs/flux-dev", "label": "FLUX Dev (~$0.025/шт)"},
    {"id": "black-forest-labs/flux-1.1-pro", "label": "FLUX 1.1 Pro (~$0.04/шт)"},
    {"id": "ideogram-ai/ideogram-v3-turbo", "label": "Ideogram V3 Turbo — лучший текст в кадре (~$0.03/шт)"},
    {"id": "gemini", "label": "Gemini (Nano Banana) — бесплатно при наличии ключа"},
]


def _build_image_input(model: str, prompt: str, seed: int | None) -> dict:
    """Собирает input для Replicate под конкретную модель — у разных семейств разные схемы полей."""
    base: dict = {"prompt": prompt}
    if model.startswith("black-forest-labs/flux"):
        base.update({"num_outputs": 1, "aspect_ratio": "16:9", "output_format": "png"})
        if model.endswith("flux-schnell") or model.endswith("flux-dev"):
            base["go_fast"] = True
        if model.endswith("flux-1.1-pro"):
            base.update({"output_quality": 100, "safety_tolerance": 2, "prompt_upsampling": True})
        if seed is not None:
            base["seed"] = seed
    elif model.startswith("ideogram-ai/"):
        base.update({"aspect_ratio": "16:9", "magic_prompt_option": "Off"})
    else:
        base["aspect_ratio"] = "16:9"
    return base


def segments_for_duration(duration_sec: int) -> int:
    """Сколько картинок нужно при смене каждые visual_segment_minutes минут."""
    if duration_sec <= 0:
        return 1
    minutes = duration_sec / 60
    count = max(1, round(minutes / settings.visual_segment_minutes))
    return min(count, settings.visual_max_images)


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


@dataclass
class PromptsResult:
    prompts: list[str]
    style: str
    llm: LLMResult | None


def generate_image_prompts(
    script_text: str, count: int, niche: str = "", style_hint: str = ""
) -> PromptsResult:
    """Просит LLM задать ОДИН общий визуальный стиль + count сцен под сценарий.

    Общий стиль (медиум, палитра, свет, реализм) добавляется к каждой сцене,
    чтобы все картинки выглядели как одна серия. Для исторического канала стиль
    и каждая сцена обязаны быть строго в эпохе — без современных объектов.
    """
    system = (
        "You are the art director for a YouTube video. You receive the full "
        "voiceover script and design a consistent visual sequence.\n\n"
        "STEP 1 — Define ONE shared visual STYLE for the whole video, fitting the channel.\n"
        f"Channel niche/theme: {niche or 'general'}.\n"
        f"Extra style notes: {style_hint or 'none'}.\n"
        "The style line must lock the art medium (e.g. dramatic oil painting, or "
        "cinematic film still), color palette, lighting, mood and level of realism — "
        "so every image clearly belongs to the same series.\n"
        "Color grading must be warm and soft pastel: golden-hour light, warm amber/rose "
        "tones, gentle low-contrast pastel colors — even on serious or historical topics, "
        "the GRADING stays warm and soft (this is about lighting/color only, not content).\n"
        "If the channel or topic is historical, every OBJECT, outfit, vehicle and setting "
        "in the style and every scene MUST be strictly period-accurate: absolutely no "
        "modern objects, clothing, vehicles, technology, signage — no anachronisms.\n\n"
        "STEP 2 — Split the script into exactly N sequential scenes covering the whole "
        "video from start to end. For each scene write ONE concrete description of the "
        "subject, action and setting only — do NOT restate the style (it is appended "
        "automatically).\n\n"
        "FRAMING — keep it UNIFORM across every scene so the series feels like one film:\n"
        "- Every scene is a WIDE establishing / long shot showing the whole environment "
        "(landscape, town, hall, battlefield) with any figures small within the frame.\n"
        "- NEVER mix shot types: no close-ups, no macro detail shots, no flat top-down "
        "maps/diagrams, no portraits. Do not jump from a wide landscape in one scene to a "
        "tight close-up of an object or a person in another.\n"
        "- Keep the same camera distance, eye-level horizon and broad composition logic in "
        "all scenes, so the exposure and framing do not jump around.\n\n"
        "Rules: English only; one dense sentence per scene; a concrete subject tied to "
        "that part of the script; no text, captions or logos baked into the image; scenes "
        "differ in content but stay consistent in style and framing.\n\n"
        f"N = {count}.\n"
        'Output ONLY JSON: {"style": "<shared style line>", "scenes": ["<scene 1>", ...]} '
        "with exactly N scenes, nothing else."
    )
    # Пробуем model_fast (может быть Gemini при включённом VPN).
    # Если Gemini недоступен гео-блокировкой — пробуем основную модель (Claude).
    # Если и она недоступна — fallback на дефолтные сцены (Replicate всё равно нарисует).
    result: LLMResult | None = None
    style = ""
    scenes: list[str] = []
    try:
        result = llm_client.complete(
            system=system, prompt=script_text, model=settings.model_fast, max_tokens=3000, stream=False
        )
    except LLMError as e:
        logger.warning("[visuals] LLM недоступна для промтов ({err}) — используем дефолтные сцены", err=e)

    if result is not None:
        try:
            data = _extract_json_object(result.text)
            style = str(data.get("style", "")).strip()
            scenes = [str(s).strip() for s in (data.get("scenes") or []) if str(s).strip()]
        except (json.JSONDecodeError, IndexError, ValueError) as e:
            logger.error("Не удалось распарсить промты визуального ряда: {err}", err=e)

    if not scenes:
        scenes = ["An establishing scene related to the video topic"]
    # Подгоняем под нужное количество (LLM иногда отдаёт +-1)
    if len(scenes) < count:
        scenes += [scenes[-1]] * (count - len(scenes))
    elif len(scenes) > count:
        scenes = scenes[:count]

    if not style:
        style = "cinematic, warm soft pastel tones, golden-hour light, highly detailed, 16:9"
    # Жёсткий технический суффикс (не зависит от LLM) — тёплая пастельная палитра
    # и максимальное качество на каждой картинке, независимо от того, что
    # допишет модель в свой style.
    full_style = f"{style}. {_QUALITY_SUFFIX}"
    # Общий стиль добавляется к каждой сцене -> единая серия картинок.
    prompts = [f"{scene}. Style: {full_style}" for scene in scenes]
    return PromptsResult(prompts=prompts, style=full_style, llm=result)


def _ensure_replicate():
    if not settings.has_replicate:
        raise ImageGenError(
            "REPLICATE_API_TOKEN не задан. Укажите ключ в .env, чтобы генерировать "
            "AI-визуальный ряд (получить — replicate.com/account/api-tokens)."
        )
    try:
        import replicate
    except ImportError as e:  # pragma: no cover
        raise ImageGenError(
            "Пакет 'replicate' не установлен. Выполните: pip install replicate"
        ) from e
    return replicate.Client(api_token=settings.replicate_api_token)


def _run_replicate(client, model: str, input_dict: dict):
    """Один вызов Replicate с авто-повтором на временных сбоях/троттлинге."""
    for attempt in range(_RETRIES):
        try:
            return client.run(model, input=input_dict)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            transient = any(s in msg for s in _TRANSIENT_MARKERS)
            if transient and attempt < _RETRIES - 1:
                # Rate-limit (429) считается в запросах/минуту — короткой паузы мало.
                rate_limited = "429" in msg or "throttled" in msg or "rate limit" in msg
                pause = 15 * (attempt + 1) if rate_limited else _RETRY_BASE_SEC * (attempt + 1)
                logger.warning(
                    "Replicate: временный сбой, повтор через {p}с ({a}/{n}): {err}",
                    p=pause, a=attempt + 1, n=_RETRIES, err=msg[:200],
                )
                time.sleep(pause)
                continue
            raise ImageGenError(f"Ошибка Replicate ({model}): {e}") from e


def _save_output(output, out_path) -> None:
    """Сохраняет результат Replicate (url/FileOutput/bytes) в out_path с авто-повтором."""
    item = output[0] if isinstance(output, (list, tuple)) else output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = str(item.url) if hasattr(item, "url") else (item if isinstance(item, str) else None)

    for attempt in range(_RETRIES):
        try:
            if url is not None:
                _download(url, out_path)
            elif hasattr(item, "read"):
                out_path.write_bytes(item.read())
            else:
                out_path.write_bytes(bytes(item))
            return
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            transient = any(s in msg for s in _TRANSIENT_MARKERS)
            if transient and attempt < _RETRIES - 1:
                pause = _RETRY_BASE_SEC * (attempt + 1)
                logger.warning(
                    "Replicate: сбой скачивания файла, повтор через {p}с ({a}/{n}): {err}",
                    p=pause, a=attempt + 1, n=_RETRIES, err=msg[:200],
                )
                time.sleep(pause)
                continue
            raise ImageGenError(f"Не удалось сохранить файл Replicate: {e}") from e


def generate_image(
    prompt: str, out_path, seed: int | None = None, reference_image_path=None, model: str | None = None
) -> None:
    """Генерирует одну картинку через Replicate и сохраняет в out_path.

    model — slug модели на Replicate (см. IMAGE_MODEL_OPTIONS); по умолчанию
    берётся settings.replicate_image_model (FLUX.2 [dev]).
    seed — общий на всё видео сид для более стабильной композиции/палитры.
    reference_image_path — опорная картинка (первая в серии): если задана и
    включён settings.visual_use_reference, генерация идёт в режиме img2img,
    чтобы держать единый стиль. Если модель не поддерживает входной image —
    откатываемся на обычную text-to-image генерацию.
    """
    client = _ensure_replicate()
    model = model or settings.replicate_image_model
    base_input = _build_image_input(model, prompt, seed)

    use_ref = bool(reference_image_path) and settings.visual_use_reference
    output = None
    ref_file = None
    if use_ref:
        try:
            ref_file = open(reference_image_path, "rb")
            ref_input = {**base_input, "image": ref_file, "prompt_strength": settings.visual_reference_strength}
            output = _run_replicate(client, model, ref_input)
        except ImageGenError as e:
            # Модель не понимает входной image (например, flux-schnell) -> text-only.
            logger.warning("img2img-референс не сработал, fallback text-only: {err}", err=str(e)[:160])
            output = None
        finally:
            if ref_file is not None:
                ref_file.close()
    if output is None:
        output = _run_replicate(client, model, base_input)

    _save_output(output, out_path)


def upscale_image(path, scale: int | None = None) -> None:
    """Апскейлит картинку через Replicate (Real-ESRGAN, ~$0.002-0.004/шт) и перезаписывает её же.

    Поднимает типичный выход FLUX (~1 MP) до Full HD+ при scale=2. Не критично:
    при сбое вызывающий код должен оставить картинку в исходном разрешении.
    """
    client = _ensure_replicate()
    with open(path, "rb") as f:
        output = _run_replicate(
            client,
            settings.replicate_upscale_model,
            {"image": f, "scale": scale or settings.visual_upscale_factor},
        )
    _save_output(output, path)


def generate_image_gemini(prompt: str, out_path) -> None:
    """Генерирует одну картинку через Gemini (gemini-2.0-flash-exp-image-generation).

    Не требует Replicate API — использует уже настроенный Gemini ключ.
    Выход сохраняется в out_path как PNG.
    """
    if not settings.has_gemini:
        raise ImageGenError("GEMINI_API_KEY не задан — Gemini-генерация недоступна.")
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError as e:
        raise ImageGenError("Пакет 'google-genai' не установлен. Выполните: pip install google-genai") from e

    import base64
    from pathlib import Path

    client = google_genai.Client(api_key=settings.gemini_api_key)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Пробуем Imagen 4 Fast (predict/generate_images), потом Gemini Flash Image (generateContent)
    for attempt_model, use_imagen in [
        ("imagen-4.0-fast-generate-001", True),
        ("gemini-2.5-flash-image", False),
    ]:
        try:
            if use_imagen:
                response = client.models.generate_images(
                    model=attempt_model,
                    prompt=prompt,
                    config=genai_types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="16:9",
                        output_mime_type="image/png",
                    ),
                )
                if response.generated_images:
                    out.write_bytes(response.generated_images[0].image.image_bytes)
                    return
            else:
                response = client.models.generate_content(
                    model=attempt_model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
                )
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data is not None:
                        data = part.inline_data.data
                        if isinstance(data, str):
                            data = base64.b64decode(data)
                        out.write_bytes(data)
                        return
        except Exception as e:  # noqa: BLE001
            logger.warning("[gemini_img] модель {m} не сработала: {err}", m=attempt_model, err=str(e)[:200])
            continue

    raise ImageGenError(
        "Gemini не смог сгенерировать изображение. "
        "Возможные причины: (1) бесплатный план не включает image-модели — "
        "включите биллинг на ai.dev/projects; "
        "(2) гео-блокировка — проверьте VPN."
    )


def _download(url: str, out_path) -> None:
    import httpx

    resp = httpx.get(url, timeout=60)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
