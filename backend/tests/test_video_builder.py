"""Тесты сборки видео: параметры FFmpeg-команд без реального рендера.

FFmpeg не вызывается — _run_ffmpeg подменяется и команды перехватываются,
поэтому тесты проверяют ЛОГИКУ построения фильтров (зум в центр, панорама,
цветокор, tmix-сглаживание, кроссфейд), а не сам кодек.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import video_builder as vb


@pytest.fixture()
def fake_ffmpeg(monkeypatch, tmp_path):
    """Подменяет запуск FFmpeg, собирая все команды в список."""
    calls: list[list[str]] = []

    def _capture(cmd: list[str], step: str) -> None:
        calls.append(cmd)
        # создаём "выходной файл", чтобы последующие шаги его находили
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 2048)

    monkeypatch.setattr(vb, "_run_ffmpeg", _capture)
    monkeypatch.setattr(vb, "_ffmpeg_available", lambda: True)
    return calls


@pytest.fixture()
def imgs(tmp_path):
    """Три фиктивные картинки + фиктивное аудио."""
    paths = []
    for i in range(3):
        p = tmp_path / f"img_{i}.png"
        p.write_bytes(b"png")
        paths.append(p)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"wav")
    return paths, audio


def _vf_of(cmd: list[str]) -> str:
    """Достаёт видеофильтр из команды (-vf или -filter_complex)."""
    for flag in ("-vf", "-filter_complex"):
        if flag in cmd:
            return cmd[cmd.index(flag) + 1]
    return ""


# ---------------------------------------------------------------------------
# Сглаживание зума (tmix)
# ---------------------------------------------------------------------------

class TestZoomSmoothing:
    def test_slow_speed_max_window(self):
        assert vb._zoom_smoothing_frames(0.1) == 7
        assert vb._zoom_smoothing_frames(0.5) == 7

    def test_medium_speeds(self):
        assert vb._zoom_smoothing_frames(0.8) == 5
        assert vb._zoom_smoothing_frames(1.0) == 5
        assert vb._zoom_smoothing_frames(1.5) == 3
        assert vb._zoom_smoothing_frames(2.0) == 3

    def test_fast_speed_disables_smoothing(self):
        assert vb._zoom_smoothing_frames(2.1) == 0
        assert vb._zoom_smoothing_frames(5.0) == 0


# ---------------------------------------------------------------------------
# Один сегмент: фильтры zoompan
# ---------------------------------------------------------------------------

class TestKenBurnsSegment:
    def test_zoom_anchored_to_center(self, fake_ffmpeg, tmp_path):
        vb._ken_burns_segment(tmp_path / "a.png", 4.0, tmp_path / "o.mp4",
                              zoom_enabled=True, zoom_speed=1.0, zoom_direction="in")
        vf = _vf_of(fake_ffmpeg[0])
        assert "x='iw/2-(iw/zoom/2)'" in vf and "y='ih/2-(ih/zoom/2)'" in vf

    def test_pan_right_moves_x_forward(self, fake_ffmpeg, tmp_path):
        vb._ken_burns_segment(tmp_path / "a.png", 4.0, tmp_path / "o.mp4",
                              zoom_enabled=True, zoom_direction="pan_right")
        vf = _vf_of(fake_ffmpeg[0])
        assert f"z='{vb._PAN_ZOOM}'" in vf
        assert "(iw-iw/zoom)*((on-1)" in vf

    def test_pan_left_moves_x_backward(self, fake_ffmpeg, tmp_path):
        vb._ken_burns_segment(tmp_path / "a.png", 4.0, tmp_path / "o.mp4",
                              zoom_enabled=True, zoom_direction="pan_left")
        assert "(iw-iw/zoom)*(1-" in _vf_of(fake_ffmpeg[0])

    def test_grades(self, fake_ffmpeg, tmp_path):
        for grade, marker in [("warm", "colorbalance=rs=0.08"),
                              ("cold", "colorbalance=rs=-0.06"),
                              ("bw", "hue=s=0"),
                              ("vintage", "curves=preset=vintage")]:
            vb._ken_burns_segment(tmp_path / "a.png", 2.0, tmp_path / f"{grade}.mp4",
                                  zoom_enabled=False, grade=grade)
            assert marker in _vf_of(fake_ffmpeg[-1]), grade

    def test_grade_off_has_no_color_filters(self, fake_ffmpeg, tmp_path):
        vb._ken_burns_segment(tmp_path / "a.png", 2.0, tmp_path / "o.mp4",
                              zoom_enabled=False, grade="off")
        vf = _vf_of(fake_ffmpeg[0])
        assert "colorbalance" not in vf and "curves" not in vf and "hue" not in vf

    def test_slow_zoom_gets_tmix(self, fake_ffmpeg, tmp_path):
        vb._ken_burns_segment(tmp_path / "a.png", 4.0, tmp_path / "o.mp4",
                              zoom_enabled=True, zoom_speed=0.3, zoom_direction="in")
        assert "tmix=frames=7" in _vf_of(fake_ffmpeg[0])

    def test_fast_zoom_has_no_tmix(self, fake_ffmpeg, tmp_path):
        vb._ken_burns_segment(tmp_path / "a.png", 4.0, tmp_path / "o.mp4",
                              zoom_enabled=True, zoom_speed=5.0, zoom_direction="in")
        assert "tmix" not in _vf_of(fake_ffmpeg[0])

    def test_static_segment_low_fps(self, fake_ffmpeg, tmp_path):
        vb._ken_burns_segment(tmp_path / "a.png", 2.0, tmp_path / "o.mp4",
                              zoom_enabled=False)
        cmd = fake_ffmpeg[0]
        assert cmd[cmd.index("-r") + 1] == "2"

    def test_static_force_full_fps(self, fake_ffmpeg, tmp_path):
        vb._ken_burns_segment(tmp_path / "a.png", 2.0, tmp_path / "o.mp4",
                              zoom_enabled=False, force_full_fps=True)
        cmd = fake_ffmpeg[0]
        assert cmd[cmd.index("-r") + 1] == "25"

    def test_zoom_capped_by_canvas_reserve(self, fake_ffmpeg, tmp_path):
        # 60 сек на скорости 5%/с дали бы зум 4.0 — должен быть обрезан до 1.25
        vb._ken_burns_segment(tmp_path / "a.png", 60.0, tmp_path / "o.mp4",
                              zoom_enabled=True, zoom_speed=5.0, zoom_direction="in")
        assert f"{vb._ZOOM_CAP:.5f}" in _vf_of(fake_ffmpeg[0])

    def test_particles_blend_forced_to_rgb(self, fake_ffmpeg, tmp_path):
        # Регресс фиолетовой заливки: screen-blend обязан идти в RGB (gbrp)
        pdir = tmp_path / "particles"
        pdir.mkdir()
        vb._ken_burns_segment(tmp_path / "a.png", 2.0, tmp_path / "o.mp4",
                              zoom_enabled=False, particles_dir=pdir)
        vf = _vf_of(fake_ffmpeg[0])
        assert vf.count("format=gbrp") == 2
        assert "blend=all_mode=screen" in vf


# ---------------------------------------------------------------------------
# Сборка нескольких сегментов
# ---------------------------------------------------------------------------

class TestRenderSegments:
    def test_alternate_direction(self, fake_ffmpeg, imgs, tmp_path):
        images, audio = imgs
        vb.render_video_segments(
            images=[(p, 2.0) for p in images], audio_path=audio,
            out_path=tmp_path / "final.mp4", zoom="on", zoom_speed=1.0,
            zoom_direction="alternate",
        )
        seg_vfs = [_vf_of(c) for c in fake_ffmpeg[:3]]
        assert "min(zoom+" in seg_vfs[0]      # in
        assert "max(zoom-" in seg_vfs[1]      # out
        assert "min(zoom+" in seg_vfs[2]      # in

    def test_pan_alternates_sides(self, fake_ffmpeg, imgs, tmp_path):
        images, audio = imgs
        vb.render_video_segments(
            images=[(p, 2.0) for p in images], audio_path=audio,
            out_path=tmp_path / "final.mp4", zoom="on", zoom_direction="pan",
        )
        seg_vfs = [_vf_of(c) for c in fake_ffmpeg[:3]]
        assert "*((on-1)" in seg_vfs[0]       # pan_right
        assert "*(1-((on-1)" in seg_vfs[1]    # pan_left

    def test_legacy_warm_grade_false_maps_to_off(self, fake_ffmpeg, imgs, tmp_path):
        images, audio = imgs
        vb.render_video_segments(
            images=[(images[0], 2.0)], audio_path=audio,
            out_path=tmp_path / "final.mp4", zoom="off",
            warm_grade=False, grade=None,
        )
        assert "colorbalance" not in _vf_of(fake_ffmpeg[0])

    def test_explicit_grade_overrides_warm_flag(self, fake_ffmpeg, imgs, tmp_path):
        images, audio = imgs
        vb.render_video_segments(
            images=[(images[0], 2.0)], audio_path=audio,
            out_path=tmp_path / "final.mp4", zoom="off",
            warm_grade=True, grade="bw",
        )
        vf = _vf_of(fake_ffmpeg[0])
        assert "hue=s=0" in vf and "colorbalance" not in vf

    def test_xfade_chain_offsets_cumulative(self, fake_ffmpeg, imgs, tmp_path):
        images, audio = imgs
        vb.render_video_segments(
            images=[(images[0], 4.0), (images[1], 5.0), (images[2], 6.0)],
            audio_path=audio, out_path=tmp_path / "final.mp4",
            zoom="off", transition="fade",
        )
        # Ищем по содержимому фильтра, а не по всей команде: pytest-каталог
        # содержит имя теста (в нём есть слово "xfade") в путях файлов
        xfade_cmd = next(c for c in fake_ffmpeg if "xfade=" in _vf_of(c))
        fc = _vf_of(xfade_cmd)
        # offset первого перехода = длительность 1-го сегмента, второго = 4+5
        assert "offset=4.000" in fc and "offset=9.000" in fc

    def test_no_audio_renders_silent(self, fake_ffmpeg, imgs, tmp_path):
        images, _ = imgs
        vb.render_video_segments(
            images=[(images[0], 2.0)], audio_path=None,
            out_path=tmp_path / "final.mp4", zoom="off",
        )
        final_cmd = fake_ffmpeg[-1]
        assert "-an" in final_cmd
        assert "aac" not in final_cmd

    def test_missing_audio_raises(self, imgs, tmp_path, monkeypatch):
        monkeypatch.setattr(vb, "_ffmpeg_available", lambda: True)
        images, _ = imgs
        with pytest.raises(vb.RenderError, match="аудио"):
            vb.render_video_segments(
                images=[(images[0], 2.0)], audio_path=tmp_path / "nope.wav",
                out_path=tmp_path / "final.mp4",
            )

    def test_empty_images_raises(self, imgs, tmp_path, monkeypatch):
        monkeypatch.setattr(vb, "_ffmpeg_available", lambda: True)
        _, audio = imgs
        with pytest.raises(vb.RenderError):
            vb.render_video_segments(
                images=[], audio_path=audio, out_path=tmp_path / "final.mp4",
            )

    def test_fades_force_reencode(self, fake_ffmpeg, imgs, tmp_path):
        images, audio = imgs
        vb.render_video_segments(
            images=[(images[0], 10.0)], audio_path=audio,
            out_path=tmp_path / "final.mp4", zoom="off",
            fade_in=True, fade_out=True,
        )
        final_cmd = fake_ffmpeg[-1]
        vf = _vf_of(final_cmd)
        assert "fade=t=in" in vf and "fade=t=out:st=7.500" in vf
        assert "copy" not in final_cmd[final_cmd.index("-vf"):]
