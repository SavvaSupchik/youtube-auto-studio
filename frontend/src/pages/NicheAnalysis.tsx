import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Radar,
  Search,
  Telescope,
  TrendingUp,
  TrendingDown,
  Minus,
  Trash2,
  ExternalLink,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { api } from "../lib/api";
import type {
  DeepDiveResult,
  NicheMetrics,
  NicheReport,
  ScanResult,
} from "../lib/types";

// ---- утилиты форматирования ----
function fmtNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

function scoreColor(score: number): string {
  if (score >= 65) return "bg-emerald-500";
  if (score >= 45) return "bg-yellow-500";
  return "bg-red-500";
}

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-surface2">
        <div
          className={`h-full ${scoreColor(score)}`}
          style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
        />
      </div>
      <span className="w-9 text-right text-sm font-semibold tabular-nums">{score}</span>
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface2 p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted">{hint}</div>}
    </div>
  );
}

// ===========================================================================
export default function NicheAnalysis() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"scan" | "deep">("scan");

  const { data: status } = useQuery({ queryKey: ["niche-status"], queryFn: api.nicheStatus });
  const { data: reports = [] } = useQuery({
    queryKey: ["niche-reports"],
    queryFn: () => api.listNicheReports(),
  });

  // общие поля региона/языка
  const [region, setRegion] = useState("");
  const [language, setLanguage] = useState("");

  // текущие показываемые отчёты (из свежей мутации или открытые из истории)
  const [scanReport, setScanReport] = useState<NicheReport | null>(null);
  const [deepReport, setDeepReport] = useState<NicheReport | null>(null);

  // --- скан ---
  const [seed, setSeed] = useState("");
  const [maxNiches, setMaxNiches] = useState(8);
  const scanMut = useMutation({
    mutationFn: () =>
      api.nicheScan({
        seed,
        region: region || undefined,
        language: language || undefined,
        max_niches: maxNiches,
      }),
    onSuccess: (rep) => {
      setScanReport(rep);
      qc.invalidateQueries({ queryKey: ["niche-reports"] });
    },
  });

  // --- глубокий разбор ---
  const [keyword, setKeyword] = useState("");
  const deepMut = useMutation({
    mutationFn: (kw: string) =>
      api.nicheDeepDive({ keyword: kw, region: region || undefined, language: language || undefined }),
    onSuccess: (rep) => {
      setDeepReport(rep);
      qc.invalidateQueries({ queryKey: ["niche-reports"] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteNicheReport(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["niche-reports"] }),
  });

  // разобрать нишу из скана → переключаемся на вкладку разбора
  const analyzeFromScan = (kw: string) => {
    setKeyword(kw);
    setTab("deep");
    deepMut.mutate(kw);
  };

  // открыть сохранённый отчёт из истории
  const openReport = (r: NicheReport) => {
    if (r.kind === "scan") {
      setScanReport(r);
      setSeed(r.query);
      setTab("scan");
    } else {
      setDeepReport(r);
      setKeyword(r.query);
      setTab("deep");
    }
  };

  const scanResult = scanReport?.payload as ScanResult | undefined;
  const deepResult = deepReport?.payload as DeepDiveResult | undefined;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex items-center gap-2">
        <Radar size={24} className="text-indigo-400" />
        <h1 className="text-2xl font-bold">Анализ ниш YouTube</h1>
      </div>
      <p className="text-sm text-muted">
        Ищем недосыщенные темы — где <b className="text-gray-200">спрос высокий, а предложение слабое</b>.
        Главный сигнал — <b className="text-gray-200">Outlier Ratio</b>: маленькие каналы стабильно
        собирают большие просмотры → алгоритм показывает их за неимением крупных.
      </p>

      {/* Баннер настройки ключа */}
      {status && !status.youtube_configured && (
        <div className="card border-yellow-500/40 bg-yellow-500/5">
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-yellow-400" />
            <div className="space-y-1 text-sm">
              <p className="font-medium text-yellow-300">Не задан YOUTUBE_API_KEY</p>
              <p className="text-muted">
                Получите бесплатный ключ:{" "}
                <a
                  className="text-indigo-400 hover:underline"
                  href="https://console.cloud.google.com/apis/library/youtube.googleapis.com"
                  target="_blank"
                  rel="noreferrer"
                >
                  включите «YouTube Data API v3»
                </a>{" "}
                → Credentials → API key, впишите в{" "}
                <code className="rounded bg-surface2 px-1 text-xs">.env</code> и перезапустите backend.
                Бесплатная квота 10 000 units/день (~90 поисков).
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Табы */}
      <div className="flex gap-1 border-b border-border">
        <TabButton active={tab === "scan"} onClick={() => setTab("scan")} icon={<Search size={15} />}>
          Скан ниш
        </TabButton>
        <TabButton active={tab === "deep"} onClick={() => setTab("deep")} icon={<Telescope size={15} />}>
          Глубокий разбор
        </TabButton>
      </div>

      {/* Общие параметры */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-24">
          <label className="label">Регион</label>
          <input
            className="input"
            placeholder={status?.region_default ?? "RU"}
            value={region}
            onChange={(e) => setRegion(e.target.value.toUpperCase().slice(0, 2))}
          />
        </div>
        <div className="w-24">
          <label className="label">Язык</label>
          <input
            className="input"
            placeholder={status?.language_default ?? "ru"}
            value={language}
            onChange={(e) => setLanguage(e.target.value.toLowerCase().slice(0, 2))}
          />
        </div>
      </div>

      {/* ---- ВКЛАДКА: СКАН ---- */}
      {tab === "scan" && (
        <div className="space-y-4">
          <div className="card space-y-3">
            <div>
              <label className="label">Широкая тема / интерес</label>
              <input
                className="input"
                placeholder="напр. личные финансы, саморазвитие, ретро-игры"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && seed.trim() && scanMut.mutate()}
              />
            </div>
            <div className="flex items-end gap-3">
              <div className="w-40">
                <label className="label">Сколько под-ниш ({maxNiches})</label>
                <input
                  type="range"
                  min={3}
                  max={12}
                  value={maxNiches}
                  onChange={(e) => setMaxNiches(Number(e.target.value))}
                  className="w-full accent-indigo-500"
                />
              </div>
              <button
                className="btn-primary ml-auto"
                disabled={!seed.trim() || scanMut.isPending || !status?.youtube_configured}
                onClick={() => scanMut.mutate()}
              >
                {scanMut.isPending ? (
                  <>
                    <Loader2 size={15} className="animate-spin" /> Сканируем…
                  </>
                ) : (
                  <>
                    <Search size={15} /> Сканировать
                  </>
                )}
              </button>
            </div>
            <p className="text-[11px] text-muted">
              LLM предложит {maxNiches} узких под-ниш, затем каждая замеряется по YouTube Data API
              (~{maxNiches * 100} units квоты). Занимает 10–30 с.
            </p>
          </div>

          {scanMut.error && <ErrorBox error={scanMut.error} />}

          {scanResult && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-muted">
                <span>
                  «{scanResult.seed}» · {scanResult.region}/{scanResult.language}
                </span>
                <span>{scanResult.quota_note}</span>
              </div>
              <NicheTable niches={scanResult.niches} onAnalyze={analyzeFromScan} />
            </div>
          )}
        </div>
      )}

      {/* ---- ВКЛАДКА: РАЗБОР ---- */}
      {tab === "deep" && (
        <div className="space-y-4">
          <div className="card flex items-end gap-3">
            <div className="flex-1">
              <label className="label">Ниша / поисковый запрос</label>
              <input
                className="input"
                placeholder="напр. инвестиции в дивидендные акции для новичков"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && keyword.trim() && deepMut.mutate(keyword)}
              />
            </div>
            <button
              className="btn-primary"
              disabled={!keyword.trim() || deepMut.isPending || !status?.youtube_configured}
              onClick={() => deepMut.mutate(keyword)}
            >
              {deepMut.isPending ? (
                <>
                  <Loader2 size={15} className="animate-spin" /> Разбираем…
                </>
              ) : (
                <>
                  <Telescope size={15} /> Разобрать
                </>
              )}
            </button>
          </div>

          {deepMut.error && <ErrorBox error={deepMut.error} />}
          {deepResult && <DeepView data={deepResult} />}
        </div>
      )}

      {/* ---- ИСТОРИЯ ---- */}
      {reports.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-muted">История отчётов</h2>
          <div className="space-y-1.5">
            {reports.map((r) => (
              <ReportRow
                key={r.id}
                report={r}
                onOpen={() => openReport(r)}
                onDelete={() => deleteMut.mutate(r.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---- подкомпоненты ----
function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? "border-indigo-500 text-white"
          : "border-transparent text-muted hover:text-gray-200"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="card border-red-500/40 bg-red-500/5 text-sm text-red-300">
      {String(error instanceof Error ? error.message : error)}
    </div>
  );
}

function NicheTable({
  niches,
  onAnalyze,
}: {
  niches: NicheMetrics[];
  onAnalyze: (kw: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface2 text-left text-xs text-muted">
          <tr>
            <th className="px-3 py-2">Ниша</th>
            <th className="px-3 py-2">Score</th>
            <th className="px-3 py-2" title="Медианные просмотры ÷ медианные подписчики">
              Outlier
            </th>
            <th className="px-3 py-2" title="Медианные просмотры топ-видео">
              Просм.
            </th>
            <th className="px-3 py-2" title="Медианные подписчики каналов">
              Подп.
            </th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {niches.map((n, i) => (
            <tr key={i} className="border-t border-border hover:bg-surface2/50">
              <td className="px-3 py-2">
                <div className="font-medium">{n.keyword}</div>
                {n.error ? (
                  <div className="text-xs text-red-400">{n.error}</div>
                ) : (
                  n.rationale && <div className="text-xs text-muted">{n.rationale}</div>
                )}
              </td>
              {n.error ? (
                <td colSpan={4} className="px-3 py-2 text-xs text-muted">
                  замер не выполнен
                </td>
              ) : (
                <>
                  <td className="px-3 py-2">
                    <ScoreBar score={n.opportunity_score} />
                  </td>
                  <td className="px-3 py-2 tabular-nums">{n.outlier_ratio}×</td>
                  <td className="px-3 py-2 tabular-nums">{fmtNum(n.median_views)}</td>
                  <td className="px-3 py-2 tabular-nums">{fmtNum(n.median_subs)}</td>
                  <td className="px-3 py-2">
                    <button
                      className="btn-ghost px-2 py-1 text-xs"
                      onClick={() => onAnalyze(n.keyword)}
                    >
                      Разобрать
                    </button>
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TrendIcon({ direction }: { direction: string }) {
  if (direction === "растёт") return <TrendingUp size={16} className="text-emerald-400" />;
  if (direction === "падает") return <TrendingDown size={16} className="text-red-400" />;
  return <Minus size={16} className="text-muted" />;
}

function verdictColor(v: string): string {
  if (v.includes("заходить")) return "border-emerald-500/50 bg-emerald-500/5";
  if (v.includes("осторож")) return "border-yellow-500/50 bg-yellow-500/5";
  if (v.includes("не стоит")) return "border-red-500/50 bg-red-500/5";
  return "border-border";
}

function DeepView({ data }: { data: DeepDiveResult }) {
  const m = data.metrics;
  const v = data.verdict;
  return (
    <div className="space-y-4">
      {/* Вердикт */}
      <div className={`card space-y-2 ${verdictColor(v.verdict)}`}>
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold capitalize">{v.verdict}</span>
          <ScoreBar score={m.opportunity_score} />
        </div>
        {v.one_liner && <p className="text-sm font-medium text-gray-200">{v.one_liner}</p>}
        {v.reasoning && <p className="text-sm text-muted">{v.reasoning}</p>}
        {v.content_angles?.length > 0 && (
          <div className="pt-1">
            <div className="mb-1 text-xs font-medium text-muted">Идеи видео:</div>
            <ul className="list-inside list-disc space-y-0.5 text-sm">
              {v.content_angles.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex flex-wrap gap-3 pt-1 text-xs text-muted">
          {v.recommended_formats?.length > 0 && (
            <span>📐 {v.recommended_formats.join(" · ")}</span>
          )}
          {v.risks?.length > 0 && <span>⚠️ {v.risks.join(" · ")}</span>}
        </div>
      </div>

      {/* Метрики */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric
          label="Outlier Ratio"
          value={`${m.outlier_ratio}×`}
          hint="просмотры ÷ подписчики"
        />
        <Metric label="Медиана просмотров" value={fmtNum(m.median_views)} hint={`выборка ${m.sample_size}`} />
        <Metric label="Медиана подписчиков" value={fmtNum(m.median_subs)} />
        <Metric label="Предложение" value={fmtNum(m.total_results)} hint="видео по запросу" />
        <Metric label="Спрос" value={`${m.demand_score}`} hint="0–100" />
        <Metric label="Слабость конкур." value={`${m.supply_score}`} hint="выше = свободнее" />
        <Metric label="Свежесть" value={`${Math.round(m.share_recent_90d * 100)}%`} hint="видео за 90 дн" />
        <Metric
          label="Монополия лидера"
          value={`${Math.round(m.top_channel_dominance * 100)}%`}
          hint="доля трафика 1 канала"
        />
      </div>

      {/* Тренд */}
      <div className="card space-y-1.5">
        <div className="flex items-center gap-2 text-sm font-medium">
          <TrendIcon direction={data.trend.direction} /> Google Trends
          {data.trend.available ? (
            <span className="text-muted">
              — интерес {data.trend.direction}, уровень {data.trend.interest}/100
            </span>
          ) : (
            <span className="text-xs text-muted">— {data.trend.note}</span>
          )}
        </div>
        {data.trend.rising?.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {data.trend.rising.map((q, i) => (
              <span key={i} className="rounded-full bg-surface2 px-2 py-0.5 text-xs">
                🔥 {q}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Топ-видео */}
      {data.top_videos.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface2 text-left text-xs text-muted">
              <tr>
                <th className="px-3 py-2">Видео</th>
                <th className="px-3 py-2">Просмотры</th>
                <th className="px-3 py-2">Подписчики</th>
                <th className="px-3 py-2" title="Просмотры ÷ подписчики канала">
                  V/S
                </th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.top_videos.map((vid) => (
                <tr key={vid.video_id} className="border-t border-border hover:bg-surface2/50">
                  <td className="px-3 py-2">
                    <div className="max-w-md truncate font-medium">{vid.title}</div>
                    <div className="text-xs text-muted">{vid.channel}</div>
                  </td>
                  <td className="px-3 py-2 tabular-nums">{fmtNum(vid.views)}</td>
                  <td className="px-3 py-2 tabular-nums">{fmtNum(vid.channel_subs)}</td>
                  <td
                    className={`px-3 py-2 tabular-nums font-semibold ${
                      vid.views_to_subs >= 5 ? "text-emerald-400" : ""
                    }`}
                  >
                    {vid.views_to_subs}×
                  </td>
                  <td className="px-3 py-2">
                    <a
                      href={vid.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-muted hover:text-indigo-400"
                      title="Открыть на YouTube"
                    >
                      <ExternalLink size={14} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ReportRow({
  report,
  onOpen,
  onDelete,
}: {
  report: NicheReport;
  onOpen: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-sm">
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
          report.kind === "scan" ? "bg-indigo-500/20 text-indigo-300" : "bg-purple-500/20 text-purple-300"
        }`}
      >
        {report.kind === "scan" ? "СКАН" : "РАЗБОР"}
      </span>
      <button className="flex-1 truncate text-left hover:text-indigo-400" onClick={onOpen}>
        <span className="font-medium">{report.query}</span>
        <span className="ml-2 text-xs text-muted">{report.note}</span>
      </button>
      <span className="shrink-0 text-xs text-muted">
        {new Date(report.created_at).toLocaleDateString("ru")}
      </span>
      <button className="p-1 text-muted hover:text-red-400" onClick={onDelete} title="Удалить">
        <Trash2 size={14} />
      </button>
    </div>
  );
}
