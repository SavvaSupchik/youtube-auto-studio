import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "../lib/api";

export function MemoryViewer({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const { data: memory } = useQuery({
    queryKey: ["memory", projectId],
    queryFn: () => api.projectMemory(projectId),
  });

  const del = useMutation({
    mutationFn: (videoId: string) => api.deleteMemory(projectId, videoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memory", projectId] }),
  });

  const filtered = (memory ?? []).filter(
    (m) =>
      !search ||
      m.title.toLowerCase().includes(search.toLowerCase()) ||
      m.hook.toLowerCase().includes(search.toLowerCase()) ||
      m.topics.some((t) => t.toLowerCase().includes(search.toLowerCase()))
  );

  const allTopics = Array.from(new Set((memory ?? []).flatMap((m) => m.topics)));

  return (
    <div className="space-y-4">
      <input
        className="input max-w-md"
        placeholder="Поиск по hook / теме / заголовку…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {allTopics.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {allTopics.map((t) => (
            <span key={t} className="rounded-full bg-surface2 px-2 py-0.5 text-xs text-muted">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((m) => (
          <div key={m.video_id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div className="font-medium">{m.title}</div>
              <button
                className="text-muted hover:text-red-400"
                onClick={() => del.mutate(m.video_id)}
                title="Не учитывать в памяти"
              >
                <Trash2 size={16} />
              </button>
            </div>
            <div className="mt-1 text-sm italic text-gray-300">«{m.hook}»</div>
            <div className="mt-1 text-sm text-muted">{m.summary_short}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {m.topics.map((t) => (
                <span
                  key={t}
                  className="rounded bg-indigo-600/20 px-1.5 py-0.5 text-xs text-indigo-300"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-10 text-center text-muted">
            Память пуста — сгенерируйте первое видео
          </div>
        )}
      </div>
    </div>
  );
}
