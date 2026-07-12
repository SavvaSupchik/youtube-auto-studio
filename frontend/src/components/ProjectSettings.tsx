import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { MusicTrack, Project } from "../lib/types";
import { api } from "../lib/api";

const LANGS = ["ru", "en", "es", "fr", "de", "it", "pt", "ja", "zh", "hi"];

export function ProjectSettings({ project }: { project: Project }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<Project>(project);
  const [saved, setSaved] = useState(false);
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: () => api.listVoices() });
  const { data: musicTracks } = useQuery({ queryKey: ["music"], queryFn: () => api.listMusic() });

  const save = useMutation({
    mutationFn: () =>
      api.updateProject(project.id, {
        name: form.name,
        niche: form.niche,
        description: form.description,
        target_audience: form.target_audience,
        style_prompt: form.style_prompt,
        language_primary: form.language_primary,
        languages_export: form.languages_export,
        voice_settings: form.voice_settings,
        tts_mode: form.tts_mode,
        accent_color: form.accent_color,
        particles_enabled: form.particles_enabled,
        default_music_track_id: form.default_music_track_id,
        default_music_volume: form.default_music_volume,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", project.id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const set = (k: keyof Project, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const toggleExport = (l: string) =>
    set(
      "languages_export",
      form.languages_export.includes(l)
        ? form.languages_export.filter((x) => x !== l)
        : [...form.languages_export, l]
    );
  const setVoice = (lang: string, voice: string) =>
    set("voice_settings", { ...form.voice_settings, [lang]: voice });

  const allLangs = [form.language_primary, ...form.languages_export];

  return (
    <div className="max-w-2xl space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Название</label>
          <input className="input" value={form.name} onChange={(e) => set("name", e.target.value)} />
        </div>
        <div>
          <label className="label">Ниша</label>
          <input className="input" value={form.niche} onChange={(e) => set("niche", e.target.value)} />
        </div>
      </div>
      <div>
        <label className="label">Целевая аудитория</label>
        <input
          className="input"
          value={form.target_audience}
          onChange={(e) => set("target_audience", e.target.value)}
        />
      </div>
      <div>
        <label className="label">Style prompt</label>
        <textarea
          className="input min-h-[120px]"
          value={form.style_prompt}
          onChange={(e) => set("style_prompt", e.target.value)}
        />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="label">Основной язык</label>
          <select
            className="input"
            value={form.language_primary}
            onChange={(e) => set("language_primary", e.target.value)}
          >
            {LANGS.map((l) => (
              <option key={l} value={l}>
                {l.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Режим TTS</label>
          <select
            className="input"
            value={form.tts_mode}
            onChange={(e) => set("tts_mode", e.target.value)}
          >
            <option value="local">Локально</option>
            <option value="manual">Вручную</option>
          </select>
        </div>
        <div>
          <label className="label">Цвет</label>
          <input
            type="color"
            className="input h-10 p-1"
            value={form.accent_color}
            onChange={(e) => set("accent_color", e.target.value)}
          />
        </div>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.particles_enabled}
          onChange={(e) => set("particles_enabled", e.target.checked)}
          className="h-4 w-4 accent-indigo-600"
        />
        <span>Частицы (искры огня) по умолчанию — для видео, где огоньки не выбраны в параметрах монтажа</span>
      </label>
      <div>
        <label className="label">Экспортные языки</label>
        <div className="flex flex-wrap gap-2">
          {LANGS.filter((l) => l !== form.language_primary).map((l) => (
            <button
              key={l}
              onClick={() => toggleExport(l)}
              className={`rounded-lg px-2.5 py-1 text-xs ${
                form.languages_export.includes(l)
                  ? "bg-indigo-600 text-white"
                  : "bg-surface2 text-muted hover:bg-border"
              }`}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className="label mb-0">Голоса под язык</label>
          <Link to="/voices" className="text-xs text-indigo-400 hover:underline">
            Управление голосами →
          </Link>
        </div>
        <div className="space-y-2">
          {allLangs.map((l) => {
            const options = (voices ?? []).filter((v) => v.language === l);
            const current = form.voice_settings[l] ?? "";
            const matches = options.some((v) => v.voice_id === current);
            return (
              <div key={l} className="flex items-center gap-2">
                <span className="w-10 text-sm text-muted">{l.toUpperCase()}</span>
                <select
                  className="input"
                  value={current}
                  onChange={(e) => setVoice(l, e.target.value)}
                >
                  <option value="">— не выбран —</option>
                  {options.map((v) => (
                    <option key={v.id} value={v.voice_id}>
                      {v.name} ({v.voice_id})
                    </option>
                  ))}
                  {current && !matches && (
                    <option value={current}>{current} (произвольный)</option>
                  )}
                </select>
              </div>
            );
          })}
        </div>
        {(voices ?? []).length === 0 && (
          <p className="mt-1 text-xs text-muted">
            Нет сохранённых голосов — добавьте их на странице{" "}
            <Link to="/voices" className="text-indigo-400 hover:underline">
              «Голоса»
            </Link>
            .
          </p>
        )}
      </div>

      {/* Музыка по умолчанию */}
      <div className="space-y-2">
        <label className="label">Фоновая музыка по умолчанию</label>
        <select
          className="input"
          value={form.default_music_track_id ?? ""}
          onChange={(e) => set("default_music_track_id", e.target.value || null)}
        >
          <option value="">— без музыки —</option>
          {(musicTracks ?? [])
            .filter((t: MusicTrack) => t.status === "ready")
            .map((t: MusicTrack) => (
              <option key={t.id} value={t.id}>
                {t.title || "Без названия"}
              </option>
            ))}
        </select>
        {form.default_music_track_id && (
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted w-24 shrink-0">
              Громкость: {Math.round(form.default_music_volume * 100)}%
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={form.default_music_volume}
              onChange={(e) => set("default_music_volume", parseFloat(e.target.value))}
              className="flex-1"
            />
          </div>
        )}
        <p className="text-xs text-muted">
          Будет автоматически применяться ко всем новым видео канала
        </p>
      </div>

      <div className="flex items-center gap-3">
        <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Сохраняем…" : "Сохранить"}
        </button>
        {saved && <span className="text-sm text-emerald-400">Сохранено</span>}
      </div>
    </div>
  );
}
