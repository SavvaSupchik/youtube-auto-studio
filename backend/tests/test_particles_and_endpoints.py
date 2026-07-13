"""Тесты частиц (бесшовный луп, виды) и новых endpoint'ов видео:
субтитры .srt, YouTube-пакет, превью монтажа.
"""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine, init_db
from app.main import app
from app.models.project import Project
from app.models.script import Script
from app.models.script_analysis import ScriptAnalysis
from app.models.video import Video
from app.services import particle_gen


# ---------------------------------------------------------------------------
# Частицы
# ---------------------------------------------------------------------------

class TestParticles:
    def test_known_kinds(self):
        assert set(particle_gen._KINDS) == {"embers", "fireflies", "dust"}

    def test_all_frequencies_integer_for_seamless_loop(self):
        """Бесшовность лупа: все частоты — целое число циклов на луп."""
        import random
        for kind, cfg in particle_gen._KINDS.items():
            rng = random.Random(1)
            for _ in range(50):
                assert isinstance(rng.randint(*cfg["drift_cycles"]), int)
                assert isinstance(rng.randint(*cfg["sway_cycles"]), int)
                assert isinstance(rng.randint(*cfg["twinkle_cycles"]), int)

    def test_dust_is_dim_and_sinking(self):
        cfg = particle_gen._KINDS["dust"]
        assert cfg["brightness"][1] <= 0.55            # тусклые
        assert cfg["drift_cycles"][0] <= 0             # оседают вниз или висят
        assert cfg["twinkle_depth"] < 0.5              # почти не мерцают

    def test_generation_and_caching(self, monkeypatch, tmp_path):
        monkeypatch.setattr(particle_gen, "_N_FRAMES", 4)
        monkeypatch.setattr(particle_gen, "_SIZE", (64, 36))
        monkeypatch.setattr(particle_gen, "_particles_dir", lambda kind: tmp_path / kind)
        (tmp_path / "dust").mkdir(parents=True)

        out = particle_gen.ensure_particle_frames("dust")
        frames = sorted(out.glob("frame_*.png"))
        assert len(frames) == 4
        marker_mtime = (out / particle_gen._MARKER).stat().st_mtime

        # Повторный вызов — кеш, ничего не перегенерируется
        out2 = particle_gen.ensure_particle_frames("dust")
        assert out2 == out
        assert (out / particle_gen._MARKER).stat().st_mtime == marker_mtime

    def test_unknown_kind_falls_back_to_embers(self, monkeypatch, tmp_path):
        monkeypatch.setattr(particle_gen, "_N_FRAMES", 2)
        monkeypatch.setattr(particle_gen, "_SIZE", (64, 36))
        captured = {}

        def _dir(kind):
            captured["kind"] = kind
            d = tmp_path / kind
            d.mkdir(parents=True, exist_ok=True)
            return d

        monkeypatch.setattr(particle_gen, "_particles_dir", _dir)
        particle_gen.ensure_particle_frames("snowstorm")
        assert captured["kind"] == "embers"

    def test_loop_positions_match_at_wraparound(self):
        """Математика лупа: позиция частицы при t=0 и t=1 совпадает."""
        for freq in (1, 2, 3):
            for drift in (-1, 0, 1):
                y0 = 100.0
                h = 720
                y_start = (y0 - 0.0 * drift * h + math.sin(0.0 * 2 * math.pi * freq) * 30) % h
                y_end = (y0 - 1.0 * drift * h + math.sin(1.0 * 2 * math.pi * freq) * 30) % h
                assert abs(y_start - y_end) < 1e-6


# ---------------------------------------------------------------------------
# Новые endpoint'ы: субтитры, YouTube-пакет, превью
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    init_db()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def seeded(client):
    """Проект + видео + сценарий (+ анализ) в тестовой БД."""
    db = SessionLocal()
    project = Project(name="Тестовый канал", language_primary="ru")
    db.add(project)
    db.flush()
    video = Video(project_id=project.id, title="Тестовое видео", topic_brief="тема")
    db.add(video)
    db.flush()
    script = Script(
        video_id=video.id, language="ru", is_primary=True,
        content_md="# Заголовок\n\nПервое предложение. Второе предложение подлиннее из пяти слов! А третье?",
        word_count=12, duration_estimate_sec=60,
    )
    db.add(script)
    db.flush()
    analysis = ScriptAnalysis(
        script_id=script.id, hook="Крючок.", summary_short="Кратко.",
        summary_long="Длинное описание видео.", key_points=["тезис 1", "тезис 2"],
        topics=["история"], structure=["intro"], tone="спокойный",
        title_suggestions=["Заголовок А", "Заголовок Б"],
        youtube_tags=["история", "сон", "релакс"],
    )
    db.add(analysis)
    db.commit()
    ids = {"project": project.id, "video": video.id, "script": script.id}
    db.close()
    return ids


class TestSubtitles:
    def test_srt_format_and_timing(self, client, seeded):
        r = client.get(f"/api/videos/{seeded['video']}/subtitles/ru")
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        body = r.text
        blocks = [b for b in body.split("\n\n") if b.strip()]
        assert len(blocks) == 3  # 3 предложения (заголовок markdown выброшен)
        assert blocks[0].startswith("1\n00:00:00,000 --> ")
        assert "Заголовок" not in body  # markdown-заголовки — не речь
        # Времена возрастают, финал не превышает длительность
        last_line = blocks[-1].splitlines()[1]
        end = last_line.split(" --> ")[1]
        assert end <= "00:01:00,000"

    def test_missing_language_404(self, client, seeded):
        assert client.get(f"/api/videos/{seeded['video']}/subtitles/en").status_code == 404

    def test_fmt_srt_time(self):
        from app.api.videos import _fmt_srt_time
        assert _fmt_srt_time(0) == "00:00:00,000"
        assert _fmt_srt_time(3661.5) == "01:01:01,500"
        assert _fmt_srt_time(59.9999) == "00:01:00,000"


class TestYouTubePackage:
    def test_package_contents(self, client, seeded):
        r = client.get(f"/api/videos/{seeded['video']}/youtube-package")
        assert r.status_code == 200
        data = r.json()
        assert data["titles"] == ["Заголовок А", "Заголовок Б"]
        assert "Крючок." in data["description"]
        assert "• тезис 1" in data["description"]
        assert data["tags_string"] == "история, сон, релакс"

    def test_tags_capped_at_youtube_limit(self, client, seeded):
        db = SessionLocal()
        analysis = db.query(ScriptAnalysis).filter_by(script_id=seeded["script"]).one()
        analysis.youtube_tags = [f"очень-длинный-тег-номер-{i:03d}" for i in range(50)]
        db.commit()
        db.close()
        r = client.get(f"/api/videos/{seeded['video']}/youtube-package")
        assert len(r.json()["tags_string"]) <= 480

    def test_no_analysis_404(self, client, seeded):
        db = SessionLocal()
        db.query(ScriptAnalysis).delete()
        db.commit()
        db.close()
        r = client.get(f"/api/videos/{seeded['video']}/youtube-package")
        assert r.status_code == 404


class TestPreviewRender:
    def test_no_visuals_returns_400_with_hint(self, client, seeded):
        r = client.post(f"/api/videos/{seeded['video']}/preview-render")
        assert r.status_code == 400
        assert "визуальный ряд" in r.json()["detail"]

    def test_unknown_video_404(self, client):
        assert client.post("/api/videos/nope/preview-render").status_code == 404
