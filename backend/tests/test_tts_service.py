"""Тесты озвучки: детект движка, сегментация, паузы, маршрутизация, пост-обработка.

Реальные движки (kokoro/edge) и ffmpeg не вызываются — подменяются, чтобы тесты
шли быстро и без сети/GPU. Проверяется логика сборки, а не качество звука.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.services import tts_service as t


class TestEngineDetect:
    def test_edge_by_neural_suffix(self):
        assert t._detect_engine("ru-RU-DmitryNeural") == "edge"
        assert t._detect_engine("en-US-BrianNeural") == "edge"

    def test_kokoro_default(self):
        assert t._detect_engine("af_heart") == "kokoro"
        assert t._detect_engine("") == "kokoro"


class TestMergeParams:
    def test_defaults_when_none(self):
        p = t._merge_params(None)
        assert p == t._DEFAULT_PARAMS
        assert p is not t._DEFAULT_PARAMS  # копия, не мутируем дефолт

    def test_partial_override(self):
        p = t._merge_params({"speed": 0.7})
        assert p["speed"] == 0.7
        assert p["paragraph_pause_ms"] == t._DEFAULT_PARAMS["paragraph_pause_ms"]

    def test_none_values_ignored(self):
        p = t._merge_params({"speed": None, "warmth": 0.9})
        assert p["speed"] == t._DEFAULT_PARAMS["speed"]
        assert p["warmth"] == 0.9


class TestSegmentText:
    def test_strips_markdown_headers_and_marks(self):
        segs = t._segment_text("# Заголовок\n\n**Жирный** текст.")
        joined = " ".join(s for s, _ in segs)
        assert "#" not in joined
        assert "*" not in joined
        assert "Жирный" in joined

    def test_paragraph_end_flags(self):
        segs = t._segment_text("Первое. Второе.\n\nТретье.")
        # Первое.(sent) Второе.(para-end) | Третье.(para-end)
        assert segs[0][1] is False
        assert segs[1][1] is True
        assert segs[-1][1] is True

    def test_single_line_splits_into_sentences(self):
        segs = t._segment_text("Раз. Два. Три.")
        assert len(segs) == 3

    def test_links_reduced_to_text(self):
        segs = t._segment_text("Смотри [тут](http://x.com) подробнее.")
        joined = " ".join(s for s, _ in segs)
        assert "http" not in joined
        assert "тут" in joined


class TestAssemble:
    def test_inserts_silence_gaps(self):
        a = np.ones(t._SR, dtype="float32")  # 1 c
        b = np.ones(t._SR, dtype="float32")
        out = t._assemble([a, b], [500, 0])  # 0.5 c паузы между
        expected = t._SR + int(t._SR * 0.5) + t._SR
        assert out.size == expected

    def test_no_gap_when_zero(self):
        a = np.ones(100, dtype="float32")
        out = t._assemble([a], [0])
        assert out.size == 100

    def test_empty(self):
        out = t._assemble([], [])
        assert out.size == 0


class TestSynthesizeRouting:
    """Проверяем маршрутизацию synthesize без реальных движков."""

    @pytest.fixture()
    def stub_engines(self, monkeypatch):
        calls = {}

        def fake_edge(segments, voice, speed, pitch):
            calls["edge"] = {"n": len(segments), "voice": voice, "speed": speed, "pitch": pitch}
            return [np.ones(t._SR // 4, dtype="float32") for _ in segments]

        def fake_kokoro(segments, voice, speed):
            calls["kokoro"] = {"n": len(segments), "voice": voice, "speed": speed}
            return [np.ones(t._SR // 4, dtype="float32") for _ in segments]

        def fake_post(raw, out, warmth):
            # имитируем ffmpeg: просто копируем raw -> out
            import shutil
            shutil.copyfile(raw, out)

        monkeypatch.setattr(t, "_edge_blocks", fake_edge)
        monkeypatch.setattr(t, "_kokoro_blocks", fake_kokoro)
        monkeypatch.setattr(t, "_post_process", fake_post)
        return calls

    def test_manual_mode_no_synthesis(self, stub_engines, tmp_path):
        res = t.synthesize(
            text="любой текст", language="ru", out_path=tmp_path / "a.wav",
            tts_mode="manual", voice_settings={},
        )
        assert res.engine == "manual"
        assert res.status == "pending_manual"
        assert "edge" not in stub_engines and "kokoro" not in stub_engines

    def test_edge_voice_routes_to_edge(self, stub_engines, tmp_path):
        out = tmp_path / "ru.wav"
        res = t.synthesize(
            text="Первое. Второе.", language="ru", out_path=out,
            tts_mode="local", voice_settings={"ru": "ru-RU-DmitryNeural"},
            voice_params={"speed": 0.9, "pitch": 2},
        )
        assert res.engine == "edge"
        assert res.voice_id == "ru-RU-DmitryNeural"
        assert stub_engines["edge"]["speed"] == 0.9
        assert stub_engines["edge"]["pitch"] == 2
        assert out.exists()
        assert out.stat().st_size > 0

    def test_kokoro_voice_routes_to_kokoro(self, stub_engines, tmp_path):
        res = t.synthesize(
            text="Hello. World.", language="en", out_path=tmp_path / "en.wav",
            tts_mode="local", voice_settings={"en": "af_heart"},
        )
        assert res.engine == "kokoro"
        assert "kokoro" in stub_engines

    def test_ru_default_is_edge(self, stub_engines, tmp_path):
        # без явного голоса русский должен уйти на Edge (нативный русский)
        res = t.synthesize(
            text="Текст.", language="ru", out_path=tmp_path / "ru.wav",
            tts_mode="local", voice_settings={},
        )
        assert res.engine == "edge"
        assert res.voice_id == t._DEFAULT_VOICES["ru"]

    def test_post_process_skipped_when_disabled(self, monkeypatch, stub_engines, tmp_path):
        called = {"post": False}

        def spy_post(raw, out, warmth):
            called["post"] = True
        monkeypatch.setattr(t, "_post_process", spy_post)

        t.synthesize(
            text="Текст.", language="ru", out_path=tmp_path / "ru.wav",
            tts_mode="local", voice_settings={"ru": "ru-RU-DmitryNeural"},
            voice_params={"post_process": False},
        )
        assert called["post"] is False

    def test_empty_text_raises(self, stub_engines, tmp_path):
        with pytest.raises(t.TTSError):
            t.synthesize(
                text="   ", language="ru", out_path=tmp_path / "ru.wav",
                tts_mode="local", voice_settings={"ru": "ru-RU-DmitryNeural"},
            )


class TestEdgeRateMapping:
    """Проверяем, что speed/pitch превращаются в строки формата Edge."""

    def test_rate_and_pitch_strings(self, monkeypatch):
        captured = {}

        class FakeComm:
            def __init__(self, text, voice, rate, pitch):
                captured["rate"] = rate
                captured["pitch"] = pitch

            async def save(self, dst):
                Path(dst).write_bytes(b"fake")

        import types as _types
        fake_edge = _types.SimpleNamespace(Communicate=FakeComm)
        monkeypatch.setitem(__import__("sys").modules, "edge_tts", fake_edge)
        # ffmpeg-декод подменяем: пишем крошечный wav, который soundfile прочитает
        import soundfile as sf

        def fake_run(cmd, **kw):
            # последний аргумент — путь wav; создаём короткий файл
            out = cmd[-1]
            sf.write(out, np.zeros(1200, dtype="float32"), t._SR)
            return _types.SimpleNamespace(returncode=0)
        monkeypatch.setattr(t.subprocess, "run", fake_run)

        t._edge_blocks([("Привет.", True)], "ru-RU-DmitryNeural", 0.9, 2)
        assert captured["rate"] == "-10%"   # (0.9-1.0)*100
        assert captured["pitch"] == "+24Hz"  # 2*12
