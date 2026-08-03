import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, Copy, Download, FolderOpen, Loader2, RefreshCw, Trash2, Upload, X } from "lucide-react";
import { api, fileUrl, srtUrl } from "../lib/api";
import { fmtDuration } from "../lib/format";
import { StatusBadge } from "../components/StatusBadge";
import { useJobSocket } from "../lib/useJobSocket";
import { PipelineLog } from "../components/PipelineLog";
import type { AudioTrack, GenLog, MusicTrack, RenderParams, Script, ThumbnailEntry, Voice, VisualAsset } from "../lib/types";

export default function VideoView() {
  const { videoId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  // retrying нужен ДО запроса logs (используется в refetchInterval)
  const [retrying, setRetrying] = useState(false);
  // Время последнего запуска retry — не сбрасываем retrying сразу, даём 4с
  // на то чтобы фоновый таск успел создать "running"-лог в БД
  const retryStartedAt = useRef<number>(0);

  const { data: video } = useQuery({
    queryKey: ["video", videoId],
    queryFn: () => api.getVideo(videoId),
    refetchInterval: (q) =>
      q.state.data?.status === "generating" ? 2000 : false,
  });
  const { data: scripts } = useQuery({
    queryKey: ["scripts", videoId],
    queryFn: () => api.scripts(videoId),
  });
  const { data: audio } = useQuery({
    queryKey: ["audio", videoId],
    queryFn: () => api.audio(videoId),
  });
  const { data: analysis } = useQuery({
    queryKey: ["analysis", videoId],
    queryFn: () => api.analysis(videoId),
    retry: false,
  });
  const { data: visuals } = useQuery({
    queryKey: ["visuals", videoId],
    queryFn: () => api.visuals(videoId),
  });
  const { data: logs } = useQuery({
    queryKey: ["logs", videoId],
    queryFn: () => api.logs(videoId),
    // Обновляем каждые 2с и во время генерации, и во время повторного запуска стадии
    refetchInterval: (video?.status === "generating" || retrying) ? 2000 : false,
  });
  const { data: project } = useQuery({
    queryKey: ["project", video?.project_id],
    queryFn: () => api.getProject(video!.project_id),
    enabled: !!video,
  });
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: () => api.listVoices() });

  const generating = video?.status === "generating";

  // Есть ли активная (running) стадия в БД — источник истины,
  // не зависит от WS-соединения и не застревает после его разрыва.
  const hasRunningStage = (logs ?? []).some((l) => l.status === "running");
  const runningStages = new Set((logs ?? []).filter((l) => l.status === "running").map((l) => l.stage));
  const isStageRunning = (stage: string) => runningStages.has(stage);
  // retrying нужен только чтобы держать WS открытым и опрашивать логи после POST на stage
  const activeStage = generating || retrying || hasRunningStage;

  const { events, done } = useJobSocket(videoId, activeStage);
  useEffect(() => {
    if (done) {
      qc.invalidateQueries({ queryKey: ["video", videoId] });
      qc.invalidateQueries({ queryKey: ["scripts", videoId] });
      qc.invalidateQueries({ queryKey: ["analysis", videoId] });
      qc.invalidateQueries({ queryKey: ["audio", videoId] });
      qc.invalidateQueries({ queryKey: ["visuals", videoId] });
      qc.invalidateQueries({ queryKey: ["logs", videoId] });
      setRetrying(false);
      setThumbTs(Date.now());
    }
  }, [done, qc, videoId]);

  // Сбрасываем retrying когда DB-логи подтверждают завершение.
  // Ждём минимум 4с после старта — фоновый таск не сразу пишет "running"-лог,
  // иначе retrying сбросится до того как лог появится в БД.
  useEffect(() => {
    if (retrying && logs && logs.length > 0 && !hasRunningStage) {
      const elapsed = Date.now() - retryStartedAt.current;
      if (elapsed > 4000) setRetrying(false);
    }
  }, [retrying, logs, hasRunningStage]);

  const retryStage = useMutation({
    mutationFn: (vars: { stage: string; lang?: string; visualEngine?: string }) =>
      api.rerunStage(videoId, vars.stage, vars.lang, vars.visualEngine),
    onSuccess: () => {
      retryStartedAt.current = Date.now();
      setRetrying(true);
      // Немедленно обновляем логи — иначе 2 секунды показывает старый stuck-таймер
      qc.invalidateQueries({ queryKey: ["logs", videoId] });
    },
  });
  const cancelPipeline = useMutation({
    mutationFn: () => api.cancelPipeline(videoId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["logs", videoId] });
      qc.invalidateQueries({ queryKey: ["video", videoId] });
      setRetrying(false);
    },
    onError: (e) => alert(`Ошибка отмены: ${e.message}`),
  });
  const uploadAudio = useMutation({
    mutationFn: (vars: { lang: string; file: File }) =>
      api.uploadAudio(videoId, vars.lang, vars.file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["audio", videoId] });
      qc.invalidateQueries({ queryKey: ["logs", videoId] });
    },
  });
  const setVoiceOverride = useMutation({
    mutationFn: (vars: { lang: string; voiceId: string | null }) =>
      api.setVoiceOverride(videoId, vars.lang, vars.voiceId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video", videoId] }),
  });

  const langs = useMemo(() => {
    const ls = (scripts ?? []).map((s) => s.language);
    const primary = (scripts ?? []).find((s) => s.is_primary)?.language;
    return primary ? [primary, ...ls.filter((l) => l !== primary)] : ls;
  }, [scripts]);
  const [activeLang, setActiveLang] = useState<string | null>(null);
  const lang = activeLang ?? langs[0] ?? null;
  const [thumbTs, setThumbTs] = useState(() => Date.now());

  const del = useMutation({
    mutationFn: () => api.deleteVideo(videoId),
    onSuccess: () => navigate(-1),
  });
  const rerun = useMutation({
    mutationFn: () =>
      api.rerun(videoId, {
        topic_brief: video!.topic_brief,
        run_translate: true,
        run_tts: false,
        run_render: false,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video", videoId] }),
  });

  if (!video) return <div className="p-6 text-muted">Загрузка…</div>;

  const currentScript = scripts?.find((s) => s.language === lang) ?? null;
  const currentAudio =
    currentScript && audio
      ? audio.find((a) => a.script_id === currentScript.id) ?? null
      : null;
  const finalAsset = null; // финальное видео раздаётся по пути; ссылку строим из языка

  return (
    <div className="mx-auto max-w-6xl p-6">
      <div className="mb-4 flex items-center gap-3">
        <h1 className="flex-1 truncate text-2xl font-bold">{video.title || video.topic_brief}</h1>
        <StatusBadge status={video.status} />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[260px_1fr_240px]">
        {/* Левая колонка */}
        <div className="space-y-3">
          <a
            href={fileUrl(`/projects/${video.project_id}/videos/${video.id}/thumbnail.png`) + `?t=${thumbTs}`}
            target="_blank"
            rel="noreferrer"
            className="group relative block aspect-video overflow-hidden rounded-lg border border-border bg-surface2"
            title="Открыть в полном размере"
          >
            <img
              src={fileUrl(`/projects/${video.project_id}/videos/${video.id}/thumbnail.png`) + `?t=${thumbTs}`}
              alt="thumbnail"
              className="h-full w-full object-cover"
              onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
            />
            <span className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
              <span className="rounded-lg bg-black/70 px-3 py-1.5 text-sm text-white">↗ Открыть</span>
            </span>
          </a>
          <div className="card space-y-2 text-sm">
            <Row label="Длительность" value={fmtDuration(video.duration_sec)} />
            <Row label="Языки" value={langs.map((l) => l.toUpperCase()).join(", ") || "—"} />
            <Row label="Тема" value={video.topic_brief} />
          </div>
          <button
            className="btn-ghost w-full"
            disabled={generating || rerun.isPending}
            onClick={() => rerun.mutate()}
          >
            <RefreshCw size={16} /> Перегенерировать сценарий
          </button>
          <button
            className="btn-ghost w-full"
            disabled={retryStage.isPending || isStageRunning("thumbnail")}
            onClick={() => retryStage.mutate({ stage: "thumbnail" })}
          >
            <RefreshCw size={16} /> {isStageRunning("thumbnail") ? "Генерируем обложку…" : "Перегенерировать обложку"}
          </button>
          <ThumbnailHistory videoId={videoId} projectId={video.project_id} onRestore={() => setThumbTs(Date.now())} />
          <MusicSelector videoId={videoId} />
          <button
            className="btn-ghost w-full"
            onClick={() => api.openVideoFolder(videoId).catch((e) => alert(e.message))}
            title="Открыть папку со сценариями, аудио и финальными mp4 в проводнике"
          >
            <FolderOpen size={16} /> Открыть папку
          </button>
          <button
            className="btn-ghost w-full text-red-400"
            onClick={() => confirm("Удалить видео?") && del.mutate()}
          >
            <Trash2 size={16} /> Удалить
          </button>
        </div>

        {/* Центр */}
        <div>
          <div className="mb-3 flex gap-1 border-b border-border">
            {langs.map((l) => (
              <button
                key={l}
                onClick={() => setActiveLang(l)}
                className={`-mb-px border-b-2 px-4 py-2 text-sm ${
                  l === lang
                    ? "border-indigo-500 text-white"
                    : "border-transparent text-muted hover:text-gray-200"
                }`}
              >
                {l.toUpperCase()}
              </button>
            ))}
            {langs.length === 0 && <span className="px-2 py-2 text-sm text-muted">Сценариев нет</span>}
          </div>

          <VisualsSection
            videoId={videoId}
            visuals={visuals}
            logs={logs}
            onRetry={(model) => retryStage.mutate({ stage: "visuals", visualEngine: model })}
            onCancel={() => cancelPipeline.mutate()}
            retryPending={retryStage.isPending || isStageRunning("visuals")}
          />

          {currentScript && lang && (
            <LangContent
              videoId={videoId}
              projectId={video.project_id}
              lang={lang}
              isPrimary={currentScript.is_primary}
              script={currentScript}
              audio={currentAudio}
              logs={logs}
              onRetryStage={(stage) => retryStage.mutate({ stage, lang })}
              isStageRunning={isStageRunning}
              retryPending={retryStage.isPending}
              onUploadAudio={(file) => uploadAudio.mutate({ lang, file })}
              uploadPending={uploadAudio.isPending}
              voices={voices}
              channelVoiceId={project?.voice_settings[lang]}
              overrideVoiceId={video.voice_overrides[lang]}
              onSetVoiceOverride={(voiceId) => setVoiceOverride.mutate({ lang, voiceId })}
              voiceOverridePending={setVoiceOverride.isPending}
              renderParams={video.render_params}
            />
          )}

          <div className="card mt-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium">Анализ</h3>
              <button
                className="btn-ghost px-2 py-1 text-xs"
                disabled={retryStage.isPending || isStageRunning("analysis")}
                onClick={() => retryStage.mutate({ stage: "analysis" })}
              >
                <RefreshCw size={13} /> {analysis ? "Переанализировать" : "Запустить анализ"}
              </button>
            </div>
            {analysis && (
              <div className="space-y-2 text-sm">
                <div>
                  <span className="text-muted">Хук: </span>
                  <span className="italic">«{analysis.hook}»</span>
                </div>
                <div>
                  <span className="text-muted">Суть: </span>
                  {analysis.summary_short}
                </div>
                <div className="text-gray-300">{analysis.summary_long}</div>
                <div>
                  <span className="text-muted">Тезисы:</span>
                  <ul className="ml-4 list-disc">
                    {analysis.key_points.map((p, i) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {analysis.topics.map((t) => (
                    <span
                      key={t}
                      className="rounded bg-indigo-600/20 px-1.5 py-0.5 text-xs text-indigo-300"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Названия и теги */}
          {analysis && (analysis.title_suggestions?.length > 0 || analysis.youtube_tags?.length > 0) && (
            <div className="card mt-4 space-y-4">
              {analysis.title_suggestions?.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-medium">Варианты названия</h3>
                  <div className="space-y-1.5">
                    {analysis.title_suggestions.map((title, i) => (
                      <TitleOption key={i} title={title} />
                    ))}
                  </div>
                </div>
              )}
              {analysis.youtube_tags?.length > 0 && (
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <h3 className="text-sm font-medium">Теги YouTube</h3>
                    <button
                      className="btn-ghost px-2 py-0.5 text-xs"
                      onClick={() => {
                        navigator.clipboard.writeText(analysis.youtube_tags.join(", "));
                      }}
                    >
                      Копировать все
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {analysis.youtube_tags.map((tag) => (
                      <span
                        key={tag}
                        className="cursor-pointer rounded bg-white/5 px-2 py-0.5 text-xs text-muted transition-colors hover:bg-white/10 hover:text-gray-200"
                        onClick={() => navigator.clipboard.writeText(tag)}
                        title="Нажмите чтобы скопировать"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Правая колонка — лог */}
        <div className="space-y-3">
          <PipelineLog logs={logs} events={events} done={done} />
          {hasRunningStage && (
            <button
              className="btn-ghost w-full text-red-400 hover:text-red-300"
              disabled={cancelPipeline.isPending}
              onClick={() => cancelPipeline.mutate()}
            >
              {cancelPipeline.isPending
                ? <><Loader2 size={14} className="animate-spin" /> Останавливаем…</>
                : <><X size={14} /> Остановить генерацию</>
              }
            </button>
          )}
          {logs && logs.some((l) => l.cost_usd) && (
            <div className="card text-xs text-muted">
              Стоимость: $
              {logs.reduce((s, l) => s + (l.cost_usd ?? 0), 0).toFixed(4)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function VisualsGrid({
  items,
  onOpen,
}: {
  items: VisualAsset[];
  onOpen: (i: number) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
      {items.map((v, i) => (
        <button
          key={v.id}
          type="button"
          onClick={() => onOpen(i)}
          className="group relative aspect-video cursor-zoom-in overflow-hidden rounded-md bg-surface2"
          title="Открыть"
        >
          <img
            src={fileUrl(v.file_path)}
            alt={v.asset_metadata.prompt}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        </button>
      ))}
    </div>
  );
}

function VisualsSection({
  videoId,
  visuals,
  logs,
  onRetry,
  onCancel,
  retryPending,
}: {
  videoId: string;
  visuals?: VisualAsset[];
  logs?: GenLog[];
  onRetry: (model?: string) => void;
  onCancel: () => void;
  retryPending: boolean;
}) {
  const qc = useQueryClient();
  const visualsError = logs?.find((l) => l.stage === "visuals" && l.status === "error");
  const hasVisuals = (visuals ?? []).length > 0;
  const [showPlaylist, setShowPlaylist] = useState(false);
  const [selectedModel, setSelectedModel] = useState("");

  const { data: imageModels } = useQuery({
    queryKey: ["image-models"],
    queryFn: () => api.imageModels(),
    staleTime: Infinity,
  });

  // lightbox: { ver, index } — привязан к конкретной версии
  const [lightbox, setLightbox] = useState<{ ver: number; index: number } | null>(null);

  // Фетчим всегда когда есть хоть один visuals, чтобы видеть вкладки версий
  const { data: history } = useQuery({
    queryKey: ["visuals-history", videoId],
    queryFn: () => api.visualsHistory(videoId),
    enabled: hasVisuals,
  });

  const activateMutation = useMutation({
    mutationFn: (version: number) => api.activateVisualsVersion(videoId, version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["visuals", videoId] });
      qc.invalidateQueries({ queryKey: ["visuals-history", videoId] });
    },
  });

  // Группируем историю по версии, сортируем по убыванию (новейшая первая)
  const versions = useMemo(() => {
    if (!history) return [];
    const map = new Map<number, VisualAsset[]>();
    for (const a of history) {
      const v = a.asset_metadata?.version ?? 1;
      if (!map.has(v)) map.set(v, []);
      map.get(v)!.push(a);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => b - a)
      .map(([ver, assets]) => ({
        ver,
        assets: assets.sort((x, y) => (x.asset_metadata?.index ?? 0) - (y.asset_metadata?.index ?? 0)),
        archived: assets[0]?.asset_metadata?.archived ?? false,
      }));
  }, [history]);

  // Активная вкладка = активная версия (не archived), если нет — первая
  const activeVer = versions.find((v) => !v.archived)?.ver ?? versions[0]?.ver ?? null;
  const [selectedVer, setSelectedVer] = useState<number | null>(null);
  const currentVer = selectedVer ?? activeVer;
  const currentAssets = versions.find((v) => v.ver === currentVer)?.assets ?? (visuals ?? []);
  const style = currentAssets[0]?.asset_metadata?.style as string | undefined;
  const isSelectedActive = versions.find((v) => v.ver === currentVer)?.archived === false;
  const hasMultipleVersions = versions.length > 1;

  const openLightbox = (ver: number, index: number) => setLightbox({ ver, index });
  const lightboxAssets = lightbox ? (versions.find((v) => v.ver === lightbox.ver)?.assets ?? []) : [];

  return (
    <div className="card mb-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium">
          Визуальный ряд (AI){hasVisuals ? ` · ${currentAssets.length} картинок` : ""}
        </h3>
        <div className="flex items-center gap-2">
          {retryPending && (
            <button
              className="btn-ghost px-2 py-1 text-xs text-red-400"
              onClick={onCancel}
            >
              Отменить
            </button>
          )}
          {hasVisuals && (
            <button
              className={`btn-ghost px-2 py-1 text-xs ${showPlaylist ? "bg-white/10" : ""}`}
              onClick={() => setShowPlaylist((v) => !v)}
            >
              Редактор ряда
            </button>
          )}
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={retryPending}
            className="rounded border border-white/10 bg-surface2 px-1.5 py-1 text-xs text-muted"
            title="Модель для генерации картинок"
          >
            <option value="">По умолчанию (FLUX.2 [dev])</option>
            {(imageModels ?? []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
          <button
            className="btn-ghost px-2 py-1 text-xs"
            disabled={retryPending}
            onClick={() => onRetry(selectedModel || undefined)}
          >
            <RefreshCw size={13} /> {hasVisuals ? "Перегенерировать" : "Сгенерировать"}
          </button>
        </div>
      </div>

      {showPlaylist && <PlaylistEditor videoId={videoId} />}

      {/* Вкладки версий — показываем только если версий больше одной */}
      {hasMultipleVersions && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {versions.map(({ ver, archived }) => (
            <button
              key={ver}
              onClick={() => setSelectedVer(ver)}
              className={[
                "rounded px-2.5 py-1 text-[11px] transition-colors",
                currentVer === ver
                  ? "bg-white/15 text-white"
                  : "bg-white/5 text-muted hover:bg-white/10",
              ].join(" ")}
            >
              v{ver}
              {!archived && (
                <span className="ml-1 rounded bg-emerald-500/20 px-1 text-[10px] text-emerald-400">
                  активная
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {style && (
        <p className="mb-2 text-[11px] text-muted">
          <span className="text-gray-400">Стиль v{currentVer}:</span> {style}
        </p>
      )}
      {visualsError && <p className="mb-2 text-xs text-red-300">{visualsError.error_message}</p>}

      {currentAssets.length > 0 ? (
        <VisualsGrid items={currentAssets} onOpen={(i) => openLightbox(currentVer!, i)} />
      ) : (
        !visualsError && (
          <p className="text-xs text-muted">
            Картинки по контексту сценария, смена каждые ~3 минуты видео. Нужен ключ
            REPLICATE_API_TOKEN в .env.
          </p>
        )
      )}

      {/* Кнопка «Использовать эту версию» — если смотрим архивную */}
      {hasMultipleVersions && currentVer !== null && !isSelectedActive && (
        <div className="mt-3 flex items-center gap-2 border-t border-white/10 pt-3">
          <span className="text-[11px] text-muted">Это архивная версия.</span>
          <button
            className="btn-ghost px-2 py-1 text-xs"
            disabled={activateMutation.isPending}
            onClick={() => activateMutation.mutate(currentVer)}
          >
            <CheckCircle2 size={13} /> Использовать как активную
          </button>
        </div>
      )}

      {lightbox !== null && lightboxAssets[lightbox.index] && (
        <Lightbox
          items={lightboxAssets}
          index={lightbox.index}
          onClose={() => setLightbox(null)}
          onNav={(i) => setLightbox({ ver: lightbox.ver, index: i })}
        />
      )}
    </div>
  );
}

function Lightbox({
  items,
  index,
  onClose,
  onNav,
}: {
  items: VisualAsset[];
  index: number;
  onClose: () => void;
  onNav: (i: number) => void;
}) {
  const v = items[index];
  const prev = () => onNav((index - 1 + items.length) % items.length);
  const next = () => onNav((index + 1) % items.length);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") prev();
      else if (e.key === "ArrowRight") next();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/85 p-6"
      onClick={onClose}
    >
      <button
        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
        onClick={onClose}
        aria-label="Закрыть"
      >
        <X size={20} />
      </button>
      {items.length > 1 && (
        <>
          <button
            className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
            onClick={(e) => { e.stopPropagation(); prev(); }}
            aria-label="Назад"
          >
            <ChevronLeft size={24} />
          </button>
          <button
            className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
            onClick={(e) => { e.stopPropagation(); next(); }}
            aria-label="Вперёд"
          >
            <ChevronRight size={24} />
          </button>
        </>
      )}
      <img
        src={fileUrl(v.file_path)}
        alt={v.asset_metadata.prompt}
        className="max-h-[80vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
      <div
        className="mt-3 max-w-[90vw] text-center text-xs text-gray-300"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="text-gray-500">
          {index + 1} / {items.length}
          {v.asset_metadata.model && <> · {v.asset_metadata.model}</>} ·{" "}
        </span>
        {v.asset_metadata.prompt}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="break-words">{value}</div>
    </div>
  );
}

function LangContent({
  videoId,
  projectId,
  lang,
  isPrimary,
  script,
  audio,
  logs,
  onRetryStage,
  isStageRunning,
  retryPending,
  onUploadAudio,
  uploadPending,
  voices,
  channelVoiceId,
  overrideVoiceId,
  onSetVoiceOverride,
  voiceOverridePending,
  renderParams,
}: {
  videoId: string;
  projectId: string;
  lang: string;
  isPrimary: boolean;
  script: Script;
  audio: AudioTrack | null;
  logs?: GenLog[];
  onRetryStage: (stage: string) => void;
  isStageRunning: (stage: string) => boolean;
  retryPending: boolean;
  onUploadAudio: (file: File) => void;
  uploadPending: boolean;
  voices?: Voice[];
  channelVoiceId?: string;
  overrideVoiceId?: string;
  onSetVoiceOverride: (voiceId: string | null) => void;
  voiceOverridePending: boolean;
  renderParams?: RenderParams | null;
}) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(script.content_md);
  useEffect(() => setText(script.content_md), [script.content_md]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const save = useMutation({
    mutationFn: () => api.editScript(videoId, lang, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scripts", videoId] });
      setEdit(false);
    },
  });

  const translateError = !isPrimary
    ? logs?.find((l) => l.stage === `translate:${lang}` && l.status === "error")
    : undefined;
  const ttsError = logs?.find((l) => l.stage === `tts:${lang}` && l.status === "error");
  const renderError = logs?.find((l) => l.stage === `render:${lang}` && l.status === "error");
  const audioReady = audio?.status === "ready";

  // История аудио
  const { data: audioHistory } = useQuery({
    queryKey: ["audio-history", videoId],
    queryFn: () => api.audioHistory(videoId),
    enabled: audioReady,
  });
  const audioVersions = useMemo(() => {
    if (!audioHistory) return [];
    const forLang = audioHistory.filter((t) => {
      // определяем язык трека через script_id — сравниваем с текущим script.id
      return true; // фильтр по script_id ниже
    }).filter((t) => t.script_id === script.id);
    const map = new Map<number, AudioTrack>();
    for (const t of forLang) {
      const prev = map.get(t.version);
      if (!prev || t.version > prev.version) map.set(t.version, t);
    }
    return Array.from(map.values()).sort((a, b) => b.version - a.version);
  }, [audioHistory, script.id]);
  const [selectedAudioVer, setSelectedAudioVer] = useState<number | null>(null);
  const activeAudioVer = audioVersions.find((t) => !t.archived)?.version ?? audioVersions[0]?.version ?? null;
  const currentAudioVer = selectedAudioVer ?? activeAudioVer;
  const currentAudioTrack = audioVersions.find((t) => t.version === currentAudioVer) ?? audio;
  const hasMultipleAudioVersions = audioVersions.length > 1;

  const activateAudioMutation = useMutation({
    mutationFn: (version: number) => api.activateAudioVersion(videoId, lang, version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["audio", videoId] });
      qc.invalidateQueries({ queryKey: ["audio-history", videoId] });
    },
  });

  // История рендеров
  const { data: rendersHistory } = useQuery({
    queryKey: ["renders-history", videoId, lang],
    queryFn: () => api.rendersHistory(videoId, lang),
    enabled: true,
  });
  const renderVersions = useMemo(() => {
    if (!rendersHistory) return [];
    const map = new Map<number, VisualAsset>();
    for (const a of rendersHistory) {
      const v = a.asset_metadata?.version ?? 1;
      const prev = map.get(v);
      if (!prev) map.set(v, a);
    }
    return Array.from(map.values()).sort((a, b) =>
      (b.asset_metadata?.version ?? 1) - (a.asset_metadata?.version ?? 1)
    );
  }, [rendersHistory]);
  const [selectedRenderVer, setSelectedRenderVer] = useState<number | null>(null);
  const activeRenderVer = renderVersions.find((a) => !a.asset_metadata?.archived)?.asset_metadata?.version
    ?? renderVersions[0]?.asset_metadata?.version ?? null;
  const currentRenderVer = selectedRenderVer ?? activeRenderVer;
  const currentRenderAsset = renderVersions.find((a) => (a.asset_metadata?.version ?? 1) === currentRenderVer);
  const hasMultipleRenderVersions = renderVersions.length > 1;
  const finalSrc = currentRenderAsset
    ? fileUrl(currentRenderAsset.file_path)
    : fileUrl(`/projects/${projectId}/videos/${videoId}/final_${lang}.mp4`);

  const activateRenderMutation = useMutation({
    mutationFn: (version: number) => api.activateRenderVersion(videoId, lang, version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["renders-history", videoId, lang] });
    },
  });

  return (
    <div className="space-y-4">
      {translateError && (
        <StageWarning
          message={translateError.error_message ?? "Перевод не удался"}
          actionLabel="Повторить перевод"
          onAction={() => onRetryStage("translate")}
          disabled={retryPending || isStageRunning(`translate:${lang}`)}
        />
      )}

      <div className="card">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium">
            Сценарий · {script.word_count} слов · ~{fmtDurationLocal(script.duration_estimate_sec)}
          </h3>
          {edit ? (
            <div className="flex gap-2">
              <button className="text-xs text-muted hover:text-white" onClick={() => setEdit(false)}>
                Отмена
              </button>
              <button
                className="text-xs text-indigo-400 hover:underline"
                onClick={() => save.mutate()}
                disabled={save.isPending}
              >
                Сохранить
              </button>
            </div>
          ) : (
            <button className="text-xs text-indigo-400 hover:underline" onClick={() => setEdit(true)}>
              Редактировать
            </button>
          )}
        </div>
        {edit ? (
          <textarea
            className="input min-h-[300px] font-mono text-xs leading-relaxed"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        ) : (
          <pre className="max-h-[400px] overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-gray-200">
            {script.content_md}
          </pre>
        )}
      </div>

      <div className="card">
        <h3 className="mb-2 text-sm font-medium">Голос для этого видео</h3>
        <select
          className="input"
          disabled={voiceOverridePending}
          value={overrideVoiceId ?? ""}
          onChange={(e) => onSetVoiceOverride(e.target.value || null)}
        >
          <option value="">
            Голос канала{channelVoiceId ? ` (${channelVoiceId})` : " (не выбран)"}
          </option>
          {(voices ?? [])
            .filter((v) => v.language === lang)
            .map((v) => (
              <option key={v.id} value={v.voice_id}>
                {v.name} ({v.voice_id})
              </option>
            ))}
        </select>
        {overrideVoiceId && (
          <p className="mt-1 text-xs text-muted">
            Для этого видео используется свой голос вместо голоса канала. Чтобы применить —
            нажми «Озвучить» ниже.
          </p>
        )}
      </div>

      <div className="card">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium">
            Аудио{currentAudioTrack ? ` · ${currentAudioTrack.engine} · ${currentAudioTrack.voice_id}` : ""}
          </h3>
          <div className="flex gap-2">
            <button
              className="btn-ghost px-2 py-1 text-xs"
              disabled={retryPending || isStageRunning(`tts:${lang}`)}
              onClick={() => onRetryStage("tts")}
            >
              <RefreshCw size={13} /> {audioReady ? "Переозвучить" : "Озвучить"}
            </button>
            <button
              className="btn-ghost px-2 py-1 text-xs"
              disabled={uploadPending}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={13} /> Загрузить вручную
            </button>
            {audioReady && (
              <a
                className="btn-ghost px-2 py-1 text-xs"
                href={srtUrl(videoId, lang)}
                download
                title="Приблизительные тайминги по предложениям сценария"
              >
                <Download size={13} /> .srt
              </a>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUploadAudio(f);
                e.target.value = "";
              }}
            />
          </div>
        </div>
        {/* Вкладки версий аудио */}
        {hasMultipleAudioVersions && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {audioVersions.map((t) => (
              <button
                key={t.version}
                onClick={() => setSelectedAudioVer(t.version)}
                className={[
                  "rounded px-2.5 py-1 text-[11px] transition-colors",
                  currentAudioVer === t.version
                    ? "bg-white/15 text-white"
                    : "bg-white/5 text-muted hover:bg-white/10",
                ].join(" ")}
              >
                v{t.version}
                {!t.archived && (
                  <span className="ml-1 rounded bg-emerald-500/20 px-1 text-[10px] text-emerald-400">
                    активная
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
        {currentAudioTrack?.status === "ready" ? (
          <audio controls src={fileUrl(currentAudioTrack.file_path)} className="w-full" />
        ) : ttsError ? (
          <p className="text-xs text-red-300">{ttsError.error_message}</p>
        ) : (
          <p className="text-xs text-muted">Аудио ещё не сгенерировано.</p>
        )}
        {/* Кнопка «Использовать» для архивной версии */}
        {hasMultipleAudioVersions && currentAudioVer !== null &&
          audioVersions.find((t) => t.version === currentAudioVer)?.archived && (
          <div className="mt-2 flex items-center gap-2 border-t border-white/10 pt-2">
            <span className="text-[11px] text-muted">Архивная версия.</span>
            <button
              className="btn-ghost px-2 py-0.5 text-xs"
              disabled={activateAudioMutation.isPending}
              onClick={() => activateAudioMutation.mutate(currentAudioVer)}
            >
              <CheckCircle2 size={13} /> Использовать как активную
            </button>
          </div>
        )}
      </div>

      <div className="card">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium">Готовое видео</h3>
          <div className="flex gap-2">
            <button
              className="btn-ghost px-2 py-1 text-xs"
              disabled={retryPending || isStageRunning(`render:${lang}`)}
              onClick={() => onRetryStage("render")}
            >
              <RefreshCw size={13} /> Перерендерить
            </button>
            <a className="btn-ghost px-2 py-1 text-xs" href={finalSrc} download>
              <Download size={14} /> Скачать
            </a>
          </div>
        </div>
        {/* Вкладки версий рендера */}
        {hasMultipleRenderVersions && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {renderVersions.map((a) => {
              const ver = a.asset_metadata?.version ?? 1;
              const isArchived = a.asset_metadata?.archived ?? false;
              return (
                <button
                  key={ver}
                  onClick={() => setSelectedRenderVer(ver)}
                  className={[
                    "rounded px-2.5 py-1 text-[11px] transition-colors",
                    currentRenderVer === ver
                      ? "bg-white/15 text-white"
                      : "bg-white/5 text-muted hover:bg-white/10",
                  ].join(" ")}
                >
                  v{ver}
                  {!isArchived && (
                    <span className="ml-1 rounded bg-emerald-500/20 px-1 text-[10px] text-emerald-400">
                      активная
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
        <RenderParamsPanel videoId={videoId} initial={renderParams} />
        {renderError && <p className="mb-2 text-xs text-red-300">{renderError.error_message}</p>}
        <video
          controls
          src={finalSrc}
          className="w-full rounded-lg"
          onError={(e) => {
            const el = (e.target as HTMLVideoElement).parentElement!;
            const note = el.querySelector(".no-video");
            if (!note) {
              const d = document.createElement("div");
              d.className = "no-video text-sm text-muted";
              d.textContent = "Финальный рендер ещё не готов";
              el.appendChild(d);
            }
          }}
        />
        {/* Кнопка «Использовать» для архивного рендера */}
        {hasMultipleRenderVersions && currentRenderVer !== null &&
          renderVersions.find((a) => (a.asset_metadata?.version ?? 1) === currentRenderVer)?.asset_metadata?.archived && (
          <div className="mt-2 flex items-center gap-2 border-t border-white/10 pt-2">
            <span className="text-[11px] text-muted">Архивная версия.</span>
            <button
              className="btn-ghost px-2 py-0.5 text-xs"
              disabled={activateRenderMutation.isPending}
              onClick={() => activateRenderMutation.mutate(currentRenderVer)}
            >
              <CheckCircle2 size={13} /> Использовать как активную
            </button>
          </div>
        )}
      </div>

      {isPrimary && <YouTubePackageCard videoId={videoId} />}
    </div>
  );
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="btn-ghost px-2 py-0.5 text-xs"
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? <CheckCircle2 size={13} className="text-emerald-400" /> : <Copy size={13} />}
      {label ?? "Копировать"}
    </button>
  );
}

function YouTubePackageCard({ videoId }: { videoId: string }) {
  const { data: pkg, error } = useQuery({
    queryKey: ["youtube-package", videoId],
    queryFn: () => api.youtubePackage(videoId),
    retry: false,
  });

  if (error) return null; // анализ ещё не готов — карточку не показываем
  if (!pkg) return null;

  return (
    <div className="card">
      <h3 className="mb-3 text-sm font-medium">Публикация на YouTube</h3>

      <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">Варианты заголовка</p>
      <ul className="mb-3 space-y-1">
        {pkg.titles.map((t, i) => (
          <li key={i} className="flex items-center gap-2 text-sm text-gray-200">
            <span className="flex-1">{t}</span>
            <CopyButton text={t} label="" />
          </li>
        ))}
      </ul>

      <div className="mb-1 flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wide text-muted">Описание</p>
        <CopyButton text={pkg.description} />
      </div>
      <pre className="mb-3 max-h-[180px] overflow-y-auto whitespace-pre-wrap rounded bg-surface2 p-2 text-xs leading-relaxed text-gray-300">
        {pkg.description}
      </pre>

      <div className="mb-1 flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wide text-muted">
          Теги ({pkg.tags.length}, {pkg.tags_string.length}/500 символов)
        </p>
        <CopyButton text={pkg.tags_string} />
      </div>
      <p className="text-xs text-gray-400">{pkg.tags_string || "Теги не сгенерированы"}</p>
    </div>
  );
}

function StageWarning({
  message,
  actionLabel,
  onAction,
  disabled,
}: {
  message: string;
  actionLabel: string;
  onAction: () => void;
  disabled: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-red-900/50 bg-red-950/30 px-3 py-2 text-xs text-red-300">
      <span className="flex-1">{message}</span>
      <button
        className="shrink-0 rounded bg-red-900/50 px-2 py-1 text-red-200 hover:bg-red-900/70 disabled:opacity-50"
        disabled={disabled}
        onClick={onAction}
      >
        {actionLabel}
      </button>
    </div>
  );
}

const DEFAULT_RENDER_PARAMS: RenderParams = {
  resolution: "720p",
  zoom: "on",
  zoom_speed: 0.3,
  zoom_direction: "in",
  warm_grade: true,
  grade: "warm",
  vignette: false,
  grain: false,
  overlay: "off",
  transition: "none",
  fade_in: false,
  fade_out: false,
};

function RenderParamsPanel({
  videoId,
  initial,
}: {
  videoId: string;
  initial: RenderParams | null | undefined;
}) {
  const qc = useQueryClient();
  const params: RenderParams = { ...DEFAULT_RENDER_PARAMS, ...(initial ?? {}) };
  const [local, setLocalState] = useState<RenderParams>(params);
  // Ref-зеркало: быстрые последовательные клики не должны терять изменения
  // друг друга из-за устаревшего state в замыкании
  const localRef = useRef(local);
  const setLocal = (next: RenderParams) => {
    localRef.current = next;
    setLocalState(next);
  };

  const save = useMutation({
    mutationFn: (p: RenderParams) => api.setRenderParams(videoId, p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video", videoId] }),
  });

  const setMany = (patch: Partial<RenderParams>) => {
    const next = { ...localRef.current, ...patch };
    setLocal(next);
    save.mutate(next);
  };
  const set = <K extends keyof RenderParams>(k: K, v: RenderParams[K]) =>
    setMany({ [k]: v } as Partial<RenderParams>);

  // Режим камеры: выкл / приближение / отдаление / чередование / панорама
  const cameraMode = local.zoom === "off" ? "off" : local.zoom_direction;
  const setCameraMode = (mode: "off" | "in" | "out" | "alternate" | "pan") => {
    if (mode === "off") setMany({ zoom: "off" });
    else setMany({ zoom: "on", zoom_direction: mode });
  };

  // Цветокор: приоритет grade; для старых записей выводим из warm_grade
  const gradeValue = local.grade ?? (local.warm_grade ? "warm" : "off");
  const setGrade = (g: RenderParams["grade"]) =>
    setMany({ grade: g, warm_grade: g === "warm" });

  const [previewTs, setPreviewTs] = useState(0);
  const preview = useMutation({
    mutationFn: () => api.previewRender(videoId),
    onSuccess: () => setPreviewTs(Date.now()),
  });

  const btn = (active: boolean) =>
    `rounded px-2 py-0.5 ${
      active ? "bg-indigo-600 text-white" : "bg-surface text-gray-300 hover:bg-border"
    }`;

  const cameraLabels: Record<string, string> = {
    off: "Выкл",
    in: "Приближение",
    out: "Отдаление",
    alternate: "Чередование",
    pan: "Панорама",
  };
  const gradeLabels: Record<string, string> = {
    warm: "Тёплый",
    off: "Без",
    cold: "Холодный",
    vintage: "Винтаж",
    bw: "Ч/Б",
  };
  const overlayLabels: Record<string, string> = {
    off: "Нет",
    fireflies: "Светлячки",
    embers: "Искры огня",
    dust: "Пыль",
  };
  const transitionLabels: Record<string, string> = {
    none: "Резкий",
    dip: "Затемнение",
    fade: "Кроссфейд",
  };

  return (
    <div className="mb-3 rounded-lg border border-border bg-surface2 px-3 py-2.5">
      <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted">
        Параметры монтажа
      </p>
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs">
        {/* Разрешение */}
        <div className="flex items-center gap-1.5">
          <span className="text-muted">Разрешение:</span>
          {(["720p", "1080p", "1440p"] as const).map((r) => (
            <button key={r} onClick={() => set("resolution", r)} className={btn(local.resolution === r)}>
              {r}
            </button>
          ))}
        </div>

        {/* Движение камеры (зум всегда в центр кадра) */}
        <div className="flex items-center gap-1.5">
          <span className="text-muted">Камера:</span>
          {(["off", "in", "out", "alternate", "pan"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setCameraMode(m)}
              className={btn(cameraMode === m)}
              title={
                m === "alternate"
                  ? "Чётные кадры приближают, нечётные отдаляют"
                  : m === "pan"
                    ? "Камера медленно едет вбок, направление чередуется по кадрам"
                    : undefined
              }
            >
              {cameraLabels[m]}
            </button>
          ))}
        </div>

        {/* Скорость зума — ползунок (для панорамы скорость фиксированная) */}
        {cameraMode !== "off" && cameraMode !== "pan" && (
          <div className="flex items-center gap-1.5">
            <span className="text-muted">Скорость:</span>
            <input
              type="range"
              min={0.05}
              max={2}
              step={0.05}
              value={local.zoom_speed}
              onChange={(e) =>
                setLocal({ ...localRef.current, zoom_speed: parseFloat(e.target.value) })
              }
              onMouseUp={(e) =>
                setMany({ zoom_speed: parseFloat((e.target as HTMLInputElement).value) })
              }
              onTouchEnd={(e) =>
                setMany({ zoom_speed: parseFloat((e.target as HTMLInputElement).value) })
              }
              className="h-1.5 w-28 cursor-pointer accent-indigo-600"
              title="% кадра в секунду; 0.3 — очень медленно (по умолчанию)"
            />
            <span className="w-14 tabular-nums text-gray-300">
              {local.zoom_speed.toFixed(2)}%/с
            </span>
          </div>
        )}

        {/* Цветокор */}
        <div className="flex items-center gap-1.5">
          <span className="text-muted">Цветокор:</span>
          {(["warm", "off", "cold", "vintage", "bw"] as const).map((g) => (
            <button key={g} onClick={() => setGrade(g)} className={btn(gradeValue === g)}>
              {gradeLabels[g]}
            </button>
          ))}
        </div>

        {/* Оверлей частиц */}
        <div className="flex items-center gap-1.5">
          <span className="text-muted">Огоньки:</span>
          {(["off", "fireflies", "embers", "dust"] as const).map((o) => (
            <button key={o} onClick={() => set("overlay", o)} className={btn(local.overlay === o)}>
              {overlayLabels[o]}
            </button>
          ))}
        </div>

        {/* Переход между кадрами */}
        <div className="flex items-center gap-1.5">
          <span className="text-muted">Переход:</span>
          {(["none", "dip", "fade"] as const).map((t) => (
            <button key={t} onClick={() => set("transition", t)} className={btn(local.transition === t)}>
              {transitionLabels[t]}
            </button>
          ))}
        </div>

        {/* Флажки-эффекты */}
        {(
          [
            ["vignette", "Виньетка"],
            ["grain", "Зерно плёнки"],
            ["fade_in", "Из темноты"],
            ["fade_out", "В темноту"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={local[key]}
              onChange={(e) => set(key, e.target.checked)}
              className="h-3.5 w-3.5 accent-indigo-600"
            />
            <span className="text-gray-300">{label}</span>
          </label>
        ))}
      </div>

      {/* Превью монтажа: короткий ролик с текущими параметрами */}
      <div className="mt-2 border-t border-border pt-2">
        <button
          className="btn-ghost px-2 py-1 text-xs"
          disabled={preview.isPending || save.isPending}
          onClick={() => preview.mutate()}
          title="Собирает ~12-секундный ролик из первых картинок с текущими параметрами"
        >
          {preview.isPending ? (
            <>
              <Loader2 size={13} className="animate-spin" /> Рендерим превью…
            </>
          ) : (
            <>
              <RefreshCw size={13} /> Превью монтажа (~12 сек)
            </>
          )}
        </button>
        {preview.isError && (
          <p className="mt-1 text-[11px] text-red-300">{(preview.error as Error).message}</p>
        )}
        {preview.data && !preview.isPending && previewTs > 0 && (
          <video
            key={previewTs}
            controls
            autoPlay
            muted
            loop
            src={fileUrl(preview.data.url) + `?t=${previewTs}`}
            className="mt-2 w-full rounded-lg"
          />
        )}
      </div>

      {save.isPending && (
        <p className="mt-1 text-[10px] text-muted">Сохраняем…</p>
      )}
    </div>
  );
}

function fmtDurationLocal(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// PlaylistEditor — drag-and-drop редактор визуального ряда
// ---------------------------------------------------------------------------
function PlaylistEditor({ videoId }: { videoId: string }) {
  const qc = useQueryClient();

  const { data: allAssets = [] } = useQuery({
    queryKey: ["visuals-all", videoId],
    queryFn: () => api.allVisuals(videoId),
  });

  const { data: playlistData } = useQuery({
    queryKey: ["playlist", videoId],
    queryFn: () => api.getPlaylist(videoId),
  });

  // Локальный плейлист — список id в нужном порядке
  const [playlist, setPlaylist] = useState<string[]>([]);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);

  // Синхронизируем с сервером один раз при загрузке
  useEffect(() => {
    if (playlistData && !dirty) setPlaylist(playlistData.playlist ?? []);
  }, [playlistData]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveMutation = useMutation({
    mutationFn: (pl: string[]) => api.setPlaylist(videoId, pl),
    onSuccess: () => {
      setDirty(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      qc.invalidateQueries({ queryKey: ["playlist", videoId] });
    },
  });

  // drag state
  const dragSrc = useRef<{ from: "pool" | "row"; id: string; rowIdx?: number } | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  const assetMap = useMemo(
    () => Object.fromEntries(allAssets.map((a) => [a.id, a])),
    [allAssets]
  );

  // Группируем пул по версиям
  const poolByVersion = useMemo(() => {
    const map = new Map<number, VisualAsset[]>();
    for (const a of allAssets) {
      const ver = a.asset_metadata?.version ?? 1;
      if (!map.has(ver)) map.set(ver, []);
      map.get(ver)!.push(a);
    }
    return [...map.entries()].sort(([a], [b]) => a - b);
  }, [allAssets]);

  const removeFromPlaylist = (idx: number) => {
    setPlaylist((pl) => pl.filter((_, i) => i !== idx));
    setDirty(true);
  };

  const handleRowDragStart = (id: string, idx: number) => {
    dragSrc.current = { from: "row", id, rowIdx: idx };
  };

  const handlePoolDragStart = (id: string) => {
    dragSrc.current = { from: "pool", id };
  };

  const handleRowDrop = (e: React.DragEvent, toIdx: number) => {
    e.preventDefault();
    setDragOverIdx(null);
    const src = dragSrc.current;
    if (!src) return;

    setPlaylist((pl) => {
      const next = [...pl];
      if (src.from === "pool") {
        next.splice(toIdx, 0, src.id);
      } else if (src.from === "row" && src.rowIdx !== undefined && src.rowIdx !== toIdx) {
        next.splice(src.rowIdx, 1);
        const insertAt = src.rowIdx < toIdx ? toIdx - 1 : toIdx;
        next.splice(insertAt, 0, src.id);
      }
      return next;
    });
    setDirty(true);
    dragSrc.current = null;
  };

  const handleRowEnd = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOverIdx(null);
    const src = dragSrc.current;
    if (!src) return;
    setPlaylist((pl) => [...pl, src.id]);
    setDirty(true);
    dragSrc.current = null;
  };

  const inPlaylist = new Set(playlist);

  return (
    <div className="mb-4 rounded-lg border border-white/10 bg-white/3 p-3">
      {/* Активный ряд */}
      <div className="mb-3">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-xs font-medium text-gray-300">
            Активный ряд · {playlist.length} картинок
            {playlist.length > 0 && (
              <span className="ml-1 text-muted">(перетащите из пула ↓ или меняйте порядок)</span>
            )}
          </span>
          <div className="flex gap-2">
            {playlist.length > 0 && (
              <button
                className="btn-ghost px-2 py-0.5 text-xs text-red-400"
                onClick={() => { setPlaylist([]); setDirty(true); }}
              >
                Очистить
              </button>
            )}
            <button
              className={`px-3 py-0.5 text-xs rounded transition-colors ${
                saved ? "bg-emerald-600/30 text-emerald-400" :
                dirty ? "bg-indigo-600 text-white hover:bg-indigo-500" :
                "btn-ghost opacity-50"
              }`}
              disabled={!dirty || saveMutation.isPending}
              onClick={() => saveMutation.mutate(playlist)}
            >
              {saved ? "✓ Сохранено" : saveMutation.isPending ? "Сохраняю…" : "Сохранить"}
            </button>
          </div>
        </div>

        {/* Дроп-зона ряда */}
        <div
          className={`flex min-h-[80px] flex-nowrap gap-2 overflow-x-auto rounded-lg border-2 border-dashed p-2 transition-colors ${
            playlist.length === 0 ? "items-center justify-center border-white/10" : "border-white/10"
          }`}
          onDragOver={(e) => { e.preventDefault(); }}
          onDrop={(e) => handleRowEnd(e)}
        >
          {playlist.length === 0 ? (
            <p className="text-xs text-muted">Перетащите картинки из пула сюда</p>
          ) : (
            playlist.map((id, idx) => {
              const asset = assetMap[id];
              if (!asset) return null;
              const ver = asset.asset_metadata?.version ?? 1;
              return (
                <div
                  key={`${id}-${idx}`}
                  className={`relative shrink-0 cursor-grab transition-opacity ${
                    dragOverIdx === idx ? "opacity-40" : "opacity-100"
                  }`}
                  draggable
                  onDragStart={() => handleRowDragStart(id, idx)}
                  onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setDragOverIdx(idx); }}
                  onDragLeave={() => setDragOverIdx(null)}
                  onDrop={(e) => handleRowDrop(e, idx)}
                >
                  <img
                    src={fileUrl(asset.file_path)}
                    className="h-16 w-28 rounded object-cover ring-1 ring-white/10"
                    draggable={false}
                  />
                  <span className="absolute left-1 top-1 rounded bg-black/60 px-1 text-[10px] text-white/70">
                    v{ver}·{idx + 1}
                  </span>
                  <button
                    className="absolute right-0.5 top-0.5 rounded bg-black/70 p-0.5 text-white/60 hover:text-white"
                    onClick={() => removeFromPlaylist(idx)}
                  >
                    <X size={10} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Пул всех картинок */}
      <div>
        <span className="mb-1.5 block text-xs font-medium text-gray-300">
          Пул · все генерации
        </span>
        <div className="space-y-2">
          {poolByVersion.map(([ver, assets]) => (
            <div key={ver}>
              <span className="mb-1 block text-[11px] text-muted">Версия {ver}</span>
              <div className="flex flex-wrap gap-1.5">
                {assets.map((asset) => {
                  const alreadyIn = inPlaylist.has(asset.id);
                  return (
                    <div
                      key={asset.id}
                      className={`relative shrink-0 transition-opacity ${alreadyIn ? "opacity-40" : "cursor-grab opacity-100"}`}
                      draggable={!alreadyIn}
                      onDragStart={() => !alreadyIn && handlePoolDragStart(asset.id)}
                      onDoubleClick={() => {
                        if (!alreadyIn) {
                          setPlaylist((pl) => [...pl, asset.id]);
                          setDirty(true);
                        }
                      }}
                      title={alreadyIn ? "Уже в ряду" : "Перетащите или дважды кликните чтобы добавить"}
                    >
                      <img
                        src={fileUrl(asset.file_path)}
                        className={`h-14 w-24 rounded object-cover ring-1 ${alreadyIn ? "ring-white/5" : "ring-white/20 hover:ring-indigo-400"}`}
                        draggable={false}
                      />
                      {alreadyIn && (
                        <div className="absolute inset-0 flex items-center justify-center rounded bg-black/40">
                          <CheckCircle2 size={16} className="text-emerald-400" />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


function MusicSelector({ videoId }: { videoId: string }) {
  const qc = useQueryClient();
  const { data: video } = useQuery({ queryKey: ["video", videoId], queryFn: () => api.getVideo(videoId) });
  const { data: tracks = [] } = useQuery({ queryKey: ["music"], queryFn: () => api.listMusic() });

  const [trackId, setTrackId] = useState<string>("");
  const [volume, setVolume] = useState<number>(0.15);

  useEffect(() => {
    if (video) {
      setTrackId(video.music_track_id ?? "");
      setVolume(video.music_volume ?? 0.15);
    }
  }, [video?.music_track_id, video?.music_volume]);

  const save = useMutation({
    mutationFn: () => api.setVideoMusic(videoId, trackId || null, volume),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video", videoId] }),
  });

  const readyTracks = tracks.filter((t) => t.status === "ready");

  return (
    <div className="card space-y-2 text-sm">
      <p className="font-medium text-xs text-muted uppercase tracking-wide">Фоновая музыка</p>
      <select
        className="input text-sm"
        value={trackId}
        onChange={(e) => setTrackId(e.target.value)}
      >
        <option value="">— без музыки —</option>
        {readyTracks.map((t) => (
          <option key={t.id} value={t.id}>{t.title || "Без названия"}</option>
        ))}
      </select>
      {trackId && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted">
            <span>Громкость</span>
            <span>{Math.round(volume * 100)}%</span>
          </div>
          <input
            type="range" min={0} max={1} step={0.01}
            value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
            className="w-full accent-indigo-500"
          />
        </div>
      )}
      <button
        className="btn-ghost w-full text-xs py-1"
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Сохраняем…" : "Сохранить"}
      </button>
    </div>
  );
}

function TitleOption({ title }: { title: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(title);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="group flex items-center justify-between gap-2 rounded-md border border-border bg-surface2/30 px-3 py-2">
      <span className="text-sm leading-snug">{title}</span>
      <button
        className="shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100 hover:text-gray-200"
        onClick={copy}
        title="Скопировать"
      >
        {copied ? <CheckCircle2 size={14} className="text-emerald-400" /> : <Copy size={14} />}
      </button>
    </div>
  );
}

function ThumbnailHistory({
  videoId,
  onRestore,
}: {
  videoId: string;
  projectId: string;
  onRestore: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [expandedPrompt, setExpandedPrompt] = useState<number | null>(null);

  const { data: history = [], refetch } = useQuery({
    queryKey: ["thumbnail-history", videoId],
    queryFn: () => api.getThumbnailHistory(videoId),
    enabled: open,
  });

  const restoreMut = useMutation({
    mutationFn: (version: number) => api.restoreThumbnail(videoId, version),
    onSuccess: () => {
      onRestore();
      refetch();
    },
  });

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-2 text-xs text-zinc-500 hover:text-zinc-300 underline underline-offset-2"
      >
        История обложек
      </button>
    );
  }

  return (
    <div className="mt-3 border border-zinc-700 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-zinc-800 border-b border-zinc-700">
        <span className="text-xs font-medium text-zinc-300">История обложек</span>
        <button onClick={() => setOpen(false)} className="text-zinc-500 hover:text-zinc-300 text-xs">✕</button>
      </div>
      {history.length === 0 ? (
        <p className="text-xs text-zinc-500 p-3">Нет истории</p>
      ) : (
        <div className="divide-y divide-zinc-800">
          {[...history].reverse().map((entry) => (
            <div key={entry.version} className="p-3 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs font-semibold text-zinc-400">v{entry.version}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 shrink-0">
                    {entry.model}
                  </span>
                  <span className="text-xs text-zinc-500 truncate">
                    {new Date(entry.created_at).toLocaleString("ru-RU")}
                  </span>
                </div>
                {entry.archived_file && entry.version !== history[history.length - 1]?.version && (
                  <button
                    onClick={() => restoreMut.mutate(entry.version)}
                    disabled={restoreMut.isPending}
                    className="text-xs text-indigo-400 hover:text-indigo-300 shrink-0"
                  >
                    Восстановить
                  </button>
                )}
              </div>
              {entry.prompt && (
                <div>
                  <button
                    onClick={() => setExpandedPrompt(expandedPrompt === entry.version ? null : entry.version)}
                    className="text-xs text-zinc-500 hover:text-zinc-400 underline underline-offset-2"
                  >
                    {expandedPrompt === entry.version ? "Скрыть промт" : "Показать промт"}
                  </button>
                  {expandedPrompt === entry.version && (
                    <p className="mt-1 text-xs text-zinc-400 bg-zinc-900 rounded p-2 leading-relaxed">
                      {entry.prompt}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
