"""Клиент LLM — Claude (Anthropic) или Gemini (Google), выбирается через LLM_PROVIDER в .env.

Единый интерфейс `LLMClient.complete()` используется всеми сервисами
(script_generator, script_analyzer, translator), поэтому переключение
провайдера не требует правок в остальном коде. Оба клиента:
- ленивая инициализация (не падают при импорте, если ключа нет)
- логируют токены и оценку стоимости каждого запроса
- превращают любую ошибку SDK в единый LLMError
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from loguru import logger

from app.core.config import settings

# Кол-во попыток и базовая пауза при временных ошибках Gemini (503/500/overloaded)
_GEMINI_RETRIES = 3
_GEMINI_RETRY_BASE_SEC = 2

# Приблизительные цены $/1M токенов для оценки стоимости (input, output).
# Используются только для статистики; не критичны. Для Gemini в пределах
# бесплатного лимита реальная стоимость = $0, эти числа — оценка "если бы
# платили" (полезно сравнить с Claude).
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.0),
}


@dataclass
class LLMResult:
    """Результат вызова LLM: текст + метрики."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMError(RuntimeError):
    """Ошибка работы с LLM (нет ключа, отказ, сетевой сбой)."""


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    # Берём цену по префиксу модели; если не нашли — 0.
    for key, (pin, pout) in _PRICING.items():
        if model.startswith(key):
            return input_tokens / 1_000_000 * pin + output_tokens / 1_000_000 * pout
    return 0.0


class LLMClient:
    """Тонкая обёртка над Anthropic SDK или Gemini SDK — выбор по settings.llm_provider."""

    def __init__(self) -> None:
        self._anthropic_client = None
        self._gemini_client = None

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 16000,
        stream: bool = True,
    ) -> LLMResult:
        """Один запрос к выбранному провайдеру. Возвращает текст и метрики."""
        if settings.llm_provider == "gemini":
            return self._complete_gemini(system=system, prompt=prompt, model=model, max_tokens=max_tokens)
        return self._complete_claude(
            system=system, prompt=prompt, model=model, max_tokens=max_tokens, stream=stream
        )

    # ---------------------------------------------------------------- Claude
    def _ensure_anthropic(self):
        if self._anthropic_client is None:
            if not settings.has_claude:
                raise LLMError(
                    "ANTHROPIC_API_KEY не задан. Укажите ключ в .env, "
                    "чтобы использовать генерацию через Claude."
                )
            try:
                import anthropic
            except ImportError as e:  # pragma: no cover
                raise LLMError(
                    "Пакет 'anthropic' не установлен. Выполните: pip install anthropic"
                ) from e
            self._anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._anthropic_client

    def _complete_claude(
        self, *, system: str, prompt: str, model: str | None, max_tokens: int, stream: bool
    ) -> LLMResult:
        client = self._ensure_anthropic()
        used_model = model or settings.model_default

        try:
            if stream:
                with client.messages.stream(
                    model=used_model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                ) as s:
                    message = s.get_final_message()
            else:
                message = client.messages.create(
                    model=used_model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
        except Exception as e:  # noqa: BLE001 — превращаем любую ошибку SDK в LLMError
            raise LLMError(f"Ошибка запроса к Claude ({used_model}): {e}") from e

        if message.stop_reason == "refusal":
            raise LLMError("Claude отказался отвечать (stop_reason=refusal).")

        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        usage = message.usage
        cost = _estimate_cost(used_model, usage.input_tokens, usage.output_tokens)
        logger.info(
            "Claude {model}: in={in_t} out={out_t} ~${cost:.4f}",
            model=used_model,
            in_t=usage.input_tokens,
            out_t=usage.output_tokens,
            cost=cost,
        )
        return LLMResult(
            text=text,
            model=used_model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost,
        )

    # ---------------------------------------------------------------- Gemini
    def _ensure_gemini(self):
        if not settings.has_gemini:
            raise LLMError(
                "GEMINI_API_KEY не задан. Укажите ключ в .env (или поставьте LLM_PROVIDER=claude), "
                "чтобы использовать генерацию через Gemini."
            )
        try:
            from google import genai
        except ImportError as e:  # pragma: no cover
            raise LLMError(
                "Пакет 'google-genai' не установлен. Выполните: pip install google-genai"
            ) from e
        if self._gemini_client is None:
            self._gemini_client = genai.Client(api_key=settings.gemini_api_key)
        return self._gemini_client

    def _complete_gemini(
        self, *, system: str, prompt: str, model: str | None, max_tokens: int
    ) -> LLMResult:
        client = self._ensure_gemini()
        used_model = model or settings.model_default

        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        )
        # Авто-повтор на временных сбоях Gemini (модель перегружена и т.п.).
        response = None
        for attempt in range(_GEMINI_RETRIES):
            try:
                response = client.models.generate_content(
                    model=used_model, contents=prompt, config=config
                )
                break
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                transient = any(
                    s in msg
                    for s in (
                        "503", "500", "UNAVAILABLE", "overloaded",
                        # сетевые обрывы (часто из-за нестабильного VPN)
                        "disconnected", "Connection", "connection", "timed out",
                        "timeout", "reset", "RemoteProtocol",
                        # региональная блокировка НЕ входит сюда — повтор не поможет
                    )
                )
                if transient and attempt < _GEMINI_RETRIES - 1:
                    pause = _GEMINI_RETRY_BASE_SEC * (attempt + 1)
                    logger.warning(
                        "Gemini {m}: временный сбой, повтор через {p}с ({a}/{n})",
                        m=used_model, p=pause, a=attempt + 1, n=_GEMINI_RETRIES,
                    )
                    time.sleep(pause)
                    continue
                raise LLMError(f"Ошибка запроса к Gemini ({used_model}): {e}") from e

        if not response.candidates:
            reason = getattr(response, "prompt_feedback", None)
            raise LLMError(f"Gemini не вернул ответ — заблокировано (причина: {reason}).")
        finish_reason = str(response.candidates[0].finish_reason)
        # STOP — нормальное завершение, MAX_TOKENS — тоже принимаем как успех
        if "STOP" not in finish_reason and "MAX_TOKENS" not in finish_reason:
            raise LLMError(f"Gemini остановил генерацию без результата (finish_reason={finish_reason}).")

        try:
            text = response.text
        except Exception as e:  # noqa: BLE001 — response.text бросает, если контент заблокирован
            raise LLMError(f"Gemini не вернул текст: {e}") from e
        if text is None:
            if "MAX_TOKENS" in finish_reason:
                raise LLMError(
                    f"Gemini ({used_model}) исчерпал лимит токенов на внутренние "
                    f"рассуждения (thinking) и не успел выдать текст — увеличьте "
                    f"max_tokens для этого запроса."
                )
            raise LLMError("Gemini вернул пустой ответ.")

        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        cost = _estimate_cost(used_model, input_tokens, output_tokens)
        logger.info(
            "Gemini {model}: in={in_t} out={out_t} ~${cost:.4f}",
            model=used_model,
            in_t=input_tokens,
            out_t=output_tokens,
            cost=cost,
        )
        return LLMResult(
            text=text,
            model=used_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )


# Единый экземпляр клиента на всё приложение
llm_client = LLMClient()
