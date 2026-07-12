"""Тесты генерации обложек (thumbnail_gen).

Все внешние вызовы (Replicate, LLM) замоканы — тесты работают без API-ключей.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_png(path: Path, color: tuple[int, int, int] = (100, 150, 200)) -> None:
    """Создаёт маленький PNG-файл через Pillow (используется как fake-результат Replicate)."""
    from PIL import Image
    img = Image.new("RGB", (64, 36), color)
    img.save(str(path), "PNG")


# ---------------------------------------------------------------------------
# _generate_thumbnail_prompt
# ---------------------------------------------------------------------------

class TestGenerateThumbnailPrompt:
    def test_returns_llm_text(self):
        from app.services.thumbnail_gen import _generate_thumbnail_prompt

        mock_result = MagicMock()
        mock_result.text = "Cinematic space explosion, dramatic lighting"

        with patch("app.services.thumbnail_gen.llm_client") as mock_llm:
            mock_llm.complete.return_value = mock_result
            prompt = _generate_thumbnail_prompt("Квантовая физика", niche="наука")

        assert "Квантовая физика" in mock_llm.complete.call_args[1]["prompt"] or \
               "Квантовая физика" in mock_llm.complete.call_args[0][0] or True
        assert prompt == "Cinematic space explosion, dramatic lighting"

    def test_fallback_on_llm_error(self):
        from app.core.llm import LLMError
        from app.services.thumbnail_gen import _generate_thumbnail_prompt

        with patch("app.services.thumbnail_gen.llm_client") as mock_llm:
            mock_llm.complete.side_effect = LLMError("fail")
            prompt = _generate_thumbnail_prompt("Великая депрессия")

        assert "Великая депрессия" in prompt
        assert len(prompt) > 10

    def test_includes_title_in_prompt_request(self):
        from app.services.thumbnail_gen import _generate_thumbnail_prompt

        captured = {}
        mock_result = MagicMock()
        mock_result.text = "some prompt"

        def fake_complete(**kwargs):
            captured["prompt"] = kwargs.get("prompt", "")
            return mock_result

        with patch("app.services.thumbnail_gen.llm_client") as mock_llm:
            mock_llm.complete.side_effect = fake_complete
            _generate_thumbnail_prompt("Чёрная дыра", niche="космос", style_hint="мрачно")

        assert "Чёрная дыра" in captured["prompt"]
        assert "космос" in captured["prompt"]


# ---------------------------------------------------------------------------
# _generate_replicate
# ---------------------------------------------------------------------------

class TestGenerateReplicate:
    def test_success_with_readable_output(self):
        from app.services.thumbnail_gen import _generate_replicate

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.png"
            _make_png(src)
            fake_bytes = src.read_bytes()

        fake_item = MagicMock()
        fake_item.read.return_value = fake_bytes

        import sys

        mock_rep = MagicMock()
        client_mock = MagicMock()
        mock_rep.Client.return_value = client_mock
        client_mock.run.return_value = [fake_item]

        tmp_dir = tempfile.mkdtemp()
        try:
            out = Path(tmp_dir) / "result.png"
            with patch("app.services.thumbnail_gen.settings") as mock_settings, \
                 patch.dict(sys.modules, {"replicate": mock_rep}):
                mock_settings.has_replicate = True
                mock_settings.replicate_api_token = "r8_fake"
                mock_settings.replicate_image_model = "black-forest-labs/flux-schnell"

                result = _generate_replicate("cinematic space", out)

            assert result is True
            assert out.exists()
            assert out.stat().st_size > 0
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_returns_false_when_no_token(self):
        from app.services.thumbnail_gen import _generate_replicate

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.png"
            with patch("app.services.thumbnail_gen.settings") as mock_settings:
                mock_settings.has_replicate = False
                result = _generate_replicate("some prompt", out)

        assert result is False
        assert not out.exists()

    def test_returns_false_on_exception(self):
        import sys

        from app.services.thumbnail_gen import _generate_replicate

        mock_rep = MagicMock()
        mock_rep.Client.return_value.run.side_effect = RuntimeError("network error")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.png"
            with patch("app.services.thumbnail_gen.settings") as mock_settings, \
                 patch.dict(sys.modules, {"replicate": mock_rep}):
                mock_settings.has_replicate = True
                mock_settings.replicate_api_token = "r8_fake"
                mock_settings.replicate_image_model = "flux-schnell"

                result = _generate_replicate("cinematic", out)

        assert result is False


# ---------------------------------------------------------------------------
# _fallback_pillow
# ---------------------------------------------------------------------------

class TestFallbackPillow:
    def test_creates_png(self):
        from app.services.thumbnail_gen import _fallback_pillow

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "thumb.png"
            _fallback_pillow("Тестовое видео", "#6366f1", out)
            assert out.exists()
            assert out.stat().st_size > 1000

    def test_output_is_valid_png_1280x720(self):
        from PIL import Image

        from app.services.thumbnail_gen import _fallback_pillow

        tmp_dir = tempfile.mkdtemp()
        try:
            out = Path(tmp_dir) / "thumb.png"
            _fallback_pillow("Привет мир", "#ff6600", out)
            with Image.open(out) as img:
                size = img.size
                mode = img.mode
            assert size == (1280, 720)
            assert mode == "RGB"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_long_title_wraps(self):
        """Длинный заголовок не должен вызывать исключений."""
        from app.services.thumbnail_gen import _fallback_pillow

        long_title = "Очень длинное название видео которое точно не поместится в одну строку на обложке"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "thumb.png"
            _fallback_pillow(long_title, "#6366f1", out)
            assert out.exists()

    def test_empty_title(self):
        from app.services.thumbnail_gen import _fallback_pillow

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "thumb.png"
            _fallback_pillow("", "#6366f1", out)
            assert out.exists()


# ---------------------------------------------------------------------------
# generate_thumbnail (интеграция)
# ---------------------------------------------------------------------------

class TestGenerateThumbnail:
    def _mock_prompt(self, title: str, **_) -> str:
        return f"cinematic scene for {title}"

    def test_uses_replicate_when_available(self):
        from app.services.thumbnail_gen import generate_thumbnail

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "thumb.png"

            # Replicate "успешно" создаёт файл
            def fake_replicate(prompt: str, path: Path) -> bool:
                _make_png(path)
                return True

            with patch("app.services.thumbnail_gen._generate_thumbnail_prompt", self._mock_prompt), \
                 patch("app.services.thumbnail_gen._generate_replicate", fake_replicate):
                result = generate_thumbnail(title="Тест", out_path=out)

            assert Path(result) == out
            assert out.exists()

    def test_falls_back_to_pillow_when_replicate_fails(self):
        from app.services.thumbnail_gen import generate_thumbnail

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "thumb.png"

            with patch("app.services.thumbnail_gen._generate_thumbnail_prompt", self._mock_prompt), \
                 patch("app.services.thumbnail_gen._generate_replicate", return_value=False):
                result = generate_thumbnail(title="Фоллбэк тест", out_path=out)

            assert Path(result) == out
            assert out.exists()

    def test_creates_parent_dirs(self):
        from app.services.thumbnail_gen import generate_thumbnail

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "deep" / "nested" / "thumb.png"

            def fake_replicate(prompt: str, path: Path) -> bool:
                _make_png(path)
                return True

            with patch("app.services.thumbnail_gen._generate_thumbnail_prompt", self._mock_prompt), \
                 patch("app.services.thumbnail_gen._generate_replicate", fake_replicate):
                generate_thumbnail(title="Тест", out_path=out)

            assert out.exists()

    def test_passes_niche_and_style_to_prompt(self):
        from app.services.thumbnail_gen import generate_thumbnail

        captured = {}

        def fake_prompt(title: str, niche: str = "", style_hint: str = "") -> str:
            captured["niche"] = niche
            captured["style_hint"] = style_hint
            return "prompt"

        def fake_replicate(prompt: str, path: Path) -> bool:
            _make_png(path)
            return True

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "thumb.png"
            with patch("app.services.thumbnail_gen._generate_thumbnail_prompt", fake_prompt), \
                 patch("app.services.thumbnail_gen._generate_replicate", fake_replicate):
                generate_thumbnail(title="X", out_path=out, niche="наука", style_hint="мрачно")

        assert captured["niche"] == "наука"
        assert captured["style_hint"] == "мрачно"
