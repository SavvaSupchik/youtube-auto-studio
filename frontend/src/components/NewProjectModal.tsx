import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { api } from "../lib/api";

const LANGS = ["ru", "en", "es", "fr", "de", "it", "pt", "ja", "zh", "hi"];

export function NewProjectModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [niche, setNiche] = useState("");
  const [audience, setAudience] = useState("");
  const [style, setStyle] = useState("");
  const [primary, setPrimary] = useState("ru");
  const [exports, setExports] = useState<string[]>([]);
  const [accent, setAccent] = useState("#6366f1");
  const [ttsMode, setTtsMode] = useState("local");

  const create = useMutation({
    mutationFn: () =>
      api.createProject({
        name,
        niche,
        target_audience: audience,
        style_prompt: style,
        language_primary: primary,
        languages_export: exports,
        accent_color: accent,
        tts_mode: ttsMode,
      }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onClose();
      navigate(`/projects/${p.id}`);
    },
  });

  const toggleExport = (l: string) =>
    setExports((e) => (e.includes(l) ? e.filter((x) => x !== l) : [...e, l]));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="card w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Новый канал</h2>
          <button onClick={onClose} className="text-muted hover:text-white">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="label">Название *</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Ниша</label>
              <input className="input" value={niche} onChange={(e) => setNiche(e.target.value)} />
            </div>
            <div>
              <label className="label">Акцентный цвет</label>
              <input
                type="color"
                className="input h-10 p-1"
                value={accent}
                onChange={(e) => setAccent(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="label">Целевая аудитория</label>
            <input
              className="input"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Style prompt (тон, стиль канала)</label>
            <textarea
              className="input min-h-[80px]"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Основной язык</label>
              <select className="input" value={primary} onChange={(e) => setPrimary(e.target.value)}>
                {LANGS.map((l) => (
                  <option key={l} value={l}>
                    {l.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Режим озвучки</label>
              <select className="input" value={ttsMode} onChange={(e) => setTtsMode(e.target.value)}>
                <option value="local">Локально (Kokoro)</option>
                <option value="manual">Вручную</option>
              </select>
            </div>
          </div>
          <div>
            <label className="label">Экспортные языки</label>
            <div className="flex flex-wrap gap-2">
              {LANGS.filter((l) => l !== primary).map((l) => (
                <button
                  key={l}
                  onClick={() => toggleExport(l)}
                  className={`rounded-lg px-2.5 py-1 text-xs ${
                    exports.includes(l)
                      ? "bg-indigo-600 text-white"
                      : "bg-surface2 text-muted hover:bg-border"
                  }`}
                >
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>

        {create.isError && (
          <div className="mt-3 text-sm text-red-400">{(create.error as Error).message}</div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>
            Отмена
          </button>
          <button
            className="btn-primary"
            disabled={!name || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Создаём…" : "Создать"}
          </button>
        </div>
      </div>
    </div>
  );
}
