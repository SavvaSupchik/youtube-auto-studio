"""Общие фикстуры для тестов: изолированная БД в памяти и temp data dir."""
import os
import tempfile
from pathlib import Path

import pytest

# Настраиваем окружение ДО импорта app: временная папка данных и БД.
_TMP = tempfile.mkdtemp(prefix="yas_test_")
os.environ["DATA_DIR"] = _TMP
os.environ["DB_PATH"] = str(Path(_TMP) / "test.sqlite")
os.environ["ANTHROPIC_API_KEY"] = ""  # без реальных вызовов


@pytest.fixture()
def db():
    from app.core.database import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
