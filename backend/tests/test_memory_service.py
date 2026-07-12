"""Тесты памяти канала (memory.jsonl)."""
from app.services import memory_service as ms


def test_append_and_read():
    pid = "proj-mem-1"
    ms.rewrite_memory(pid, [])
    for i in range(3):
        ms.append_memory(pid, {"video_id": f"v{i}", "title": f"Видео {i}", "topics": ["t"]})
    records = ms.read_memory(pid, limit=10)
    assert len(records) == 3
    assert records[-1]["title"] == "Видео 2"


def test_read_limit_returns_tail():
    pid = "proj-mem-2"
    ms.rewrite_memory(pid, [{"video_id": f"v{i}", "title": str(i)} for i in range(50)])
    records = ms.read_memory(pid, limit=10)
    assert len(records) == 10
    assert records[0]["title"] == "40"


def test_format_for_prompt_empty():
    text = ms.format_memory_for_prompt([])
    assert "первое видео" in text


def test_format_for_prompt_nonempty():
    text = ms.format_memory_for_prompt(
        [{"title": "T", "hook": "H", "summary_short": "S", "topics": ["a", "b"]}]
    )
    assert "hook: H" in text
    assert "a, b" in text
