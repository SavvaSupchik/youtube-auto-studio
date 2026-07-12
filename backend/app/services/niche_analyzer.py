"""Анализ ниш YouTube: поиск недосыщенных тем (спрос > предложения).

Идея: собрать по нише реальные метрики через YouTube Data API v3 и оценить,
насколько «спрос давит на слабое предложение». Главный сигнал —
Outlier Ratio: медианные просмотры топ-видео делим на медианные подписчики
их каналов. Если маленькие каналы стабильно собирают большие просмотры —
алгоритм вынужден показывать их за неимением крупных => ниша недосыщена.

Стоимость квоты (важно): search.list = 100 units, videos.list / channels.list
= по 1 unit. Дневная бесплатная квота 10 000 => ~90-100 поисков в день.
Поэтому:
- один probe ниши = 1 search + 1 videos + 1 channels ≈ 102 units;
- скан на 8 под-ниш ≈ 800 units;
- Google Trends дёргаем только в deep_dive (медленный и нестабильный).
"""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from loguru import logger

from app.core.config import settings
from app.core.llm import LLMError, llm_client
from app.services import prompts

_YT_BASE = "https://www.googleapis.com/youtube/v3"
_HTTP_TIMEOUT = 20.0


class NicheError(RuntimeError):
    """Ошибка анализа ниши (нет ключа, исчерпана квота, сетевой сбой)."""


# ---------------------------------------------------------------------------
# YouTube Data API — тонкие обёртки
# ---------------------------------------------------------------------------
def _yt_get(endpoint: str, params: dict) -> dict:
    """GET к YouTube Data API с ключом; понятные ошибки вместо голого 4xx."""
    if not settings.has_youtube:
        raise NicheError(
            "YOUTUBE_API_KEY не задан в .env. Получите бесплатный ключ: "
            "console.cloud.google.com → APIs & Services → Credentials, "
            "включите 'YouTube Data API v3'."
        )
    params = {**params, "key": settings.youtube_api_key}
    try:
        r = httpx.get(f"{_YT_BASE}/{endpoint}", params=params, timeout=_HTTP_TIMEOUT)
    except httpx.HTTPError as e:
        raise NicheError(f"Сетевая ошибка при запросе к YouTube API: {e}") from e

    if r.status_code == 403:
        # Чаще всего — исчерпана квота или ключ без нужного API/с ограничениями.
        detail = ""
        try:
            detail = r.json()["error"]["errors"][0].get("reason", "")
        except Exception:  # noqa: BLE001
            pass
        if detail == "quotaExceeded":
            raise NicheError(
                "Исчерпана дневная квота YouTube Data API (10 000 units). "
                "Подождите до сброса (полночь по тихоокеанскому времени) или "
                "используйте другой ключ."
            )
        raise NicheError(
            f"YouTube API отклонил запрос (403, {detail or 'forbidden'}). "
            "Проверьте, что ключ активен и 'YouTube Data API v3' включён."
        )
    if r.status_code != 200:
        raise NicheError(f"YouTube API вернул {r.status_code}: {r.text[:200]}")
    return r.json()


def _search(query: str, region: str, language: str, published_after: str | None,
            max_results: int = 25) -> dict:
    """search.list → id видео + приблизительное totalResults (proxy предложения)."""
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "relevance",
        "maxResults": min(max_results, 50),
        "regionCode": region,
        "relevanceLanguage": language,
    }
    if published_after:
        params["publishedAfter"] = published_after
    return _yt_get("search", params)


def _videos_stats(video_ids: list[str]) -> list[dict]:
    if not video_ids:
        return []
    data = _yt_get("videos", {
        "part": "statistics,snippet,contentDetails",
        "id": ",".join(video_ids[:50]),
    })
    return data.get("items", [])


def _channels_stats(channel_ids: list[str]) -> dict[str, dict]:
    uniq = list(dict.fromkeys(channel_ids))[:50]
    if not uniq:
        return {}
    data = _yt_get("channels", {"part": "statistics,snippet", "id": ",".join(uniq)})
    return {c["id"]: c for c in data.get("items", [])}


# ---------------------------------------------------------------------------
# Google Trends (опционально; pytrends нестабилен и не входит в requirements)
# ---------------------------------------------------------------------------
@dataclass
class TrendInfo:
    available: bool
    interest: int = 0          # средний интерес за период 0-100
    direction: str = "unknown"  # растёт / стабильно / падает
    rising: list[str] = field(default_factory=list)
    note: str = ""


def _google_trends(keyword: str, region: str) -> TrendInfo:
    """Динамика поискового интереса за 12 мес. Мягко деградирует при сбое."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return TrendInfo(available=False,
                         note="Google Trends отключён: pip install pytrends для динамики спроса.")
    try:
        py = TrendReq(hl="en-US", tz=0)
        geo = region if region and len(region) == 2 else ""
        py.build_payload([keyword], timeframe="today 12-m", geo=geo)
        df = py.interest_over_time()
        if df.empty:
            return TrendInfo(available=True, note="Google Trends не вернул данных по запросу.")
        series = df[keyword].tolist()
        interest = int(statistics.mean(series)) if series else 0
        first_half = statistics.mean(series[: len(series) // 2] or [0])
        second_half = statistics.mean(series[len(series) // 2:] or [0])
        if second_half > first_half * 1.15:
            direction = "растёт"
        elif second_half < first_half * 0.85:
            direction = "падает"
        else:
            direction = "стабильно"
        rising: list[str] = []
        try:
            related = py.related_queries().get(keyword, {})
            rdf = related.get("rising")
            if rdf is not None and not rdf.empty:
                rising = rdf["query"].head(5).tolist()
        except Exception:  # noqa: BLE001
            pass
        return TrendInfo(available=True, interest=interest, direction=direction, rising=rising)
    except Exception as e:  # noqa: BLE001 — pytrends часто ловит 429 от Google
        logger.warning("[niche] Google Trends недоступен для '{k}': {e}", k=keyword, e=e)
        return TrendInfo(available=False,
                         note="Google Trends временно недоступен (частая блокировка 429).")


# ---------------------------------------------------------------------------
# Метрики и скоринг
# ---------------------------------------------------------------------------
def _parse_iso8601_duration(dur: str) -> int:
    """PT#H#M#S → секунды (нужно, чтобы отсеять Shorts)."""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _log_score(value: float, at_100: float) -> float:
    """0-100 по логарифмической шкале: value == at_100 даёт ~100."""
    import math
    if value <= 0:
        return 0.0
    return _clamp(math.log10(value + 1) / math.log10(at_100 + 1) * 100)


@dataclass
class NicheMetrics:
    keyword: str
    sample_size: int
    total_results: int          # приблизительное число видео по запросу (предложение)
    median_views: int
    median_subs: int
    outlier_ratio: float
    share_recent_90d: float     # доля свежих видео в топе 0-1
    median_engagement: float    # (likes+comments)/views, 0-1
    top_channel_dominance: float  # доля просмотров у одного канала 0-1
    demand_score: float
    supply_score: float
    outlier_score: float
    freshness_score: float
    engagement_score: float
    opportunity_score: float


def _compute_metrics(keyword: str, videos: list[dict],
                     channels: dict[str, dict], total_results: int) -> NicheMetrics:
    now = datetime.now(timezone.utc)
    views: list[int] = []
    subs: list[int] = []
    engagements: list[float] = []
    recent = 0
    channel_views: dict[str, int] = {}
    counted = 0

    for v in videos:
        stats = v.get("statistics", {})
        details = v.get("contentDetails", {})
        # Отсекаем Shorts (< 70 c) — другой рынок, искажает метрики.
        if _parse_iso8601_duration(details.get("duration", "")) < 70:
            continue
        vc = int(stats.get("viewCount", 0) or 0)
        if vc <= 0:
            continue
        counted += 1
        views.append(vc)
        likes = int(stats.get("likeCount", 0) or 0)
        comments = int(stats.get("commentCount", 0) or 0)
        engagements.append((likes + comments) / vc)

        ch_id = v.get("snippet", {}).get("channelId", "")
        channel_views[ch_id] = channel_views.get(ch_id, 0) + vc
        ch = channels.get(ch_id, {})
        sc = ch.get("statistics", {})
        if not sc.get("hiddenSubscriberCount", False):
            subs.append(int(sc.get("subscriberCount", 0) or 0))

        published = v.get("snippet", {}).get("publishedAt", "")
        try:
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if now - pub_dt <= timedelta(days=90):
                recent += 1
        except ValueError:
            pass

    if counted == 0:
        # Ниша без «длинных» видео — вернём нули, чтобы не падать.
        return NicheMetrics(
            keyword=keyword, sample_size=0, total_results=total_results,
            median_views=0, median_subs=0, outlier_ratio=0.0, share_recent_90d=0.0,
            median_engagement=0.0, top_channel_dominance=0.0, demand_score=0.0,
            supply_score=0.0, outlier_score=0.0, freshness_score=0.0,
            engagement_score=0.0, opportunity_score=0.0,
        )

    median_views = int(statistics.median(views))
    median_subs = int(statistics.median(subs)) if subs else 0
    outlier_ratio = median_views / max(median_subs, 1)
    share_recent = recent / counted
    median_engagement = statistics.median(engagements) if engagements else 0.0
    total_views = sum(views)
    dominance = (max(channel_views.values()) / total_views) if total_views else 0.0

    # --- субоценки 0-100 ---
    # Спрос: медианные просмотры топ-видео (100к ≈ сильный сигнал).
    demand_score = _log_score(median_views, at_100=300_000)
    # Предложение (инверсия): мало конкурирующих видео = хорошо.
    # 200к+ результатов = насыщено; <2к = почти пусто.
    supply_score = _clamp(100 - _log_score(total_results, at_100=200_000))
    # Outlier: ratio 10+ = отличный сигнал недосыщенности.
    outlier_score = _clamp(outlier_ratio / 10 * 100)
    freshness_score = share_recent * 100
    # Вовлечённость: 5%+ (like+comment)/views — живая аудитория.
    engagement_score = _clamp(median_engagement / 0.05 * 100)
    # Штраф за монополию одного канала (вход закрыт).
    dominance_penalty = _clamp(dominance * 100)

    opportunity = (
        0.32 * outlier_score
        + 0.24 * demand_score
        + 0.20 * supply_score
        + 0.14 * freshness_score
        + 0.10 * engagement_score
        - 0.15 * dominance_penalty
    )

    return NicheMetrics(
        keyword=keyword, sample_size=counted, total_results=total_results,
        median_views=median_views, median_subs=median_subs,
        outlier_ratio=round(outlier_ratio, 2), share_recent_90d=round(share_recent, 2),
        median_engagement=round(median_engagement, 4),
        top_channel_dominance=round(dominance, 2),
        demand_score=round(demand_score, 1), supply_score=round(supply_score, 1),
        outlier_score=round(outlier_score, 1), freshness_score=round(freshness_score, 1),
        engagement_score=round(engagement_score, 1),
        opportunity_score=round(_clamp(opportunity), 1),
    )


def _probe_keyword(keyword: str, region: str, language: str,
                   sample: int = 20) -> NicheMetrics:
    """Один лёгкий замер ниши: search → videos → channels → метрики."""
    published_after = (datetime.now(timezone.utc) - timedelta(days=365)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    search = _search(keyword, region, language, published_after, max_results=sample)
    items = search.get("items", [])
    total_results = int(search.get("pageInfo", {}).get("totalResults", 0) or 0)
    video_ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
    videos = _videos_stats(video_ids)
    channel_ids = [v.get("snippet", {}).get("channelId", "") for v in videos]
    channels = _channels_stats(channel_ids)
    return _compute_metrics(keyword, videos, channels, total_results)


# ---------------------------------------------------------------------------
# LLM-помощники
# ---------------------------------------------------------------------------
def _extract_json(text: str):
    """Достаёт JSON из ответа LLM (снимает ```json-ограждения и лишний текст)."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Берём первый {...} или [...] блок.
        m = re.search(r"(\[.*\]|\{.*\})", cleaned, flags=re.DOTALL)
        if m:
            return json.loads(m.group(1))
        raise


def _expand_seed(seed: str, region: str, language: str, count: int) -> list[dict]:
    """LLM → список под-ниш (keyword + rationale) для проверки по данным."""
    system = prompts.render("niche_scan_system", region=region, language=language, count=count)
    try:
        res = llm_client.complete(
            system=system,
            prompt=f"Широкая тема: {seed}",
            model=settings.model_fast,
            max_tokens=2000,
            stream=False,
        )
        data = _extract_json(res.text)
        out = []
        for item in data[:count]:
            kw = (item.get("keyword") or "").strip()
            if kw:
                out.append({"keyword": kw, "rationale": (item.get("rationale") or "").strip()})
        return out
    except (LLMError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise NicheError(f"Не удалось получить список под-ниш от LLM: {e}") from e


# ---------------------------------------------------------------------------
# Публичный API сервиса
# ---------------------------------------------------------------------------
def scan(seed: str, region: str | None = None, language: str | None = None,
         max_niches: int = 8) -> dict:
    """Скан: LLM предлагает под-ниши → каждую замеряем по YouTube → ранжируем.

    Возвращает словарь, готовый к сохранению в NicheReport.payload.
    """
    region = (region or settings.youtube_region).upper()
    language = language or settings.youtube_language
    max_niches = max(1, min(max_niches, 12))  # защита от перерасхода квоты

    candidates = _expand_seed(seed, region, language, max_niches)
    logger.info("[niche] Скан '{s}': {n} под-ниш, регион {r}", s=seed, n=len(candidates), r=region)

    results: list[dict] = []
    for cand in candidates:
        kw = cand["keyword"]
        try:
            m = _probe_keyword(kw, region, language)
        except NicheError as e:
            # Квота/сеть — прерываем скан, но отдаём уже посчитанное.
            logger.warning("[niche] Прерван замер '{k}': {e}", k=kw, e=e)
            if "квот" in str(e).lower():
                results.append({"keyword": kw, "error": str(e)})
                break
            results.append({"keyword": kw, "error": str(e)})
            continue
        results.append({**_metrics_dict(m), "rationale": cand.get("rationale", "")})

    ranked = sorted(
        results,
        key=lambda r: r.get("opportunity_score", -1),
        reverse=True,
    )
    return {
        "seed": seed,
        "region": region,
        "language": language,
        "niches": ranked,
        "quota_note": f"Замерено под-ниш: {sum(1 for r in results if 'opportunity_score' in r)} "
                      f"(~{len(results) * 102} units квоты YouTube).",
    }


def deep_dive(keyword: str, region: str | None = None, language: str | None = None) -> dict:
    """Глубокий разбор одной ниши: метрики + топ-видео + тренд + вердикт LLM."""
    region = (region or settings.youtube_region).upper()
    language = language or settings.youtube_language

    published_after = (datetime.now(timezone.utc) - timedelta(days=365)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    search = _search(keyword, region, language, published_after, max_results=25)
    items = search.get("items", [])
    total_results = int(search.get("pageInfo", {}).get("totalResults", 0) or 0)
    video_ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
    videos = _videos_stats(video_ids)
    channels = _channels_stats([v.get("snippet", {}).get("channelId", "") for v in videos])
    metrics = _compute_metrics(keyword, videos, channels, total_results)

    top_videos = _top_videos(videos, channels)
    trend = _google_trends(keyword, region)

    verdict = _llm_verdict(keyword, metrics, trend)

    return {
        "keyword": keyword,
        "region": region,
        "language": language,
        "metrics": _metrics_dict(metrics),
        "top_videos": top_videos,
        "trend": {
            "available": trend.available,
            "interest": trend.interest,
            "direction": trend.direction,
            "rising": trend.rising,
            "note": trend.note,
        },
        "verdict": verdict,
    }


def _top_videos(videos: list[dict], channels: dict[str, dict], limit: int = 10) -> list[dict]:
    rows = []
    for v in videos:
        stats = v.get("statistics", {})
        snip = v.get("snippet", {})
        ch = channels.get(snip.get("channelId", ""), {})
        subs = int(ch.get("statistics", {}).get("subscriberCount", 0) or 0)
        views = int(stats.get("viewCount", 0) or 0)
        rows.append({
            "video_id": v.get("id", ""),
            "title": snip.get("title", ""),
            "channel": snip.get("channelTitle", ""),
            "channel_subs": subs,
            "views": views,
            "views_to_subs": round(views / max(subs, 1), 1),
            "published_at": snip.get("publishedAt", ""),
            "url": f"https://www.youtube.com/watch?v={v.get('id', '')}",
        })
    return sorted(rows, key=lambda r: r["views"], reverse=True)[:limit]


def _llm_verdict(keyword: str, m: NicheMetrics, trend: TrendInfo) -> dict:
    system = prompts._load("niche_verdict_system")  # без .format — фигурные скобки в примере JSON
    payload = {
        "keyword": keyword,
        "outlier_ratio": m.outlier_ratio,
        "median_views": m.median_views,
        "median_subs": m.median_subs,
        "total_results_supply": m.total_results,
        "demand_score": m.demand_score,
        "supply_score": m.supply_score,
        "freshness": m.share_recent_90d,
        "dominance": m.top_channel_dominance,
        "engagement": m.median_engagement,
        "opportunity_score": m.opportunity_score,
        "trend_direction": trend.direction if trend.available else "нет данных",
        "trend_interest": trend.interest if trend.available else None,
        "trend_rising": trend.rising,
    }
    try:
        res = llm_client.complete(
            system=system,
            prompt="Метрики ниши (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2),
            model=settings.model_fast,
            max_tokens=2000,
            stream=False,
        )
        return _extract_json(res.text)
    except (LLMError, json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("[niche] Вердикт LLM недоступен: {e}", e=e)
        return {
            "verdict": "нет данных",
            "one_liner": "Автоматический вердикт недоступен — ориентируйтесь на метрики.",
            "reasoning": str(e),
            "content_angles": [],
            "recommended_formats": [],
            "risks": [],
        }


def _metrics_dict(m: NicheMetrics) -> dict:
    return {
        "keyword": m.keyword,
        "sample_size": m.sample_size,
        "total_results": m.total_results,
        "median_views": m.median_views,
        "median_subs": m.median_subs,
        "outlier_ratio": m.outlier_ratio,
        "share_recent_90d": m.share_recent_90d,
        "median_engagement": m.median_engagement,
        "top_channel_dominance": m.top_channel_dominance,
        "demand_score": m.demand_score,
        "supply_score": m.supply_score,
        "outlier_score": m.outlier_score,
        "freshness_score": m.freshness_score,
        "engagement_score": m.engagement_score,
        "opportunity_score": m.opportunity_score,
    }
