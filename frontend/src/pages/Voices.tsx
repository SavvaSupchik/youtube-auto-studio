import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Lock, Play, Plus, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { Voice } from "../lib/types";
import { KOKORO_VOICES } from "../lib/kokoroVoices";

const LANGS = ["ru", "en", "es", "fr", "de", "it", "pt", "ja", "zh", "hi"];

const EMPTY = { name: "", language: "en", engine: "kokoro", voice_id: "", description: "" };

export default function Voices() {
  const qc = useQueryClient();
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: () => api.listVoices() });
  const [form, setForm] = useState(EMPTY);

  const create = useMutation({
    mutationFn: () => api.createVoice(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["voices"] });
      setForm(EMPTY);
    },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteVoice(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["voices"] }),
  });

  const byLang = (voices ?? []).reduce<Record<string, Voice[]>>((acc, v) => {
    (acc[v.language] ??= []).push(v);
    return acc;
  }, {});

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-1 text-2xl font-bold">Голоса</h1>
      <p className="mb-5 text-sm text-muted">
        Общая библиотека голосов для всех каналов. Создайте голос один раз, затем выбирайте его в
        настройках канала для каждого языка.
      </p>

      <div className="card mb-6">
        <h3 className="mb-3 text-sm font-medium">Новый голос</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Название</label>
            <input
              className="input"
              placeholder="напр. Глубокий мужской рассказчик"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div>
            <label className="label">Язык</label>
            <select
              className="input"
              value={form.language}
              onChange={(e) => setForm((f) => ({ ...f, language: e.target.value }))}
            >
              {LANGS.map((l) => (
                <option key={l} value={l}>
                  {l.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Движок</label>
            <select
              className="input"
              value={form.engine}
              onChange={(e) => setForm((f) => ({ ...f, engine: e.target.value }))}
            >
              <option value="kokoro">Kokoro (локальный синтез)</option>
              <option value="manual">Manual (всегда загружается вручную)</option>
            </select>
          </div>
          <div>
            <label className="label">
              {form.engine === "kokoro" ? "Voice ID (напр. af_heart)" : "Voice ID (необязательно)"}
            </label>
            <input
              className="input"
              placeholder={form.engine === "kokoro" ? "af_heart" : "любая метка"}
              value={form.voice_id}
              onChange={(e) => setForm((f) => ({ ...f, voice_id: e.target.value }))}
            />
          </div>
          <div className="col-span-2">
            <label className="label">Описание (необязательно)</label>
            <input
              className="input"
              placeholder="на что годится этот голос…"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
        </div>
        <button
          className="btn-primary mt-3"
          disabled={!form.name.trim() || (form.engine === "kokoro" && !form.voice_id.trim()) || create.isPending}
          onClick={() => create.mutate()}
        >
          <Plus size={16} /> Добавить голос
        </button>
        {create.isError && (
          <div className="mt-2 text-sm text-red-400">{(create.error as Error).message}</div>
        )}
      </div>

      <KokoroCatalog
        onUse={(v) =>
          setForm((f) => ({
            ...f,
            language: v.language,
            engine: "kokoro",
            voice_id: v.voice_id,
            name: f.name || `Kokoro ${v.language.toUpperCase()} — ${v.voice_id} (${v.gender === "f" ? "ж" : "м"})`,
          }))
        }
      />

      <div className="space-y-5">
        {Object.entries(byLang).map(([lang, list]) => (
          <div key={lang}>
            <h3 className="mb-2 text-sm font-medium text-muted">{lang.toUpperCase()}</h3>
            <div className="space-y-1.5">
              {list.map((v) => (
                <VoiceRow key={v.id} voice={v} onDelete={() => del.mutate(v.id)} />
              ))}
            </div>
          </div>
        ))}
        {voices?.length === 0 && <div className="text-sm text-muted">Голосов пока нет.</div>}
      </div>
    </div>
  );
}

function KokoroCatalog({
  onUse,
}: {
  onUse: (v: { language: string; voice_id: string; gender: "f" | "m" }) => void;
}) {
  const [open, setOpen] = useState(false);

  const byLang = useMemo(() => {
    return KOKORO_VOICES.reduce<Record<string, typeof KOKORO_VOICES>>((acc, v) => {
      (acc[v.language] ??= []).push(v);
      return acc;
    }, {});
  }, []);

  return (
    <div className="card mb-6">
      <button
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <h3 className="text-sm font-medium">
          Справка: каталог голосов Kokoro ({KOKORO_VOICES.length})
        </h3>
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>
      {!open && (
        <p className="mt-1 text-xs text-muted">
          Полный список ID голосов, доступных в Kokoro, по языкам — чтобы не угадывать. Открой и
          нажми «Использовать», чтобы подставить ID в форму выше.
        </p>
      )}
      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-muted">
            Схема ID: <code>{"{язык}{пол}_{имя}"}</code> — вторая буква <code>f</code> = женский,{" "}
            <code>m</code> = мужской. Список собран из публичной документации модели Kokoro-82M;
            если у тебя другая версия модели, какого-то ID может не быть — это сразу видно по
            ошибке при нажатии «Прослушать».
          </p>
          {Object.entries(byLang).map(([lang, list]) => (
            <div key={lang}>
              <h4 className="mb-1.5 text-xs font-medium uppercase text-muted">{lang}</h4>
              <div className="flex flex-wrap gap-1.5">
                {list.map((v) => (
                  <button
                    key={v.voice_id}
                    className="flex items-center gap-1 rounded-md bg-surface2 px-2 py-1 text-xs hover:bg-border"
                    onClick={() => onUse(v)}
                    title="Использовать этот голос в форме выше"
                  >
                    <code>{v.voice_id}</code>
                    <span className="text-muted">{v.gender === "f" ? "♀" : "♂"}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function VoiceRow({ voice, onDelete }: { voice: Voice; onDelete: () => void }) {
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const preview = useMutation({
    mutationFn: () => api.previewVoice(voice.id),
    onSuccess: (res) => setPreviewSrc(`${res.url}?t=${Date.now()}`),
  });
  const canPreview = voice.engine === "kokoro";

  return (
    <div className="card space-y-2 py-2.5 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{voice.name}</span>
            {voice.is_builtin && (
              <span className="flex items-center gap-1 rounded bg-surface2 px-1.5 py-0.5 text-xs text-muted">
                <Lock size={11} /> встроенный
              </span>
            )}
            <span className="rounded bg-indigo-600/20 px-1.5 py-0.5 text-xs text-indigo-300">
              {voice.engine}
            </span>
          </div>
          <div className="mt-0.5 text-xs text-muted">
            {voice.voice_id && <code>{voice.voice_id}</code>}
            {voice.description && <span> · {voice.description}</span>}
          </div>
        </div>
        <button
          className="btn-ghost px-2 py-1 text-xs disabled:opacity-40"
          disabled={!canPreview || preview.isPending}
          title={canPreview ? "Сгенерировать и прослушать короткий сэмпл" : "Доступно только для голосов Kokoro"}
          onClick={() => preview.mutate()}
        >
          <Play size={13} /> {preview.isPending ? "Генерация…" : "Прослушать"}
        </button>
        {!voice.is_builtin && (
          <button
            className="text-muted hover:text-red-400"
            onClick={() => confirm(`Удалить голос «${voice.name}»?`) && onDelete()}
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>
      {preview.isError && (
        <p className="text-xs text-red-300">{(preview.error as Error).message}</p>
      )}
      {previewSrc && <audio controls autoPlay src={previewSrc} className="w-full" />}
    </div>
  );
}
