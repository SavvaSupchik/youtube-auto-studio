"""Утилиты для работы с текстом сценариев."""
from __future__ import annotations

import re

# Средний темп начитки voice-over (слов в минуту). Используется для оценки длительности.
WORDS_PER_MINUTE = 140


def count_words(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def estimate_duration_sec(text: str) -> int:
    """Оценивает длительность озвучки по числу слов."""
    words = count_words(text)
    return int(words / WORDS_PER_MINUTE * 60)


def words_for_minutes(minutes: float) -> int:
    return int(minutes * WORDS_PER_MINUTE)
