import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtDuration } from "../lib/format";
import { StatusBadge } from "../components/StatusBadge";
import { ProjectSettings } from "../components/ProjectSettings";
import { MemoryViewer } from "../components/MemoryViewer";
import { ProjectStatsPanel } from "../components/ProjectStatsPanel";

type Tab = "videos" | "settings" | "memory" | "stats";

export default function ProjectView() {
  const { projectId = "" } = useParams();
  const [tab, setTab] = useState<Tab>("videos");
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
  });
  const { data: videos } = useQuery({
    queryKey: ["videos", projectId],
    queryFn: () => api.listVideos(projectId),
  });

  if (!project) return <div className="p-6 text-muted">Загрузка…</div>;

  const tabs: [Tab, string][] = [
    ["videos", "Видео"],
    ["settings", "Настройки"],
    ["memory", "Память"],
    ["stats", "Статистика"],
  ];

  return (
    <div className="mx-auto max-w-6xl p-6">
      <div className="mb-4 flex items-center gap-3">
        <span className="h-4 w-4 rounded-full" style={{ background: project.accent_color }} />
        <h1 className="text-2xl font-bold">{project.name}</h1>
        <span className="text-sm text-muted">{project.niche}</span>
      </div>

      <div className="mb-5 flex gap-1 border-b border-border">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm ${
              tab === key
                ? "border-indigo-500 text-white"
                : "border-transparent text-muted hover:text-gray-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "videos" && (
        <div>
          <div className="mb-3 flex justify-end">
            <Link to={`/projects/${projectId}/new`} className="btn-primary">
              <Plus size={16} /> Создать видео
            </Link>
          </div>
          <div className="space-y-2">
            {videos?.map((v) => (
              <Link
                key={v.id}
                to={`/videos/${v.id}`}
                className="card flex items-center gap-4 hover:border-indigo-600"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{v.title || v.topic_brief}</div>
                  <div className="truncate text-xs text-muted">{v.topic_brief}</div>
                </div>
                <div className="text-xs text-muted">{fmtDuration(v.duration_sec)}</div>
                <div className="text-xs text-muted">{fmtDate(v.created_at)}</div>
                <StatusBadge status={v.status} />
              </Link>
            ))}
            {videos?.length === 0 && (
              <div className="rounded-xl border border-dashed border-border p-10 text-center text-muted">
                Видео пока нет
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "settings" && <ProjectSettings project={project} />}
      {tab === "memory" && <MemoryViewer projectId={projectId} />}
      {tab === "stats" && <ProjectStatsPanel projectId={projectId} />}
    </div>
  );
}
