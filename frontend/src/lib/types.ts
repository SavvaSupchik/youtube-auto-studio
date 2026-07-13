export interface ThumbnailEntry {
  version: number;
  created_at: string;
  model: string;
  prompt: string;
  file: string;
  archived_file: string | null;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  niche: string;
  target_audience: string;
  style_prompt: string;
  language_primary: string;
  languages_export: string[];
  voice_settings: Record<string, string>;
  tts_mode: string;
  accent_color: string;
  particles_enabled: boolean;
  intro_enabled: boolean;
  intro_template: string;
  default_music_track_id: string | null;
  default_music_volume: number;
  created_at: string;
  updated_at: string;
  video_count?: number;
  ready_count?: number;
}

export interface RenderParams {
  resolution: "720p" | "1080p" | "1440p";
  // "off" = без зума; "on" (или старые subtle/normal/strong) = зум включён
  zoom: string;
  zoom_speed: number; // % кадра в секунду, 0.05–5.0 (0.3 = очень медленно)
  zoom_direction: "in" | "out" | "alternate" | "pan";
  warm_grade: boolean; // устаревшее; актуален grade
  grade: "off" | "warm" | "cold" | "vintage" | "bw";
  vignette: boolean;
  grain: boolean;
  overlay: "off" | "fireflies" | "embers" | "dust";
  transition: "none" | "dip" | "fade";
  fade_in: boolean;
  fade_out: boolean;
}

export interface YouTubePackage {
  titles: string[];
  description: string;
  tags: string[];
  tags_string: string;
}

export interface CostEstimate {
  llm_usd: number;
  visuals_usd: number;
  total_usd: number;
  n_images: number;
  based_on_history: boolean;
  llm_provider: string;
}

export interface Script {
  id: string;
  video_id: string;
  language: string;
  content_md: string;
  word_count: number;
  duration_estimate_sec: number;
  is_primary: boolean;
  created_at: string;
}

export interface Analysis {
  id: string;
  script_id: string;
  hook: string;
  summary_short: string;
  summary_long: string;
  key_points: string[];
  topics: string[];
  structure: string[];
  tone: string;
  title_suggestions: string[];
  youtube_tags: string[];
}

export interface AudioTrack {
  id: string;
  script_id: string;
  file_path: string;
  duration_sec: number;
  voice_id: string;
  engine: string;
  status: string;
  version: number;
  archived: boolean;
}

export interface GenLog {
  id: string;
  video_id: string;
  stage: string;
  model_used: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  duration_sec: number;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface GlobalStats {
  total_projects: number;
  total_videos: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  total_duration_sec: number;
  disk_usage_bytes: number;
  llm_provider: string;
  llm_configured: boolean;
}

export interface ProjectStats {
  total_videos: number;
  ready_videos: number;
  draft_videos: number;
  generating_videos: number;
  error_videos: number;
  total_duration_sec: number;
  top_topics: [string, number][];
}

export interface Voice {
  id: string;
  name: string;
  language: string;
  engine: string;
  voice_id: string;
  description: string;
  is_builtin: boolean;
  created_at: string;
}

export interface MusicTrack {
  id: string;
  title: string;
  source: "suno" | "upload" | "manual";
  tags: string;
  file_path: string;
  duration_sec: number | null;
  status: "pending" | "ready" | "error";
  created_at: string;
}

export interface Video {
  id: string;
  project_id: string;
  title: string;
  topic_brief: string;
  status: "draft" | "generating" | "ready" | "error";
  duration_sec: number | null;
  voice_overrides: Record<string, string>;
  script_prompts: Record<string, string>;
  render_params: RenderParams;
  music_track_id: string | null;
  music_volume: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

export interface VisualAsset {
  id: string;
  file_path: string;
  asset_metadata: { index: number; prompt: string; style?: string; version?: number; archived?: boolean };
}

export interface AppSettings {
  default_voices: Record<string, string>;
}

export interface ScriptTemplate {
  name: string;
  title: string;
  content: string;
  overridden: boolean;
}

export interface AdaptedPrompts {
  stage1: string;
  stage2: string;
  stage3: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface MemoryEntry {
  video_id: string;
  created_at: string;
  title: string;
  hook: string;
  summary_short: string;
  key_points: string[];
  topics: string[];
  structure: string[];
}

// ===== Анализ ниш YouTube =====
export interface NicheStatus {
  youtube_configured: boolean;
  llm_configured: boolean;
  region_default: string;
  language_default: string;
}

export interface NicheMetrics {
  keyword: string;
  sample_size: number;
  total_results: number;
  median_views: number;
  median_subs: number;
  outlier_ratio: number;
  share_recent_90d: number;
  median_engagement: number;
  top_channel_dominance: number;
  demand_score: number;
  supply_score: number;
  outlier_score: number;
  freshness_score: number;
  engagement_score: number;
  opportunity_score: number;
  // присутствует у элементов скана
  rationale?: string;
  // если замер не удался (напр. квота)
  error?: string;
}

export interface ScanResult {
  seed: string;
  region: string;
  language: string;
  niches: NicheMetrics[];
  quota_note: string;
}

export interface NicheTopVideo {
  video_id: string;
  title: string;
  channel: string;
  channel_subs: number;
  views: number;
  views_to_subs: number;
  published_at: string;
  url: string;
}

export interface NicheTrend {
  available: boolean;
  interest: number;
  direction: string;
  rising: string[];
  note: string;
}

export interface NicheVerdict {
  verdict: string;
  one_liner: string;
  reasoning: string;
  content_angles: string[];
  recommended_formats: string[];
  risks: string[];
}

export interface DeepDiveResult {
  keyword: string;
  region: string;
  language: string;
  metrics: NicheMetrics;
  top_videos: NicheTopVideo[];
  trend: NicheTrend;
  verdict: NicheVerdict;
}

export interface NicheReport {
  id: string;
  kind: "scan" | "deep";
  query: string;
  region: string;
  language: string;
  payload: ScanResult | DeepDiveResult;
  note: string;
  created_at: string;
}
