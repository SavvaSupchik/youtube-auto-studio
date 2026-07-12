"""Управление редактируемыми шаблонами 3-шаговой генерации сценария.

Шаблоны (на английском) задают логику каждого шага пайплайна:
- adapt          — мета-промт: переписывает шаблон шага под конкретную тему;
- stage1_prep    — подготовка/бриф;
- stage2_write   — написание сценария;
- stage3_humanize— аудит + авто-чистка (очеловечивание).

Дефолты лежат в app/prompts/chain/<name>.txt (часть репозитория).
Правки пользователя сохраняются отдельно в DATA_DIR/templates/<name>.txt и
имеют приоритет. Это позволяет редактировать шаблоны из UI (Настройки),
не теряя оригинал и не коммитя пользовательские правки.
"""
from __future__ import annotations

from pathlib import Path

from app.core import paths

# Каталог дефолтных шаблонов внутри пакета
_DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "chain"

# Порядок и человекочитаемые названия для UI
TEMPLATE_NAMES = ["stage1_prep", "stage2_write", "stage3_humanize", "adapt"]
TEMPLATE_TITLES = {
    "stage1_prep": "Шаг 1 — Подготовка (бриф)",
    "stage2_write": "Шаг 2 — Написание сценария",
    "stage3_humanize": "Шаг 3 — Аудит и очеловечивание",
    "adapt": "Адаптер промтов под тему (продвинутое)",
}


def _default_path(name: str) -> Path:
    return _DEFAULTS_DIR / f"{name}.txt"


def is_valid(name: str) -> bool:
    return name in TEMPLATE_NAMES


def default_text(name: str) -> str:
    return _default_path(name).read_text(encoding="utf-8")


def load(name: str) -> str:
    """Текст шаблона: пользовательский оверрайд, если есть, иначе дефолт."""
    override = paths.template_override_file(name)
    if override.exists():
        return override.read_text(encoding="utf-8")
    return default_text(name)


def is_overridden(name: str) -> bool:
    return paths.template_override_file(name).exists()


def save(name: str, content: str) -> None:
    """Сохраняет пользовательский оверрайд шаблона."""
    paths.template_override_file(name).write_text(content, encoding="utf-8")


def reset(name: str) -> None:
    """Удаляет пользовательский оверрайд — шаблон возвращается к дефолту."""
    override = paths.template_override_file(name)
    if override.exists():
        override.unlink()


def list_all() -> list[dict]:
    """Список всех шаблонов для UI: имя, заголовок, текст, признак правки."""
    return [
        {
            "name": name,
            "title": TEMPLATE_TITLES[name],
            "content": load(name),
            "overridden": is_overridden(name),
        }
        for name in TEMPLATE_NAMES
    ]
