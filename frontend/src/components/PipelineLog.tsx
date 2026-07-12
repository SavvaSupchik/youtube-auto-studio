import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import type { JobEvent } from "../lib/useJobSocket";
import type { GenLog } from "../lib/types";

const STAGE_LABELS: Record<string, string> = {
  script: "Генерация сценария",
  "script:adapt": "Адаптация промтов",
  "script:prep": "Бриф",
  "script:write": "Черновик",
  "script:humanize": "Очеловечивание",
  analysis: "Анализ сценария",
  thumbnail: "Обложка",
  stats: "Обновление статистики",
  visuals: "Визуальный ряд (AI)",
};

export function stageLabel(stage: string): string {
  if (stage.startsWith("translate:")) return `Перевод → ${stage.split(":")[1].toUpperCase()}`;
  if (stage.startsWith("tts:")) return `Озвучка ${stage.split(":")[1].toUpperCase()}`;
  if (stage.startsWith("render:")) return `Рендер ${stage.split(":")[1].toUpperCase()}`;
  return STAGE_LABELS[stage] ?? stage;
}

function fmtSec(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

/** Парсим timestamp из БД как UTC — сервер хранит без суффикса Z,
 *  JS без него трактует строку как местное время → неверный elapsed. */
function toUtcMs(ts: string): number {
  // Если уже есть Z или +offset — парсим как есть, иначе добавляем Z
  const hasOffset = /Z|[+-]\d{2}:?\d{2}$/.test(ts);
  const normalized = hasOffset ? ts : ts + "Z";
  const ms = new Date(normalized).getTime();
  if (import.meta.env.DEV) {
    console.debug("[PipelineLog] toUtcMs", {
      raw: ts,
      normalized,
      elapsedSec: `${((Date.now() - ms) / 1000).toFixed(1)}s`,
    });
  }
  return ms;
}

/** Живой таймер для стадии в статусе "running". */
function ElapsedTimer({ since }: { since: string }) {
  const [elapsed, setElapsed] = useState(() => (Date.now() - toUtcMs(since)) / 1000);
  useEffect(() => {
    const id = setInterval(() => {
      setElapsed((Date.now() - toUtcMs(since)) / 1000);
    }, 1000);
    return () => clearInterval(id);
  }, [since]);
  return <span className="text-amber-400">{fmtSec(Math.max(0, elapsed))}</span>;
}

/**
 * Единая панель прогресса: берёт записи из БД (logs) как основу и дополняет
 * живыми WS-событиями текущей сессии (events). Работает и после перезагрузки
 * страницы (из logs), и в реальном времени во время генерации (из events).
 */
export function PipelineLog({
  logs,
  events,
  done,
}: {
  logs?: GenLog[];
  events: JobEvent[];
  done: boolean;
}) {
  // Строим карту stage → {status, duration_sec, created_at} из БД
  type StageState = {
    status: "running" | "ok" | "error";
    duration_sec: number | null;
    created_at: string;
    error_message: string | null;
  };
  const stageMap = new Map<string, StageState>();

  for (const log of logs ?? []) {
    stageMap.set(log.stage, {
      status: log.status as "running" | "ok" | "error",
      duration_sec: log.duration_sec,
      created_at: log.created_at,
      error_message: log.error_message,
    });
  }

  // Накладываем живые WS-события (могут опережать БД на 1-2 сек)
  let pipelineError: string | null = null;
  for (const e of events) {
    if (e.type === "stage_start" && e.stage) {
      const prev = stageMap.get(e.stage);
      // Сохраняем created_at только если предыдущая запись тоже "running" —
      // чтобы таймер не прыгал при кратком расхождении WS и DB.
      // Если предыдущая запись "error" или "ok" — берём текущее время (новый запуск).
      const isResume = prev?.status === "running";
      const created_at = isResume ? prev.created_at : new Date().toISOString();
      if (import.meta.env.DEV) {
        console.debug("[PipelineLog] WS stage_start", {
          stage: e.stage,
          prevStatus: prev?.status ?? "none",
          isResume,
          created_at,
        });
      }
      stageMap.set(e.stage, {
        status: "running",
        duration_sec: null,
        created_at,
        error_message: null,
      });
    }
    if (e.type === "stage_done" && e.stage) {
      const prev = stageMap.get(e.stage);
      stageMap.set(e.stage, {
        status: "ok",
        duration_sec: e.duration_sec ?? prev?.duration_sec ?? null,
        created_at: prev?.created_at ?? new Date().toISOString(),
        error_message: null,
      });
    }
    if (e.type === "stage_error" && e.stage) {
      const prev = stageMap.get(e.stage);
      stageMap.set(e.stage, {
        status: "error",
        duration_sec: prev?.duration_sec ?? null,
        created_at: prev?.created_at ?? new Date().toISOString(),
        error_message: e.error ?? "Ошибка",
      });
    }
    if (e.type === "pipeline_error") pipelineError = e.error ?? "Ошибка пайплайна";
  }

  const entries = Array.from(stageMap.entries());
  const hasAny = entries.length > 0;
  const isActive = entries.some(([, s]) => s.status === "running");

  return (
    <div className="card">
      <h3 className="mb-3 text-sm font-medium">Прогресс генерации</h3>

      {!hasAny && !done && (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="animate-spin" size={16} /> Ожидание запуска…
        </div>
      )}

      <div className="space-y-1.5">
        {entries.map(([stage, s]) => (
          <div key={stage} className="flex items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-1.5">
              {s.status === "running" && (
                <Loader2 className="shrink-0 animate-spin text-amber-400" size={14} />
              )}
              {s.status === "ok" && (
                <CheckCircle2 className="shrink-0 text-emerald-400" size={14} />
              )}
              {s.status === "error" && (
                <XCircle className="shrink-0 text-red-400" size={14} />
              )}
              <span className={s.status === "error" ? "text-red-300" : "text-gray-200"}>
                {stageLabel(stage)}
              </span>
            </div>

            <span className="shrink-0 tabular-nums text-muted">
              {s.status === "running" ? (
                <ElapsedTimer since={s.created_at} />
              ) : s.duration_sec != null ? (
                fmtSec(s.duration_sec)
              ) : null}
            </span>
          </div>
        ))}
      </div>

      {/* Сообщения об ошибках под списком */}
      {entries
        .filter(([, s]) => s.status === "error" && s.error_message)
        .map(([stage, s]) => (
          <div
            key={`err-${stage}`}
            className="mt-1 rounded bg-red-950/40 px-2 py-1 text-[11px] text-red-300"
          >
            {stageLabel(stage)}: {s.error_message}
          </div>
        ))}

      {pipelineError && (
        <div className="mt-2 rounded-lg bg-red-950/40 p-2 text-xs text-red-300">
          {pipelineError}
        </div>
      )}

      {done && !isActive && !pipelineError && hasAny && (
        <div className="mt-2 text-xs text-emerald-400">Готово ✓</div>
      )}
    </div>
  );
}
