import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Save } from "lucide-react";
import { api } from "../lib/api";
import type { ScriptTemplate, VoiceParams } from "../lib/types";

const LANGS = ["ru", "en", "es", "fr", "de", "it", "pt", "ja", "zh", "hi"];

export default function Settings() {
  const { data: templates } = useQuery({ queryKey: ["templates"], queryFn: api.listTemplates });

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-1 text-2xl font-bold">Настройки</h1>
      <p className="mb-6 text-sm text-muted">
        Глобальные настройки приложения: голоса озвучки по умолчанию и шаблоны генерации сценария.
      </p>

      <h2 className="mb-2 text-lg font-semibold">Голоса по умолчанию</h2>
      <p className="mb-3 text-sm text-muted">
        Используются при озвучке, когда голос не задан ни у видео, ни у канала. Самый низкий
        приоритет: видео → канал → этот глобальный дефолт.
      </p>
      <DefaultVoicesSection />

      <h2 className="mb-2 mt-8 text-lg font-semibold">Живость голоса</h2>
      <p className="mb-3 text-sm text-muted">
        Глобальные параметры озвучки — применяются ко всем каналам и языкам. Делают голос
        спокойнее и «человечнее»: медленный темп, паузы между фразами и тёплая обработка звука.
        Прослушать результат можно кнопкой ▶ у любого голоса на странице «Голоса».
      </p>
      <VoiceParamsSection />

      <h2 className="mb-2 mt-8 text-lg font-semibold">Шаблоны сценария</h2>
      <p className="mb-3 text-sm text-muted">
        3-шаговая генерация: пользователь задаёт только тему — ИИ переписывает эти шаблоны под неё
        (свои клише, свои боли аудитории), затем по цепочке генерирует сценарий: подготовка →
        написание → аудит. Шаблоны на английском, общие для всех каналов.
      </p>
      <div className="space-y-3">
        {templates?.map((t) => (
          <TemplateEditor key={t.name} tpl={t} />
        ))}
        {!templates && <div className="text-sm text-muted">Загрузка…</div>}
      </div>
    </div>
  );
}

function DefaultVoicesSection() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({ queryKey: ["appSettings"], queryFn: api.getSettings });
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: () => api.listVoices() });
  const [map, setMap] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settings) setMap(settings.default_voices ?? {});
  }, [settings]);

  const save = useMutation({
    mutationFn: () => api.saveSettings({ default_voices: map }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["appSettings"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  // Показываем языки, для которых есть голоса в библиотеке (или уже выбран дефолт)
  const langsWithVoices = LANGS.filter(
    (l) => (voices ?? []).some((v) => v.language === l) || map[l]
  );

  return (
    <div className="card max-w-2xl space-y-3">
      {(voices ?? []).length === 0 ? (
        <p className="text-sm text-muted">
          Нет сохранённых голосов — добавьте их на странице{" "}
          <Link to="/voices" className="text-indigo-400 hover:underline">
            «Голоса»
          </Link>
          .
        </p>
      ) : (
        <div className="space-y-2">
          {langsWithVoices.map((l) => {
            const options = (voices ?? []).filter((v) => v.language === l);
            const current = map[l] ?? "";
            const matches = options.some((v) => v.voice_id === current);
            return (
              <div key={l} className="flex items-center gap-2">
                <span className="w-10 text-sm text-muted">{l.toUpperCase()}</span>
                <select
                  className="input"
                  value={current}
                  onChange={(e) => setMap((m) => ({ ...m, [l]: e.target.value }))}
                >
                  <option value="">— не задан —</option>
                  {options.map((v) => (
                    <option key={v.id} value={v.voice_id}>
                      {v.name} ({v.voice_id})
                    </option>
                  ))}
                  {current && !matches && <option value={current}>{current} (произвольный)</option>}
                </select>
              </div>
            );
          })}
        </div>
      )}
      <div className="flex items-center gap-3">
        <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Сохраняем…" : "Сохранить"}
        </button>
        {saved && <span className="text-sm text-emerald-400">Сохранено</span>}
        <Link to="/voices" className="ml-auto text-xs text-indigo-400 hover:underline">
          Управление голосами →
        </Link>
      </div>
    </div>
  );
}

const PARAM_DEFAULTS: VoiceParams = {
  speed: 0.95,
  pitch: 0,
  sentence_pause_ms: 160,
  paragraph_pause_ms: 650,
  post_process: true,
  warmth: 0.35,
};

function VoiceParamsSection() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({ queryKey: ["appSettings"], queryFn: api.getSettings });
  const [p, setP] = useState<VoiceParams>(PARAM_DEFAULTS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settings?.voice_params) setP({ ...PARAM_DEFAULTS, ...settings.voice_params });
  }, [settings]);

  const save = useMutation({
    mutationFn: () => api.saveSettings({ voice_params: p }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["appSettings"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });
  const reset = useMutation({
    mutationFn: () => api.resetVoiceParams(),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["appSettings"] });
      if (data?.voice_params) setP({ ...PARAM_DEFAULTS, ...data.voice_params });
    },
  });

  const set = <K extends keyof VoiceParams>(k: K, v: VoiceParams[K]) =>
    setP((prev) => ({ ...prev, [k]: v }));

  return (
    <div className="card max-w-2xl space-y-4">
      <Slider
        label="Темп речи"
        value={p.speed}
        min={0.5}
        max={1.3}
        step={0.01}
        onChange={(v) => set("speed", v)}
        fmt={(v) => `${v.toFixed(2)}× ${v < 0.9 ? "(медленно)" : v > 1.1 ? "(быстро)" : ""}`}
      />
      <Slider
        label="Высота тона (только Edge)"
        value={p.pitch}
        min={-6}
        max={6}
        step={1}
        onChange={(v) => set("pitch", Math.round(v))}
        fmt={(v) => (v === 0 ? "0 (норма)" : `${v > 0 ? "+" : ""}${v} полутон.`)}
      />
      <Slider
        label="Пауза между предложениями"
        value={p.sentence_pause_ms}
        min={0}
        max={800}
        step={20}
        onChange={(v) => set("sentence_pause_ms", Math.round(v))}
        fmt={(v) => `${v} мс`}
      />
      <Slider
        label="Пауза между абзацами"
        value={p.paragraph_pause_ms}
        min={0}
        max={2000}
        step={50}
        onChange={(v) => set("paragraph_pause_ms", Math.round(v))}
        fmt={(v) => `${v} мс`}
      />
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={p.post_process}
          onChange={(e) => set("post_process", e.target.checked)}
        />
        Тёплая обработка звука (компрессия + мягкий EQ + лёгкая реверберация)
      </label>
      {p.post_process && (
        <Slider
          label="Теплота / реверберация"
          value={p.warmth}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => set("warmth", v)}
          fmt={(v) => `${Math.round(v * 100)}%`}
        />
      )}
      <div className="flex items-center gap-3 pt-1">
        <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Сохраняем…" : "Сохранить"}
        </button>
        <button
          className="btn-ghost text-xs"
          disabled={reset.isPending}
          onClick={() => reset.mutate()}
        >
          <RotateCcw size={13} /> Сброс
        </button>
        {saved && <span className="text-sm text-emerald-400">Сохранено</span>}
      </div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  fmt,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  fmt: (v: number) => string;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted">{fmt(value)}</span>
      </div>
      <input
        type="range"
        className="w-full"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
    </div>
  );
}

function TemplateEditor({ tpl }: { tpl: ScriptTemplate }) {
  const qc = useQueryClient();
  const [content, setContent] = useState(tpl.content);
  const [open, setOpen] = useState(false);

  // Подхватываем серверное значение после сохранения/сброса
  useEffect(() => setContent(tpl.content), [tpl.content]);

  const save = useMutation({
    mutationFn: () => api.saveTemplate(tpl.name, content),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
  const reset = useMutation({
    mutationFn: () => api.resetTemplate(tpl.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });

  const dirty = content !== tpl.content;

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <button
          className="flex items-center gap-2 text-left text-sm font-medium"
          onClick={() => setOpen((o) => !o)}
        >
          <span className="text-muted">{open ? "▾" : "▸"}</span>
          {tpl.title}
          {tpl.overridden && (
            <span className="rounded bg-amber-900/40 px-1.5 py-0.5 text-[10px] text-amber-300">
              изменён
            </span>
          )}
        </button>
        <div className="flex gap-2">
          {tpl.overridden && (
            <button
              className="btn-ghost text-xs"
              disabled={reset.isPending}
              onClick={() => {
                if (confirm("Сбросить шаблон к стандартному?")) reset.mutate();
              }}
            >
              <RotateCcw size={13} /> Сброс
            </button>
          )}
          <button
            className="btn-primary text-xs"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            <Save size={13} /> {save.isPending ? "Сохраняю…" : "Сохранить"}
          </button>
        </div>
      </div>

      {open && (
        <textarea
          className="input mt-3 min-h-[320px] w-full font-mono text-[11px] leading-relaxed"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
      )}
      {(save.isError || reset.isError) && (
        <div className="mt-2 text-xs text-red-400">
          {((save.error || reset.error) as Error).message}
        </div>
      )}
    </div>
  );
}
