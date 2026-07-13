import type {
  AdaptedPrompts,
  Analysis,
  AppSettings,
  AudioTrack,
  CostEstimate,
  GenLog,
  GlobalStats,
  MemoryEntry,
  MusicTrack,
  NicheReport,
  NicheStatus,
  Project,
  ProjectStats,
  RenderParams,
  Script,
  ScriptTemplate,
  ThumbnailEntry,
  Video,
  VisualAsset,
  Voice,
  YouTubePackage,
} from "./types";

const BASE = "";

async function http<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface NewVideoPayload {
  topic_brief: string;
  title?: string;
  script_content?: string | null;
  script_prompts?: Record<string, string> | null;
  languages?: string[] | null;
  target_duration_min?: number | null;
  run_translate?: boolean;
  run_tts?: boolean;
  run_render?: boolean;
  run_visuals?: boolean;
}

export const api = {
  // Projects
  listProjects: () => http<Project[]>("/api/projects"),
  getProject: (id: string) => http<Project>(`/api/projects/${id}`),
  createProject: (data: Partial<Project>) =>
    http<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
  updateProject: (id: string, data: Partial<Project>) =>
    http<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteProject: (id: string) =>
    http<void>(`/api/projects/${id}`, { method: "DELETE" }),
  projectMemory: (id: string) => http<MemoryEntry[]>(`/api/projects/${id}/memory`),
  suggestTopics: (id: string, count = 6) =>
    http<{ title: string; brief: string }[]>(`/api/projects/${id}/suggest-topics?count=${count}`, { method: "POST" }),
  deleteMemory: (id: string, videoId: string) =>
    http<void>(`/api/projects/${id}/memory/${videoId}`, { method: "DELETE" }),
  projectStats: (id: string) => http<ProjectStats>(`/api/projects/${id}/stats`),

  // Videos
  listVideos: (projectId: string) =>
    http<Video[]>(`/api/projects/${projectId}/videos`),
  createVideo: (projectId: string, data: NewVideoPayload) =>
    http<Video>(`/api/projects/${projectId}/videos`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getVideo: (id: string) => http<Video>(`/api/videos/${id}`),
  deleteVideo: (id: string) => http<void>(`/api/videos/${id}`, { method: "DELETE" }),
  rerun: (id: string, data: NewVideoPayload) =>
    http<Video>(`/api/videos/${id}/rerun`, { method: "POST", body: JSON.stringify(data) }),
  scripts: (id: string) => http<Script[]>(`/api/videos/${id}/scripts`),
  editScript: (id: string, lang: string, content_md: string) =>
    http<Script>(`/api/videos/${id}/scripts/${lang}`, {
      method: "PATCH",
      body: JSON.stringify({ content_md }),
    }),
  analysis: (id: string) => http<Analysis>(`/api/videos/${id}/analysis`),
  audio: (id: string) => http<AudioTrack[]>(`/api/videos/${id}/audio`),
  audioHistory: (id: string) => http<AudioTrack[]>(`/api/videos/${id}/audio/history`),
  activateAudioVersion: (id: string, lang: string, version: number) =>
    http<AudioTrack[]>(`/api/videos/${id}/audio/${lang}/activate/${version}`, { method: "PUT" }),
  visuals: (id: string) => http<VisualAsset[]>(`/api/videos/${id}/visuals`),
  visualsHistory: (id: string) => http<VisualAsset[]>(`/api/videos/${id}/visuals/history`),
  allVisuals: (id: string) => http<VisualAsset[]>(`/api/videos/${id}/visuals/all`),
  getPlaylist: (id: string) => http<{ playlist: string[] }>(`/api/videos/${id}/visuals/playlist`),
  setPlaylist: (id: string, playlist: string[]) =>
    http<{ playlist: string[] }>(`/api/videos/${id}/visuals/playlist`, {
      method: "PUT", body: JSON.stringify({ playlist }),
    }),
  activateVisualsVersion: (id: string, version: number) =>
    http<VisualAsset[]>(`/api/videos/${id}/visuals/activate/${version}`, { method: "PUT" }),
  rendersHistory: (id: string, lang: string) =>
    http<VisualAsset[]>(`/api/videos/${id}/renders/${lang}/history`),
  activateRenderVersion: (id: string, lang: string, version: number) =>
    http<VisualAsset[]>(`/api/videos/${id}/renders/${lang}/activate/${version}`, { method: "PUT" }),
  logs: (id: string) => http<GenLog[]>(`/api/videos/${id}/logs`),
  setVoiceOverride: (id: string, lang: string, voice_id: string | null) =>
    http<Video>(`/api/videos/${id}/voice/${lang}`, {
      method: "PUT",
      body: JSON.stringify({ voice_id }),
    }),
  rerunStage: (id: string, stage: string, lang?: string, visual_engine?: string) => {
    const params = new URLSearchParams();
    if (lang) params.set("lang", lang);
    if (visual_engine) params.set("visual_engine", visual_engine);
    const qs = params.toString();
    return http<{ status: string }>(`/api/videos/${id}/stages/${stage}${qs ? `?${qs}` : ""}`, { method: "POST" });
  },
  cancelPipeline: (id: string) =>
    http<{ status: string }>(`/api/videos/${id}/cancel`, { method: "POST" }),
  setRenderParams: (id: string, params: RenderParams) =>
    http<Video>(`/api/videos/${id}/render_params`, {
      method: "PUT",
      body: JSON.stringify(params),
    }),

  uploadAudio: async (id: string, lang: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/videos/${id}/audio/${lang}`, { method: "POST", body: form });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res.json() as Promise<AudioTrack>;
  },

  // Stats
  globalStats: () => http<GlobalStats>("/api/stats/global"),

  // Глобальные настройки приложения (голоса по умолчанию и т.п.)
  getSettings: () => http<AppSettings>("/api/settings"),
  saveSettings: (data: Partial<AppSettings>) =>
    http<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(data) }),
  resetVoiceParams: () =>
    http<AppSettings>("/api/settings/voice-params/reset", { method: "POST" }),

  // Шаблоны сценария (глобальные, редактируются в Настройках)
  listTemplates: () => http<ScriptTemplate[]>("/api/templates"),
  saveTemplate: (name: string, content: string) =>
    http<ScriptTemplate>(`/api/templates/${name}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  resetTemplate: (name: string) =>
    http<ScriptTemplate>(`/api/templates/${name}/reset`, { method: "POST" }),
  adaptPrompts: (projectId: string, topic: string) =>
    http<AdaptedPrompts>("/api/templates/adapt", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, topic }),
    }),

  // Voices (общая библиотека)
  listVoices: (language?: string) =>
    http<Voice[]>(`/api/voices${language ? `?language=${encodeURIComponent(language)}` : ""}`),
  createVoice: (data: Omit<Voice, "id" | "created_at" | "is_builtin">) =>
    http<Voice>("/api/voices", { method: "POST", body: JSON.stringify(data) }),
  updateVoice: (id: string, data: Partial<Voice>) =>
    http<Voice>(`/api/voices/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteVoice: (id: string) => http<void>(`/api/voices/${id}`, { method: "DELETE" }),
  previewVoice: (id: string) =>
    http<{ status: string; url: string }>(`/api/voices/${id}/preview`, { method: "POST" }),

  // Music library
  listMusic: () => http<MusicTrack[]>("/api/music"),
  getMusic: (id: string) => http<MusicTrack>(`/api/music/${id}`),
  generateSuno: (data: { prompt: string; tags?: string; title?: string; instrumental?: boolean }) =>
    http<MusicTrack>("/api/music/generate", { method: "POST", body: JSON.stringify(data) }),
  browseMusic: () => http<{ path: string | null }>("/api/music/browse"),
  uploadMusic: (filePath: string) =>
    http<MusicTrack>("/api/music/upload", {
      method: "POST",
      body: JSON.stringify({ file_path: filePath }),
    }),
  deleteMusic: (id: string) => http<void>(`/api/music/${id}`, { method: "DELETE" }),
  setVideoMusic: (videoId: string, trackId: string | null, volume: number) =>
    http<Video>(`/api/videos/${videoId}/music`, {
      method: "PUT",
      body: JSON.stringify({ music_track_id: trackId, music_volume: volume }),
    }),
  getThumbnailHistory: (videoId: string) =>
    http<ThumbnailEntry[]>(`/api/videos/${videoId}/thumbnail-history`),
  restoreThumbnail: (videoId: string, version: number) =>
    http<{ status: string }>(`/api/videos/${videoId}/thumbnail-restore`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),

  // Монтаж: превью, YouTube-пакет
  previewRender: (videoId: string) =>
    http<{ url: string }>(`/api/videos/${videoId}/preview-render`, { method: "POST" }),
  youtubePackage: (videoId: string) =>
    http<YouTubePackage>(`/api/videos/${videoId}/youtube-package`),
  openVideoFolder: (videoId: string) =>
    http<{ folder: string }>(`/api/videos/${videoId}/open-folder`, { method: "POST" }),
  estimateCost: (projectId: string, p: { duration_min: number; visuals: boolean; translate: boolean }) =>
    http<CostEstimate>(
      `/api/projects/${projectId}/estimate?duration_min=${p.duration_min}&visuals=${p.visuals}&translate=${p.translate}`
    ),

  // Niche analysis
  nicheStatus: () => http<NicheStatus>("/api/niche/status"),
  listNicheReports: (kind?: "scan" | "deep") =>
    http<NicheReport[]>(`/api/niche/reports${kind ? `?kind=${kind}` : ""}`),
  getNicheReport: (id: string) => http<NicheReport>(`/api/niche/reports/${id}`),
  deleteNicheReport: (id: string) =>
    http<void>(`/api/niche/reports/${id}`, { method: "DELETE" }),
  nicheScan: (data: { seed: string; region?: string; language?: string; max_niches?: number }) =>
    http<NicheReport>("/api/niche/scan", { method: "POST", body: JSON.stringify(data) }),
  nicheDeepDive: (data: { keyword: string; region?: string; language?: string }) =>
    http<NicheReport>("/api/niche/deep-dive", { method: "POST", body: JSON.stringify(data) }),
};

export function wsUrl(videoId: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/ws/jobs/${videoId}`;
}

export function srtUrl(videoId: string, lang: string): string {
  return `/api/videos/${videoId}/subtitles/${lang}`;
}

export function fileUrl(filePath: string): string {
  // file_path хранится как абсолютный путь; берём часть после projects/
  const idx = filePath.replace(/\\/g, "/").indexOf("/projects/");
  if (idx === -1) return filePath;
  return "/files" + filePath.replace(/\\/g, "/").slice(idx);
}
