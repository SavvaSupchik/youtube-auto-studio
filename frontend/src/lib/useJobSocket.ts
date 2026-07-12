import { useEffect, useRef, useState } from "react";
import { wsUrl } from "./api";

export interface JobEvent {
  type: string;
  stage?: string;
  error?: string;
  duration_sec?: number;
  status?: string;
  video_id?: string;
}

/** Подписка на WebSocket прогресса пайплайна для конкретного видео. */
export function useJobSocket(videoId: string | null, enabled: boolean) {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [done, setDone] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!videoId || !enabled) return;
    setEvents([]);
    setDone(false);
    const ws = new WebSocket(wsUrl(videoId));
    wsRef.current = ws;
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data) as JobEvent;
      if (data.type === "ping" || data.type === "connected") return;
      setEvents((prev) => [...prev, data]);
      if (
        data.type === "pipeline_done" ||
        data.type === "pipeline_error" ||
        data.type === "stage_retry_done"
      ) {
        setDone(true);
      }
    };
    return () => ws.close();
  }, [videoId, enabled]);

  return { events, done };
}
