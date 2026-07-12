import { NavLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Clapperboard, LayoutDashboard, Mic, Music2, Plus, Radar, Settings } from "lucide-react";
import { api } from "../lib/api";

export function Sidebar() {
  const navigate = useNavigate();
  const { data: projects } = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2 px-4 py-4 text-lg font-semibold">
        <Clapperboard className="text-indigo-400" size={22} />
        <span>Auto Studio</span>
      </div>

      <NavLink
        to="/"
        className={({ isActive }) =>
          `mx-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
            isActive ? "bg-surface2 text-white" : "text-muted hover:bg-surface2"
          }`
        }
      >
        <LayoutDashboard size={18} /> Дашборд
      </NavLink>

      <NavLink
        to="/voices"
        className={({ isActive }) =>
          `mx-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
            isActive ? "bg-surface2 text-white" : "text-muted hover:bg-surface2"
          }`
        }
      >
        <Mic size={18} /> Голоса
      </NavLink>

      <NavLink
        to="/music"
        className={({ isActive }) =>
          `mx-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
            isActive ? "bg-surface2 text-white" : "text-muted hover:bg-surface2"
          }`
        }
      >
        <Music2 size={18} /> Музыка
      </NavLink>

      <NavLink
        to="/niches"
        className={({ isActive }) =>
          `mx-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
            isActive ? "bg-surface2 text-white" : "text-muted hover:bg-surface2"
          }`
        }
      >
        <Radar size={18} /> Анализ ниш
      </NavLink>

      <NavLink
        to="/settings"
        className={({ isActive }) =>
          `mx-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
            isActive ? "bg-surface2 text-white" : "text-muted hover:bg-surface2"
          }`
        }
      >
        <Settings size={18} /> Настройки
      </NavLink>

      <div className="mt-4 px-4 text-xs uppercase tracking-wide text-muted">Каналы</div>
      <nav className="mt-1 flex-1 space-y-0.5 overflow-y-auto px-2">
        {projects?.map((p) => (
          <NavLink
            key={p.id}
            to={`/projects/${p.id}`}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                isActive ? "bg-surface2 text-white" : "text-gray-300 hover:bg-surface2"
              }`
            }
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: p.accent_color }}
            />
            <span className="truncate">{p.name}</span>
            <span className="ml-auto text-xs text-muted">{p.video_count ?? 0}</span>
          </NavLink>
        ))}
        {projects?.length === 0 && (
          <div className="px-3 py-2 text-sm text-muted">Каналов пока нет</div>
        )}
      </nav>

      <button className="btn-ghost m-2" onClick={() => navigate("/")}>
        <Plus size={16} /> Новый канал
      </button>
    </aside>
  );
}
