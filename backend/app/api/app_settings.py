"""API глобальных настроек приложения (голоса по умолчанию и т.п.)."""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas.app_settings import AppSettingsOut, AppSettingsUpdate
from app.services import app_settings as svc

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=AppSettingsOut)
def get_settings():
    """Текущие глобальные настройки."""
    return svc.load()


@router.put("/settings", response_model=AppSettingsOut)
def update_settings(payload: AppSettingsUpdate):
    """Частично обновляет глобальные настройки."""
    patch = payload.model_dump(exclude_unset=True)
    # пустые voice_id убираем, чтобы не плодить мусор
    if "default_voices" in patch and patch["default_voices"] is not None:
        patch["default_voices"] = {k: v for k, v in patch["default_voices"].items() if v}
    return svc.save(patch)


@router.post("/settings/voice-params/reset", response_model=AppSettingsOut)
def reset_voice_params():
    """Сбрасывает параметры голоса к значениям по умолчанию."""
    return svc.save({"voice_params": dict(svc._DEFAULT_VOICE_PARAMS)})
