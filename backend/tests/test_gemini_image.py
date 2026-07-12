"""Тесты Gemini-генерации изображений.

Запуск (из папки backend/):
    python -m pytest tests/test_gemini_image.py -v -s

Или напрямую (без pytest):
    python tests/test_gemini_image.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Быстрый smoke-тест без pytest (python tests/test_gemini_image.py)
# ---------------------------------------------------------------------------

def _run_smoke():
    print("=== Smoke-тест: Gemini Image Generation ===\n")

    try:
        from app.core.config import settings
    except Exception as e:
        print(f"[FAIL] Не удалось загрузить настройки: {e}")
        sys.exit(1)

    if not settings.has_gemini:
        print("[SKIP] GEMINI_API_KEY не задан")
        sys.exit(0)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        print("[FAIL] google-genai не установлен: pip install google-genai")
        sys.exit(1)

    client = google_genai.Client(api_key=settings.gemini_api_key)
    prompt = "A wide establishing shot of a sunlit mountain valley, warm golden light, cinematic"

    # --- Список моделей ---
    print("Доступные image-модели:")
    image_models = []
    for m in client.models.list():
        if "image" in m.name.lower() or "imagen" in m.name.lower():
            actions = getattr(m, "supported_actions", [])
            print(f"  {m.name}  actions={actions}")
            image_models.append((m.name, actions))
    print()

    with tempfile.TemporaryDirectory() as tmp:
        # --- Тест 1: Imagen Fast (predict -> generate_images) ---
        for model_name, actions in image_models:
            if "predict" in actions:
                print(f"Тест generate_images -> {model_name} ...", end=" ", flush=True)
                out = Path(tmp) / "test_imagen.png"
                try:
                    resp = client.models.generate_images(
                        model=model_name,
                        prompt=prompt,
                        config=genai_types.GenerateImagesConfig(
                            number_of_images=1,
                            aspect_ratio="16:9",
                            output_mime_type="image/png",
                        ),
                    )
                    if resp.generated_images:
                        out.write_bytes(resp.generated_images[0].image.image_bytes)
                        size = out.stat().st_size
                        print(f"OK ({size:,} байт)")
                    else:
                        print("FAIL — ответ пуст")
                except Exception as e:
                    print(f"FAIL — {e}")
                break  # тестируем первую подходящую

        # --- Тест 2: Flash Image (generateContent) ---
        for model_name, actions in image_models:
            if "generateContent" in actions:
                print(f"Тест generateContent -> {model_name} ...", end=" ", flush=True)
                out = Path(tmp) / "test_flash.png"
                try:
                    import base64
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
                    )
                    saved = False
                    for part in resp.candidates[0].content.parts:
                        if hasattr(part, "inline_data") and part.inline_data is not None:
                            data = part.inline_data.data
                            if isinstance(data, str):
                                data = base64.b64decode(data)
                            out.write_bytes(data)
                            size = out.stat().st_size
                            print(f"OK ({size:,} байт)")
                            saved = True
                            break
                    if not saved:
                        print("FAIL — изображение в ответе не найдено")
                except Exception as e:
                    print(f"FAIL — {e}")
                break  # тестируем первую подходящую

        # --- Тест 3: сервисная функция generate_image_gemini ---
        print("Тест image_gen.generate_image_gemini() ...", end=" ", flush=True)
        out = Path(tmp) / "test_service.png"
        try:
            from app.services import image_gen
            image_gen.generate_image_gemini(prompt, out)
            if out.exists():
                print(f"OK ({out.stat().st_size:,} байт)")
            else:
                print("FAIL — файл не создан")
        except Exception as e:
            print(f"FAIL — {e}")

    print("\n=== Готово ===")


# ---------------------------------------------------------------------------
# pytest-тесты (только при наличии ключа)
# ---------------------------------------------------------------------------

def pytest_configure(config):  # noqa: ARG001
    pass


try:
    import pytest

    @pytest.fixture(scope="module")
    def gemini_client():
        from app.core.config import settings
        if not settings.has_gemini:
            pytest.skip("GEMINI_API_KEY не задан")
        from google import genai as google_genai
        return google_genai.Client(api_key=settings.gemini_api_key)

    def test_list_image_models(gemini_client):
        """Хотя бы одна image-модель должна быть доступна."""
        found = [
            m for m in gemini_client.models.list()
            if "image" in m.name.lower() or "imagen" in m.name.lower()
        ]
        assert found, "Ни одной image-модели не найдено"

    def test_generate_image_gemini_service():
        """Сервисная функция генерирует файл."""
        from app.core.config import settings
        if not settings.has_gemini:
            pytest.skip("GEMINI_API_KEY не задан")
        from app.services import image_gen
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.png"
            image_gen.generate_image_gemini(
                "A wide shot of a calm lake at sunrise, golden light, cinematic", out
            )
            assert out.exists(), "Файл не создан"
            assert out.stat().st_size > 1000, "Файл слишком маленький"

except ImportError:
    pass  # pytest не установлен — только smoke-тест


if __name__ == "__main__":
    _run_smoke()
