"""Память канала: чтение/запись memory.jsonl со сжатыми саммари видео.

Ключевая фича — сценарии не должны повторяться. В промпт генерации передаются
только компактные саммари последних N видео, а не полные тексты.
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.core.paths import project_memory_file


def read_memory(project_id: str, limit: int = 40) -> list[dict[str, Any]]:
    """Возвращает последние `limit` записей памяти проекта (самые свежие в конце)."""
    path = project_memory_file(project_id)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Битая строка в memory.jsonl проекта {pid}", pid=project_id)
    return records[-limit:]


def append_memory(project_id: str, record: dict[str, Any]) -> None:
    """Дозаписывает одну запись в memory.jsonl (UTF-8, без BOM)."""
    path = project_memory_file(project_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def rewrite_memory(project_id: str, records: list[dict[str, Any]]) -> None:
    """Полностью перезаписывает memory.jsonl (например, после удаления записи)."""
    path = project_memory_file(project_id)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def format_memory_for_prompt(records: list[dict[str, Any]]) -> str:
    """Готовит компактный текст памяти для вставки в промпт генерации.

    Если памяти нет — возвращает явную пометку, чтобы модель это понимала.
    """
    if not records:
        return "(пока нет прошлых видео — это первое видео на канале)"
    lines: list[str] = []
    for rec in records:
        topics = ", ".join(rec.get("topics", []))
        points = "; ".join(rec.get("key_points", []))
        structure = " → ".join(rec.get("structure", []))
        lines.append(
            f"- [{rec.get('created_at', '')}] {rec.get('title', '')}\n"
            f"  hook: {rec.get('hook', '')}\n"
            f"  суть: {rec.get('summary_short', '')}\n"
            f"  темы: {topics}\n"
            f"  тезисы: {points}\n"
            f"  структура: {structure}"
        )
    return "\n".join(lines)
