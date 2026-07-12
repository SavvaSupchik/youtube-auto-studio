import { create } from "zustand";

/**
 * Локальный UI-state (не серверные данные — те живут в TanStack Query).
 * Например, выбранный язык во вкладках видео, открытые модалки и т.п.
 */
interface UIState {
  activeLangByVideo: Record<string, string>;
  setActiveLang: (videoId: string, lang: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeLangByVideo: {},
  setActiveLang: (videoId, lang) =>
    set((s) => ({ activeLangByVideo: { ...s.activeLangByVideo, [videoId]: lang } })),
}));
