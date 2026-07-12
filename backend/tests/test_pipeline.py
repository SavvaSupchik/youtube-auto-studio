"""Тест пайплайна с замоканным Claude — проверяем сценарий → анализ → память."""
from unittest.mock import patch

from app.core.llm import LLMResult
from app.models.project import Project
from app.models.script import Script
from app.models.script_analysis import ScriptAnalysis
from app.models.video import Video
from app.services import memory_service
from app.services.pipeline import PipelineOptions, run_pipeline


def _fake_llm(text: str) -> LLMResult:
    return LLMResult(text=text, model="mock", input_tokens=10, output_tokens=20, cost_usd=0.001)


def test_pipeline_script_analysis_memory(db):
    p = Project(name="Пайплайн", language_primary="ru", languages_export=[])
    db.add(p)
    db.commit()
    v = Video(project_id=p.id, topic_brief="Почему небо голубое")
    db.add(v)
    db.commit()
    vid = v.id

    analysis_json = (
        '{"hook":"Эйнштейн удивился бы","summary_short":"про свет",'
        '"summary_long":"подробно про рассеяние","key_points":["Рэлей"],'
        '"topics":["физика","свет"],"structure":["intro","outro"],"tone":"образовательный"}'
    )

    def fake_complete(*, system, prompt, model=None, max_tokens=16000, stream=True):
        if "аналитик" in system.lower() or "JSON" in system:
            return _fake_llm(analysis_json)
        return _fake_llm("# Заголовок\nЭто сгенерированный сценарий про небо.")

    with patch("app.core.llm.llm_client.complete", side_effect=fake_complete):
        run_pipeline(vid, PipelineOptions(languages=["ru"], run_translate=False))

    # Сценарий сохранён
    script = db.query(Script).filter(Script.video_id == vid).one()
    assert "сценарий" in script.content_md
    assert script.is_primary is True

    # Анализ сохранён
    analysis = db.query(ScriptAnalysis).filter(ScriptAnalysis.script_id == script.id).one()
    assert analysis.hook == "Эйнштейн удивился бы"
    assert "физика" in analysis.topics

    # Память пополнена
    records = memory_service.read_memory(p.id, limit=10)
    assert any(r["video_id"] == vid for r in records)

    # Статус видео — ready
    db.refresh(v)
    assert v.status == "ready"


def test_pipeline_handles_llm_error(db):
    p = Project(name="Ошибка", language_primary="ru")
    db.add(p)
    db.commit()
    v = Video(project_id=p.id, topic_brief="тема")
    db.add(v)
    db.commit()
    vid = v.id

    from app.core.llm import LLMError

    with patch("app.core.llm.llm_client.complete", side_effect=LLMError("нет ключа")):
        run_pipeline(vid, PipelineOptions(languages=["ru"], run_translate=False))

    db.refresh(v)
    assert v.status == "error"
