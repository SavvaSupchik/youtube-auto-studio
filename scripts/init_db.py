"""Создаёт таблицы БД вручную (без Alembic). Запуск: python scripts/init_db.py"""
import sys
from pathlib import Path

# чтобы импортировался пакет app из backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import init_db  # noqa: E402

if __name__ == "__main__":
    init_db()
    print("База данных инициализирована.")
