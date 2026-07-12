import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Music2, Trash2, Upload, Wand2, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import type { MusicTrack } from "../lib/types";

function fmtDur(sec: number | null) {
  if (!sec) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function StatusDot({ status }: { status: MusicTrack["status"] }) {
  const colors: Record<string, string> = {
    ready: "bg-emerald-400",
    pending: "bg-yellow-400 animate-pulse",
    error: "bg-red-400",
  };
  return <span className={`inline-block h-2 w-2 rounded-full ${colors[status] ?? "bg-muted"}`} />;
}

export function Music() {
  const qc = useQueryClient();
  const { data: tracks = [], isLoading } = useQuery({
    queryKey: ["music"],
    queryFn: () => api.listMusic(),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((t) => t.status === "pending") ? 3000 : false,
  });

  // Suno generation form
  const [sunoPrompt, setSunoPrompt] = useState("");
  const [sunoTags, setSunoTags] = useState("");
  const [sunoTitle, setSunoTitle] = useState("");
  const [showSuno, setShowSuno] = useState(false);

  const generateSuno = useMutation({
    mutationFn: () =>
      api.generateSuno({ prompt: sunoPrompt, tags: sunoTags, title: sunoTitle, instrumental: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["music"] });
      setSunoPrompt("");
      setSunoTags("");
      setSunoTitle("");
      setShowSuno(false);
    },
  });

  // Загрузка через системный диалог на сервере (без multipart upload)
  const uploadMutation = useMutation({
    mutationFn: async () => {
      const { path } = await api.browseMusic();
      if (!path) return null;
      return api.uploadMusic(path);
    },
    onSuccess: (track) => {
      if (track) qc.invalidateQueries({ queryKey: ["music"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteMusic(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["music"] }),
  });

  return (
    <div className="mx-auto max-w-3xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Music2 size={24} /> Музыкальная библиотека
        </h1>
        <div className="flex gap-2">
          <button
            className="btn-ghost flex items-center gap-1 text-sm"
            onClick={() => uploadMutation.mutate()}
            disabled={uploadMutation.isPending}
          >
            <Upload size={15} /> {uploadMutation.isPending ? "Выбираем…" : "Загрузить файл"}
          </button>
          <button
            className="btn-primary flex items-center gap-1 text-sm"
            onClick={() => setShowSuno((v) => !v)}
          >
            <Wand2 size={15} /> Suno AI
          </button>
        </div>
      </div>

      {uploadMutation.error && (
        <p className="text-sm text-red-400">{String(uploadMutation.error)}</p>
      )}

      {/* Форма генерации Suno */}
      {showSuno && (
        <div className="card space-y-3 border border-indigo-500/40">
          <p className="text-sm text-muted">
            Генерация через{" "}
            <a
              href="https://github.com/gcui-art/suno-api"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-400 hover:underline"
            >
              suno-api
            </a>
            . Укажите <code className="text-xs bg-surface2 px-1 rounded">SUNO_API_URL</code> в{" "}
            <code className="text-xs bg-surface2 px-1 rounded">.env</code>.
          </p>
          <div>
            <label className="label">Описание музыки (промт)</label>
            <textarea
              className="input min-h-[64px]"
              placeholder="Calm cinematic background, orchestral, no vocals"
              value={sunoPrompt}
              onChange={(e) => setSunoPrompt(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Название (необязательно)</label>
              <input
                className="input"
                placeholder="Моя тема"
                value={sunoTitle}
                onChange={(e) => setSunoTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="label">Теги (жанр, настроение)</label>
              <input
                className="input"
                placeholder="cinematic, orchestral, calm"
                value={sunoTags}
                onChange={(e) => setSunoTags(e.target.value)}
              />
            </div>
          </div>
          {generateSuno.error && (
            <p className="text-sm text-red-400">{String(generateSuno.error)}</p>
          )}
          <div className="flex gap-2">
            <button
              className="btn-primary"
              disabled={!sunoPrompt.trim() || generateSuno.isPending}
              onClick={() => generateSuno.mutate()}
            >
              {generateSuno.isPending ? "Отправляем…" : "Генерировать"}
            </button>
            <button className="btn-ghost" onClick={() => setShowSuno(false)}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* Список треков */}
      {isLoading ? (
        <p className="text-muted text-sm">Загрузка…</p>
      ) : tracks.length === 0 ? (
        <div className="card text-center py-12 text-muted space-y-2">
          <Music2 size={40} className="mx-auto opacity-30" />
          <p>Библиотека пуста</p>
          <p className="text-xs">Загрузите аудиофайл или сгенерируйте через Suno AI</p>
        </div>
      ) : (
        <div className="space-y-2">
          {tracks.map((t) => (
            <TrackRow
              key={t.id}
              track={t}
              onDelete={() => confirm("Удалить трек?") && deleteMutation.mutate(t.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TrackRow({ track, onDelete }: { track: MusicTrack; onDelete: () => void }) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  const toggle = () => {
    if (!audioRef.current) return;
    if (playing) {
      audioRef.current.pause();
      setPlaying(false);
    } else {
      audioRef.current.play();
      setPlaying(true);
    }
  };

  const audioSrc = track.file_path
    ? "/files/music/" + track.file_path.replace(/\\/g, "/").split("/music/")[1]
    : "";

  return (
    <div className="card flex items-center gap-3">
      <button
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface2 hover:bg-border disabled:opacity-40 text-lg"
        disabled={track.status !== "ready" || !audioSrc}
        onClick={toggle}
        title={playing ? "Пауза" : "Слушать"}
      >
        {track.status === "pending" ? (
          <RefreshCw size={14} className="animate-spin" />
        ) : playing ? "⏸" : "▶"}
      </button>

      {audioSrc && (
        <audio
          ref={audioRef}
          src={audioSrc}
          onEnded={() => setPlaying(false)}
          className="hidden"
        />
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <StatusDot status={track.status} />
          <span className="font-medium truncate">{track.title || "Без названия"}</span>
          <span className="text-xs text-muted shrink-0">
            {track.source === "suno" ? "🎵 Suno" : "📁 Файл"}
          </span>
        </div>
        <div className="flex gap-3 text-xs text-muted mt-0.5">
          {track.tags && <span>{track.tags}</span>}
          <span>{fmtDur(track.duration_sec)}</span>
          {track.status === "pending" && <span className="text-yellow-400">Генерируется…</span>}
          {track.status === "error" && <span className="text-red-400">Ошибка</span>}
        </div>
      </div>

      <button
        className="text-muted hover:text-red-400 p-1"
        onClick={onDelete}
        title="Удалить"
      >
        <Trash2 size={15} />
      </button>
    </div>
  );
}
