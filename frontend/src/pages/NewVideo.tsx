import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Lightbulb, RefreshCw } from "lucide-react";
import { api, type NewVideoPayload } from "../lib/api";
import { useJobSocket } from "../lib/useJobSocket";
import { PipelineLog } from "../components/PipelineLog";

export default function NewVideo() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
  });

  const [scriptMode, setScriptMode] = useState<"generate" | "manual">("generate");
  const [brief, setBrief] = useState("");
  const [manualScript, setManualScript] = useState("");
  const [duration, setDuration] = useState(12);
  const [runTranslate, setRunTranslate] = useState(true);
  const [runTts, setRunTts] = useState(false);
  const [runRender, setRunRender] = useState(false);
  const [runVisuals, setRunVisuals] = useState(false);
  const [videoId, setVideoId] = useState<string | null>(null);

  // Адаптированные под тему промты (после правки можно запускать с ними).
  // null -> бэкенд адаптирует шаблоны автоматически при генерации.
  const [prompts, setPrompts] = useState<{ stage1: string; stage2: string; stage3: string } | null>(
    null
  );

  const [ideas, setIdeas] = useState<{ title: string; brief: string }[]>([]);

  const suggestTopics = useMutation({
    mutationFn: () => api.suggestTopics(projectId, 6),
    onSuccess: (data) => setIdeas(data),
  });

  const { events, done } = useJobSocket(videoId, !!videoId);

  // Пакетный режим: каждая непустая строка поля темы — отдельное видео
  const [batchMode, setBatchMode] = useState(false);
  const batchTopics = brief
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  const canSubmit =
    scriptMode === "generate"
      ? batchMode
        ? batchTopics.length > 0
        : !!brief.trim()
      : !!manualScript.trim();

  const adapt = useMutation({
    mutationFn: () => api.adaptPrompts(projectId, brief),
    onSuccess: (p) => setPrompts({ stage1: p.stage1, stage2: p.stage2, stage3: p.stage3 }),
  });

  const create = useMutation({
    mutationFn: () => {
      const payload: NewVideoPayload = {
        topic_brief: brief,
        target_duration_min: duration,
        run_translate: runTranslate,
        run_tts: runTts,
        run_render: runRender,
        run_visuals: runVisuals,
        script_content: scriptMode === "manual" ? manualScript : null,
        script_prompts: scriptMode === "generate" ? prompts : null,
      };
      return api.createVideo(projectId, payload);
    },
    onSuccess: (v) => setVideoId(v.id),
  });

  // Пакетный запуск: создаём видео по одному на тему; пайплайны на бэкенде
  // выполняются последовательно (глобальная очередь), очередные ждут в "draft"
  const createBatch = useMutation({
    mutationFn: async () => {
      for (const topic of batchTopics) {
        await api.createVideo(projectId, {
          topic_brief: topic,
          target_duration_min: duration,
          run_translate: runTranslate,
          run_tts: runTts,
          run_render: runRender,
          run_visuals: runVisuals,
          script_content: null,
          script_prompts: null,
        });
      }
      return batchTopics.length;
    },
    onSuccess: () => navigate(`/projects/${projectId}`),
  });

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Новое видео</h1>
        <button
          className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-sm"
          disabled={!!videoId || suggestTopics.isPending}
          onClick={() => suggestTopics.mutate()}
        >
          {suggestTopics.isPending ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : (
            <Lightbulb size={14} />
          )}
          {suggestTopics.isPending ? "Подбираю идеи…" : "Предложить идеи"}
        </button>
      </div>

      {/* Блок идей */}
      {(ideas.length > 0 || suggestTopics.isError) && (
        <div className="mb-5">
          {suggestTopics.isError && (
            <p className="mb-2 text-xs text-red-400">{(suggestTopics.error as Error).message}</p>
          )}
          {ideas.length > 0 && (
            <>
              <p className="mb-2 text-xs text-muted">
                Идеи подобраны с учётом тематики канала и уже вышедших видео. Нажмите на карточку — тема вставится в поле.
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {ideas.map((idea, i) => (
                  <button
                    key={i}
                    disabled={!!videoId}
                    onClick={() => {
                      setScriptMode("generate");
                      setBrief(idea.brief);
                      setPrompts(null);
                    }}
                    className="rounded-lg border border-border bg-surface2/40 p-3 text-left transition-colors hover:border-indigo-500/60 hover:bg-indigo-500/10 disabled:opacity-50"
                  >
                    <p className="mb-1 text-xs font-semibold leading-snug text-gray-200">{idea.title}</p>
                    <p className="text-[11px] leading-relaxed text-muted">{idea.brief}</p>
                  </button>
                ))}
              </div>
              <div className="mt-2 flex justify-end">
                <button
                  className="btn-ghost px-2 py-1 text-xs"
                  disabled={!!videoId || suggestTopics.isPending}
                  onClick={() => suggestTopics.mutate()}
                >
                  <RefreshCw size={12} /> Ещё идеи
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="space-y-4">
          <div>
            <label className="label">Сценарий</label>
            <div className="flex gap-1 rounded-lg border border-border p-1">
              <button
                className={`flex-1 rounded-md px-3 py-1.5 text-sm transition-colors ${
                  scriptMode === "generate" ? "bg-indigo-600 text-white" : "text-muted hover:text-gray-200"
                }`}
                disabled={!!videoId}
                onClick={() => setScriptMode("generate")}
              >
                Сгенерировать ИИ
              </button>
              <button
                className={`flex-1 rounded-md px-3 py-1.5 text-sm transition-colors ${
                  scriptMode === "manual" ? "bg-indigo-600 text-white" : "text-muted hover:text-gray-200"
                }`}
                disabled={!!videoId}
                onClick={() => setScriptMode("manual")}
              >
                Вставить свой
              </button>
            </div>
          </div>

          {scriptMode === "generate" ? (
            <>
              <div>
                <label className="label">
                  {batchMode ? "Темы видео (по одной на строку)" : "О чём видео (тема)"}
                </label>
                <textarea
                  className="input min-h-[120px]"
                  placeholder={
                    batchMode
                      ? "Каждая строка — отдельное видео:\nПадение Римской империи\nТайны египетских пирамид\nВеликий шёлковый путь"
                      : "1-3 предложения о теме видео…"
                  }
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  disabled={!!videoId}
                />
                <label className="mt-1.5 flex cursor-pointer items-center gap-2 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={batchMode}
                    onChange={(e) => setBatchMode(e.target.checked)}
                    disabled={!!videoId}
                    className="h-3.5 w-3.5 accent-indigo-600"
                  />
                  Пакетный режим: каждая строка — отдельное видео (генерируются по очереди)
                </label>
              </div>
              <div>
                <label className="label">Целевая длительность: {duration} мин</label>
                <input
                  type="range"
                  min={5}
                  max={30}
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  className="w-full"
                  disabled={!!videoId}
                />
              </div>

              {!batchMode && (
              <div className="rounded-lg border border-border p-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-sm font-medium">Промты генерации (3 шага)</span>
                  {prompts && (
                    <button
                      className="text-xs text-muted hover:text-gray-200"
                      disabled={!!videoId}
                      onClick={() => setPrompts(null)}
                    >
                      Сбросить
                    </button>
                  )}
                </div>
                <p className="mb-2 text-xs text-muted">
                  Сценарий пишется в 3 шага: подготовка → написание → аудит. Можно заранее
                  адаптировать шаблоны под тему и поправить их вручную. Если не нажимать —
                  адаптация произойдёт автоматически при запуске.
                </p>
                {!prompts ? (
                  <button
                    className="btn-ghost w-full text-sm"
                    disabled={!brief.trim() || adapt.isPending || !!videoId}
                    onClick={() => adapt.mutate()}
                  >
                    {adapt.isPending ? "Адаптирую под тему…" : "Подготовить промты под тему"}
                  </button>
                ) : (
                  <div className="space-y-2">
                    <PromptField
                      label="Шаг 1 — Подготовка (бриф)"
                      value={prompts.stage1}
                      onChange={(v) => setPrompts({ ...prompts, stage1: v })}
                      disabled={!!videoId}
                    />
                    <PromptField
                      label="Шаг 2 — Написание сценария"
                      value={prompts.stage2}
                      onChange={(v) => setPrompts({ ...prompts, stage2: v })}
                      disabled={!!videoId}
                    />
                    <PromptField
                      label="Шаг 3 — Аудит и очеловечивание"
                      value={prompts.stage3}
                      onChange={(v) => setPrompts({ ...prompts, stage3: v })}
                      disabled={!!videoId}
                    />
                  </div>
                )}
                {adapt.isError && (
                  <div className="mt-2 text-xs text-red-400">{(adapt.error as Error).message}</div>
                )}
              </div>
              )}
            </>
          ) : (
            <>
              <div>
                <label className="label">Готовый сценарий</label>
                <textarea
                  className="input min-h-[220px] font-mono text-xs leading-relaxed"
                  placeholder="Вставьте текст сценария целиком — генерация через Claude для него пропускается. Дальше его всё равно можно проанализировать, перевести, озвучить и собрать в видео."
                  value={manualScript}
                  onChange={(e) => setManualScript(e.target.value)}
                  disabled={!!videoId}
                />
              </div>
              <div>
                <label className="label">Тема видео (необязательно, для заголовка/памяти)</label>
                <textarea
                  className="input min-h-[60px]"
                  placeholder="Короткое описание темы — поможет с заголовком и анализом…"
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  disabled={!!videoId}
                />
              </div>
            </>
          )}
          <div className="space-y-2">
            <Checkbox
              label={`Перевести на экспортные языки (${
                project?.languages_export.join(", ").toUpperCase() || "нет"
              })`}
              checked={runTranslate}
              onChange={setRunTranslate}
              disabled={!!videoId || !project?.languages_export.length}
            />
            <Checkbox label="Озвучить (TTS)" checked={runTts} onChange={setRunTts} disabled={!!videoId} />
            <Checkbox
              label="AI-визуальный ряд (картинки по контексту, меняются каждые ~3 мин)"
              checked={runVisuals}
              onChange={setRunVisuals}
              disabled={!!videoId}
            />
            <Checkbox
              label="Собрать обложку и финальный mp4"
              checked={runRender}
              onChange={setRunRender}
              disabled={!!videoId}
            />
          </div>
          {runVisuals && (
            <p className="text-xs text-muted">
              Нужен ключ REPLICATE_API_TOKEN в .env (платно, ~$0.003 за картинку). Без него стадия
              просто пропустится, рендер будет со статичной обложкой.
            </p>
          )}

          {!videoId ? (
            <button
              className="btn-primary w-full"
              disabled={!canSubmit || create.isPending || createBatch.isPending}
              onClick={() =>
                batchMode && scriptMode === "generate" ? createBatch.mutate() : create.mutate()
              }
            >
              {createBatch.isPending
                ? `Создаю видео (${batchTopics.length})…`
                : create.isPending
                  ? "Запуск…"
                  : batchMode && scriptMode === "generate"
                    ? `Запустить ${batchTopics.length} видео по очереди`
                    : "Запустить пайплайн"}
            </button>
          ) : (
            <button
              className="btn-ghost w-full"
              disabled={!done}
              onClick={() => navigate(`/videos/${videoId}`)}
            >
              {done ? "Открыть видео →" : "Генерация идёт…"}
            </button>
          )}
          {create.isError && (
            <div className="text-sm text-red-400">{(create.error as Error).message}</div>
          )}
          {createBatch.isError && (
            <div className="text-sm text-red-400">{(createBatch.error as Error).message}</div>
          )}
        </div>

        <div>
          {videoId ? (
            <PipelineLog events={events} done={done} />
          ) : (
            <div className="card text-sm text-muted">
              Лог генерации появится здесь после запуска пайплайна.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PromptField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <details className="rounded-md border border-border bg-surface2/40">
      <summary className="cursor-pointer px-2 py-1.5 text-xs font-medium">{label}</summary>
      <textarea
        className="input m-2 min-h-[180px] font-mono text-[11px] leading-relaxed"
        style={{ width: "calc(100% - 1rem)" }}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </details>
  );
}

function Checkbox({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-indigo-600"
      />
      <span className={disabled ? "text-muted" : ""}>{label}</span>
    </label>
  );
}
