"""Тесты моделей и каскадного удаления."""
from app.models.project import Project
from app.models.script import Script
from app.models.video import Video


def test_create_project_and_video(db):
    p = Project(name="Тест", niche="научпоп", language_primary="ru")
    db.add(p)
    db.commit()
    assert p.id and len(p.id) == 36
    assert p.created_at is not None

    v = Video(project_id=p.id, topic_brief="о чём-то", title="Заголовок")
    db.add(v)
    db.commit()
    assert v.status == "draft"
    assert v.project_id == p.id


def test_cascade_delete(db):
    p = Project(name="Каскад", language_primary="ru")
    db.add(p)
    db.commit()
    v = Video(project_id=p.id, topic_brief="t")
    db.add(v)
    db.commit()
    s = Script(video_id=v.id, language="ru", content_md="текст", is_primary=True)
    db.add(s)
    db.commit()

    db.delete(p)
    db.commit()
    assert db.query(Video).count() == 0
    assert db.query(Script).count() == 0
