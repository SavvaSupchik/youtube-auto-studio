"""Настройки приложения. Читаются из .env через pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень репозитория (на два уровня выше: backend/app/core -> backend -> root)
ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Глобальные настройки. Все значения переопределяются через .env."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Провайдер LLM для генерации/анализа/перевода: "claude" (платный, по умолчанию)
    # или "gemini" (есть бесплатный лимит) — см. core/llm.py
    llm_provider: str = Field(default="claude", alias="LLM_PROVIDER")

    # Claude
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    claude_model: str = Field(default="claude-sonnet-4-5", alias="CLAUDE_MODEL")
    claude_model_fast: str = Field(
        default="claude-haiku-4-5-20251001", alias="CLAUDE_MODEL_FAST"
    )

    # Gemini (бесплатный лимит на ключ — console.cloud.google.com / aistudio.google.com)
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    gemini_model_fast: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL_FAST")

    # YouTube Data API v3 (анализ ниш) — бесплатная квота 10 000 units/день.
    # Ключ: console.cloud.google.com -> APIs & Services -> Credentials.
    # ВНИМАНИЕ: search.list стоит 100 units за запрос, поэтому скан ниш
    # расходует квоту заметно (см. services/niche_analyzer.py).
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    # Регион по умолчанию для анализа (2-буквенный код ISO 3166-1): RU, US, ...
    youtube_region: str = Field(default="US", alias="YOUTUBE_REGION")
    # Язык релевантности выдачи по умолчанию (ISO 639-1): ru, en, ...
    youtube_language: str = Field(default="ru", alias="YOUTUBE_LANGUAGE")

    # Внешние сервисы
    pexels_api_key: str = Field(default="", alias="PEXELS_API_KEY")
    replicate_api_token: str = Field(default="", alias="REPLICATE_API_TOKEN")
    # Модель генерации картинок на Replicate (FLUX.2 [dev] — баланс цена/качество, ~$0.012/картинка)
    replicate_image_model: str = Field(
        default="black-forest-labs/flux-2-dev", alias="REPLICATE_IMAGE_MODEL"
    )
    # Визуальный ряд: картинка меняется каждые N минут видео
    visual_segment_minutes: float = Field(default=3.0, alias="VISUAL_SEGMENT_MINUTES")
    # Потолок на число картинок за видео (защита от случайного перерасхода)
    visual_max_images: int = Field(default=12, alias="VISUAL_MAX_IMAGES")
    # Генерировать каждую следующую картинку с опорой на первую (img2img) —
    # сильнее держит единый стиль/композицию. Требует модель с поддержкой
    # входного image (например, black-forest-labs/flux-dev). flux-schnell не
    # поддерживает — там этот режим автоматически откатывается на text-only.
    visual_use_reference: bool = Field(default=False, alias="VISUAL_USE_REFERENCE")
    # Насколько следовать новому промту (1.0) vs опорной картинке (ниже -> ближе к опоре)
    visual_reference_strength: float = Field(default=0.85, alias="VISUAL_REFERENCE_STRENGTH")
    # Апскейл картинок до Full HD+ после генерации (Replicate Real-ESRGAN, ~$0.002-0.004/шт)
    visual_upscale: bool = Field(default=True, alias="VISUAL_UPSCALE")
    replicate_upscale_model: str = Field(
        default="nightmareai/real-esrgan", alias="REPLICATE_UPSCALE_MODEL"
    )
    visual_upscale_factor: int = Field(default=2, alias="VISUAL_UPSCALE_FACTOR")

    # Пути
    data_dir: str = Field(default="./data", alias="DATA_DIR")
    db_path: str = Field(default="./data/db.sqlite", alias="DB_PATH")

    # Kokoro
    kokoro_model_path: str = Field(default="", alias="KOKORO_MODEL_PATH")
    kokoro_device: str = Field(default="cpu", alias="KOKORO_DEVICE")

    # Suno (неофициальный self-hosted API: https://github.com/gcui-art/suno-api)
    suno_api_url: str = Field(default="", alias="SUNO_API_URL")

    # FFmpeg
    ffmpeg_path: str = Field(default="ffmpeg", alias="FFMPEG_PATH")

    # Сервер
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    @property
    def data_path(self) -> Path:
        """Абсолютный путь к директории данных."""
        p = Path(self.data_dir)
        if not p.is_absolute():
            p = ROOT_DIR / p
        return p.resolve()

    @property
    def db_file(self) -> Path:
        """Абсолютный путь к файлу SQLite."""
        p = Path(self.db_path)
        if not p.is_absolute():
            p = ROOT_DIR / p
        return p.resolve()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_replicate(self) -> bool:
        return bool(self.replicate_api_token)

    @property
    def has_youtube(self) -> bool:
        return bool(self.youtube_api_key)

    @property
    def has_claude(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def llm_configured(self) -> bool:
        """Готов ли к работе тот провайдер, что выбран в LLM_PROVIDER."""
        return self.has_gemini if self.llm_provider == "gemini" else self.has_claude

    @property
    def model_default(self) -> str:
        return self.gemini_model if self.llm_provider == "gemini" else self.claude_model

    @property
    def model_fast(self) -> str:
        return self.gemini_model_fast if self.llm_provider == "gemini" else self.claude_model_fast


@lru_cache
def get_settings() -> Settings:
    """Кешированный экземпляр настроек."""
    return Settings()


settings = get_settings()
