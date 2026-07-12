import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { fmtDuration } from "../lib/format";

export function ProjectStatsPanel({ projectId }: { projectId: string }) {
  const { data: stats } = useQuery({
    queryKey: ["projectStats", projectId],
    queryFn: () => api.projectStats(projectId),
  });
  if (!stats) return <div className="text-muted">Загрузка…</div>;

  const topicData = stats.top_topics.map(([name, count]) => ({ name, count }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Всего видео" value={String(stats.total_videos)} />
        <Metric label="Готово" value={String(stats.ready_videos)} />
        <Metric label="В работе" value={String(stats.generating_videos)} />
        <Metric label="Суммарно" value={fmtDuration(stats.total_duration_sec)} />
      </div>

      <div className="card">
        <h3 className="mb-3 text-sm font-medium">Топ тем</h3>
        {topicData.length === 0 ? (
          <div className="text-sm text-muted">Пока нет данных</div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={topicData} layout="vertical" margin={{ left: 20 }}>
              <XAxis type="number" stroke="#8b8b9e" fontSize={12} allowDecimals={false} />
              <YAxis type="category" dataKey="name" stroke="#8b8b9e" fontSize={12} width={120} />
              <Tooltip
                contentStyle={{ background: "#1c1c28", border: "1px solid #2a2a3a" }}
                cursor={{ fill: "#ffffff10" }}
              />
              <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <div className="text-xl font-semibold">{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}
