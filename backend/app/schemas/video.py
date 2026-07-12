"""Pydantic-схемы видео, сценариев, анализа, логов."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


# ---------- Video ----------
class VideoCreate(BaseModel):
    topic_brief: str = ""
    title: str = ""
    # Готовый сценарий на основном языке канала — если задан, генерация через
    # Claude для основного языка пропускается, текст сохраняется как есть
    # (дальше всё равно можно прогнать анализ/перевод/озвучку/рендер).
    script_content: str | None = None
    # Адаптированные промты 3-шаговой генерации {stage1, stage2, stage3}.
    # Если переданы (например, пользователь поправил их в форме) — пайплайн
    # использует их как есть и не вызывает шаг адаптации. Если пусто —
    # адаптация шаблонов под тему выполняется автоматически.
    script_prompts: dict[str, str] | None = None
    # Языки для генерации; если пусто — берутся из настроек канала
    languages: list[str] | None = None
    target_duration_min: int | None = None
    # Какие стадии запускать сразу (по умолчанию только сценарий + анализ)
    run_translate: bool = True
    run_tts: bool = False
    run_render: bool = False
    # AI-визуальный ряд (Replicate/FLUX) — картинка по контексту сценария,
    # меняется каждые несколько минут видео. Опционально и платно.
    run_visuals: bool = False

    @model_validator(mode="after")
    def _check_has_brief_or_script(self) -> "VideoCreate":
        if not self.topic_brief.strip() and not (self.script_content or "").strip():
            raise ValueError("Укажите тему видео (topic_brief) или вставьте готовый сценарий (script_content)")
        return self


class VideoUpdate(BaseModel):
    title: str | None = None
    topic_brief: str | None = None
    status: str | None = None


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    topic_brief: str
    status: str
    duration_sec: int | None
    voice_overrides: dict[str, str]
    script_prompts: dict[str, str]
    render_params: dict[str, object]
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class RenderParamsIn(BaseModel):
    resolution: str = "720p"     # "720p" | "1080p" | "1440p"
    zoom: str = "on"             # "off" | "on" (старые "subtle"/"normal"/"strong" тоже = включён)
    zoom_speed: float = Field(default=0.3, ge=0.05, le=5.0)  # % кадра в секунду
    zoom_direction: str = "in"   # "in" | "out" | "alternate" | "pan" (панорама)
    warm_grade: bool = True      # устаревшее; используйте grade
    grade: str | None = None     # "off"|"warm"|"cold"|"vintage"|"bw"; None = из warm_grade
    vignette: bool = False       # мягкое затемнение углов
    grain: bool = False          # лёгкое плёночное зерно
    overlay: str = "off"         # "off" | "fireflies" (светлячки) | "embers" (искры) | "dust" (пыль)
    transition: str = "none"     # "none" | "dip" (затемнение) | "fade" (кроссфейд)
    fade_in: bool = False        # появление из чёрного в начале
    fade_out: bool = False       # уход в чёрный в конце


class VoiceOverrideIn(BaseModel):
    # voice_id="" / null снимает override — дальше берётся голос канала
    voice_id: str | None = None


class VisualAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_path: str
    asset_metadata: dict

    @computed_field
    @property
    def version(self) -> int:
        return (self.asset_metadata or {}).get("version", 1)

    @computed_field
    @property
    def archived(self) -> bool:
        return bool((self.asset_metadata or {}).get("archived", False))


# ---------- Script / Analysis ----------
class ScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    language: str
    content_md: str
    word_count: int
    duration_estimate_sec: int
    is_primary: bool
    created_at: datetime


class ScriptUpdate(BaseModel):
    content_md: str = Field(min_length=1)


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    script_id: str
    hook: str
    summary_short: str
    summary_long: str
    key_points: list[str]
    topics: list[str]
    structure: list[str]
    tone: str
    title_suggestions: list[str] = Field(default_factory=list)
    youtube_tags: list[str] = Field(default_factory=list)


# ---------- Audio ----------
class AudioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    script_id: str
    file_path: str
    duration_sec: int
    voice_id: str
    engine: str
    status: str
    version: int = 1
    archived: bool = False


# ---------- Logs ----------
class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    stage: str
    model_used: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    duration_sec: float
    status: str
    error_message: str | None
    created_at: datetime
