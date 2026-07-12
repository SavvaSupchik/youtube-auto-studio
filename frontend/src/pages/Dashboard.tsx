import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Film, HardDrive, Plus, Video as VideoIcon } from "lucide-react";
import { api } from "../lib/api";
import { fmtBytes, fmtDuration } from "../lib/format";
import { NewProjectModal } from "../components/NewProjectModal";

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="card flex items-center gap-3">
      <div className="rounded-lg bg-surface2 p-2 text-indigo-400">{icon}</div>
      <div>
        <div className="text-xl font-semibold">{value}</div>
        <div className="text-xs text-muted">{label}</div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const qc = useQueryClient();
  const [showNew, setShowNew] = useState(false);
  const { data: projects } = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });
  const { data: stats } = useQuery({ queryKey: ["globalStats"], queryFn: api.globalStats });

  const del = useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });

  return (
    <div className="mx-auto max-w-6xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Дашборд</h1>
        <button className="btn-primary" onClick={() => setShowNew(true)}>
          <Plus size={16} /> Новый канал
        </button>
      </div>

      {stats && !stats.llm_configured && (
        <div className="card mb-6 flex items-start gap-3 border-amber-700/50 bg-amber-950/30">
          <AlertTriangle className="mt-0.5 shrink-0 text-amber-400" size={18} />
          <div className="text-sm text-amber-200">
            <b>
              {stats.llm_provider === "gemini" ? "GEMINI_API_KEY" : "ANTHROPIC_API_KEY"} не задан.
            </b>{" "}
            Генерация сценариев недоступна (провайдер: {stats.llm_provider}). Укажите ключ в{" "}
            <code>.env</code> и перезапустите бэкенд.
          </div>
        </div>
      )}

      {stats && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard icon={<Film size={20} />} label="Каналов" value={String(stats.total_projects)} />
          <StatCard icon={<VideoIcon size={20} />} label="Видео" value={String(stats.total_videos)} />
          <StatCard
            icon={<HardDrive size={20} />}
            label="Диск"
            value={fmtBytes(stats.disk_usage_bytes)}
          />
          <StatCard
            icon={<span className="text-sm font-bold">$</span>}
            label="Расход токенов"
            value={`$${stats.total_cost_usd.toFixed(3)}`}
          />
        </div>
      )}

      <h2 className="mb-3 text-lg font-semibold">Каналы</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {projects?.map((p) => (
          <div key={p.id} className="card group relative">
            <Link to={`/projects/${p.id}`} className="block">
              <div className="mb-2 flex items-center gap-2">
                <span
                  className="h-3 w-3 rounded-full"
                  style={{ background: p.accent_color }}
                />
                <span className="font-medium">{p.name}</span>
              </div>
              <div className="mb-3 text-sm text-muted">{p.niche || "Без ниши"}</div>
              <div className="flex gap-4 text-xs text-muted">
                <span>{p.video_count ?? 0} видео</span>
                <span>{p.ready_count ?? 0} готово</span>
                <span>{p.language_primary.toUpperCase()}</span>
              </div>
            </Link>
            <button
              className="absolute right-3 top-3 hidden text-xs text-red-400 hover:underline group-hover:block"
              onClick={() => {
                if (confirm(`Удалить канал «${p.name}» со всеми видео?`)) del.mutate(p.id);
              }}
            >
              Удалить
            </button>
          </div>
        ))}
        {projects?.length === 0 && (
          <div className="col-span-full rounded-xl border border-dashed border-border p-10 text-center text-muted">
            Создайте первый канал, чтобы начать
          </div>
        )}
      </div>

      {showNew && <NewProjectModal onClose={() => setShowNew(false)} />}
    </div>
  );
}
