"""Загрузка и форматирование текстовых шаблонов промптов из app/prompts/."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache
def _load(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def render(name: str, **kwargs: object) -> str:
    """Загружает шаблон <name>.txt и подставляет значения через str.format.

    В шаблонах одинарные {ph} — плейсхолдеры, двойные {{ }} — литеральные скобки.
    """
    return _load(name).format(**kwargs)
